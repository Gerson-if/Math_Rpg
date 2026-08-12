"""
Progression service — the single place XP, levels, ranks, mastery and
achievement unlocks are computed, per the spec's requirement that
progression rules not be scattered through the codebase.

This module has no idea *how* a question was generated or corrected — it
only reads an already-persisted `Attempt` and updates everything that
should react to it. `app/mathematics/routes.py` calls `process_attempt`
right after saving the Attempt; nothing else needs to know this module
exists.
"""
from datetime import datetime, timedelta

from flask import current_app
from sqlalchemy import func

from app.extensions import db
from app.models import (
    Attempt,
    PlayerStats,
    Level,
    Rank,
    Mastery,
    Achievement,
    UserAchievement,
    Notification,
)

# XP per correct answer, scaled by difficulty (1..5). Wrong answers award
# no XP — XP measures effort-that-paid-off, not just participation, so it
# stays a meaningful signal on top of raw practice volume.
_XP_BY_DIFFICULTY = {1: 10, 2: 15, 3: 20, 4: 30, 5: 45}

# How much a topic's mastery score can decay from not being practiced.
# Retention (section 4 of the spec) is what makes mastery different from a
# one-time completion checkbox.
_RETENTION_GRACE_DAYS = 7
_RETENTION_DECAY_PER_DAY = 0.02
_RETENTION_MAX_DECAY = 0.4


def process_attempt(attempt: Attempt) -> dict:
    """Update stats, level/rank, mastery and achievements for one answered
    question. Commits its own transaction. Returns a summary usable for
    immediate UI feedback (XP earned, level-up, unlocked achievements)."""

    stats = _get_or_create_stats(attempt.user_id)

    xp_awarded = _xp_for_attempt(attempt)
    stats.xp += xp_awarded

    if attempt.is_correct:
        stats.total_correct += 1
        stats.current_streak += 1
        stats.best_streak = max(stats.best_streak, stats.current_streak)
    else:
        stats.total_wrong += 1
        stats.current_streak = 0
    stats.last_active_at = datetime.utcnow()

    leveled_up = _update_level(stats)
    _update_rank(stats)

    mastery = _update_mastery(attempt)

    new_achievements = _check_achievements(attempt.user_id, stats)

    db.session.commit()

    return {
        "xp_awarded": xp_awarded,
        "leveled_up": leveled_up,
        "level_number": stats.level.number if stats.level else None,
        "mastery_score": mastery.mastery_score,
        "needs_review": mastery.needs_review,
        "new_achievements": new_achievements,
    }


def _get_or_create_stats(user_id: int) -> PlayerStats:
    stats = PlayerStats.query.filter_by(user_id=user_id).first()
    if stats is None:
        stats = PlayerStats(user_id=user_id)
        db.session.add(stats)
        db.session.flush()
    return stats


def _xp_for_attempt(attempt: Attempt) -> int:
    if not attempt.is_correct:
        return 0
    return _XP_BY_DIFFICULTY.get(attempt.difficulty, 10)


def _update_level(stats: PlayerStats) -> bool:
    """Returns True if this attempt caused a level-up."""
    previous_number = stats.level.number if stats.level else 0

    new_level = (
        Level.query.filter(Level.xp_required <= stats.xp)
        .order_by(Level.number.desc())
        .first()
    )
    if new_level is None:
        return False

    if new_level.id != stats.level_id:
        stats.level_id = new_level.id
        return new_level.number > previous_number
    return False


def _update_rank(stats: PlayerStats) -> None:
    if stats.level is None:
        return
    new_rank = (
        Rank.query.filter(Rank.min_level <= stats.level.number)
        .order_by(Rank.order.desc())
        .first()
    )
    if new_rank is not None:
        stats.rank_id = new_rank.id


def _update_mastery(attempt: Attempt) -> Mastery:
    mastery = Mastery.query.filter_by(
        user_id=attempt.user_id, topic_id=attempt.topic_id
    ).first()
    if mastery is None:
        mastery = Mastery(user_id=attempt.user_id, topic_id=attempt.topic_id)
        db.session.add(mastery)
        db.session.flush()

    now = datetime.utcnow()

    # Retention: a long gap since last practice erodes mastery even though
    # nothing "went wrong" — this is what lets the review system in
    # section 4 notice "you used to be good at this."
    if mastery.last_practiced_at:
        days_since = (now - mastery.last_practiced_at).days
        if days_since > _RETENTION_GRACE_DAYS:
            decay = min(
                _RETENTION_MAX_DECAY,
                _RETENTION_DECAY_PER_DAY * (days_since - _RETENTION_GRACE_DAYS),
            )
            mastery.mastery_score = max(0.0, mastery.mastery_score - decay)

    # Exponential moving average toward 1.0 (correct) or 0.0 (wrong),
    # weighted so a correct answer at higher difficulty moves mastery more
    # than an easy one, and a wrong answer at low difficulty hurts more
    # than a wrong one on a hard question (it should have been solid).
    difficulty_weight = 0.5 + attempt.difficulty / 10  # 0.6 .. 1.0
    alpha = 0.2 * difficulty_weight
    target = 1.0 if attempt.is_correct else 0.0
    mastery.mastery_score = max(
        0.0, min(1.0, mastery.mastery_score + alpha * (target - mastery.mastery_score))
    )

    if attempt.is_correct:
        mastery.correct_count += 1
        mastery.current_streak += 1
    else:
        mastery.wrong_count += 1
        mastery.current_streak = 0

    total_attempts = mastery.correct_count + mastery.wrong_count
    mastery.avg_response_time_ms = int(
        ((mastery.avg_response_time_ms * (total_attempts - 1)) + attempt.response_time_ms)
        / total_attempts
    )
    mastery.last_practiced_at = now

    threshold = current_app.config.get("MASTERY_REVIEW_THRESHOLD", 0.75)
    # Require a handful of data points before flagging for review, so one
    # unlucky slip on a brand-new topic doesn't trigger it immediately.
    mastery.needs_review = total_attempts >= 5 and mastery.mastery_score < threshold

    return mastery


def _check_achievements(user_id: int, stats: PlayerStats) -> list[Achievement]:
    already_unlocked_ids = {
        row.achievement_id
        for row in UserAchievement.query.filter_by(user_id=user_id).all()
    }

    unlocked = []
    for achievement in Achievement.query.all():
        if achievement.id in already_unlocked_ids:
            continue
        if _meets_criteria(user_id, stats, achievement.criteria or {}):
            db.session.add(UserAchievement(user_id=user_id, achievement_id=achievement.id))
            db.session.add(Notification(
                user_id=user_id,
                type="achievement",
                payload={"code": achievement.code, "name": achievement.name},
            ))
            unlocked.append(achievement)
    return unlocked


def _meets_criteria(user_id: int, stats: PlayerStats, criteria: dict) -> bool:
    """Declarative achievement criteria, read straight from the DB row —
    new achievement types just need a new branch here, not a schema
    change."""
    criteria_type = criteria.get("type")
    value = criteria.get("value")

    if criteria_type == "attempts_correct_total":
        return stats.total_correct >= value

    if criteria_type == "attempts_total":
        return (stats.total_correct + stats.total_wrong) >= value

    if criteria_type == "distinct_practice_days":
        distinct_days = (
            db.session.query(func.count(func.distinct(func.date(Attempt.created_at))))
            .filter(Attempt.user_id == user_id)
            .scalar()
        )
        return distinct_days >= value

    if criteria_type == "best_streak":
        return stats.best_streak >= value

    return False
