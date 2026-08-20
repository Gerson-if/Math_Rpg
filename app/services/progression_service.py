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
    Subject,
    Topic,
    Profile,
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

# Dynamic difficulty (section 9 of the spec deferred this to "future" —
# it's built on top of Mastery, which Fase 4 already tracks). Require a
# few data points before adapting so one lucky/unlucky answer on a fresh
# topic doesn't swing difficulty around.
_DIFFICULTY_MIN_ATTEMPTS = 3
_DIFFICULTY_STREAK_BONUS_AT = 5
# A correct answer that still takes this long on average isn't fluent
# yet, even if it's usually right — see get_effective_difficulty below.
_SLOW_RESPONSE_MS = 12000


def process_attempt(attempt: Attempt, bonus_xp: int = 0) -> dict:
    """Update stats, level/rank, mastery and achievements for one answered
    question. Commits its own transaction. Returns a summary usable for
    immediate UI feedback (XP earned, level-up, unlocked achievements).

    `bonus_xp` is an optional, caller-verified extra amount — currently
    only used by the dungeon co-op invite (see app/services/
    dungeon_service.py): practicing the same topic as an accepted ally
    within their invite window grants a small bonus on top of the normal
    difficulty-based XP. It's additive and only ever applied by the route,
    never inferred here, so this module still has no idea co-op exists."""

    stats = _get_or_create_stats(attempt.user_id)

    applied_bonus = max(0, bonus_xp) if attempt.is_correct else 0
    xp_awarded = _xp_for_attempt(attempt) + applied_bonus
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

    mastery, mastery_just_dropped, mastery_just_recovered = _update_mastery(attempt)

    new_achievements = _check_achievements(attempt.user_id, stats)

    db.session.commit()

    return {
        "xp_awarded": xp_awarded,
        "bonus_xp": applied_bonus,
        "leveled_up": leveled_up,
        "level_number": stats.level.number if stats.level else None,
        "mastery_score": mastery.mastery_score,
        "needs_review": mastery.needs_review,
        "mastery_just_dropped": mastery_just_dropped,
        "mastery_just_recovered": mastery_just_recovered,
        "new_achievements": new_achievements,
    }


def get_effective_difficulty(user_id: int, topic: Topic) -> int:
    """Adapts `topic.base_difficulty` to how this user is actually doing on
    it. Read-only — mathematics_service's generators stay DB-free by
    design, so the routes layer calls this before generating a question
    instead of the generators reading Mastery themselves.

    High mastery or a hot streak nudge difficulty up; a topic the user is
    clearly struggling with nudges it back down. Everything stays inside
    the existing 1..5 range topics were already authored for.
    """
    mastery = Mastery.query.filter_by(user_id=user_id, topic_id=topic.id).first()
    if mastery is None:
        return topic.base_difficulty

    total_attempts = mastery.correct_count + mastery.wrong_count
    if total_attempts < _DIFFICULTY_MIN_ATTEMPTS:
        return topic.base_difficulty

    delta = 0
    if mastery.mastery_score >= 0.9:
        delta += 2
    elif mastery.mastery_score >= 0.75:
        delta += 1
    elif mastery.mastery_score < 0.35:
        delta -= 1

    if mastery.current_streak >= _DIFFICULTY_STREAK_BONUS_AT:
        delta += 1

    # High mastery alone doesn't mean it's *easy* for this student — if
    # correct answers are still taking a long time on average, an upward
    # bump would be outrunning actual fluency. Cap the increase by one
    # step instead of skipping it outright, so a slow-but-solid student
    # still progresses, just more gradually than a fast one.
    if delta > 0 and mastery.avg_response_time_ms >= _SLOW_RESPONSE_MS:
        delta -= 1

    return max(1, min(5, topic.base_difficulty + delta))


# Mastery score above which a prerequisite topic counts as "solid enough"
# to recommend moving on — deliberately looser than MASTERY_REVIEW_THRESHOLD
# (which flags an already-practiced topic for review), since this is about
# a first-time recommendation, not a regression warning.
_PREREQUISITE_MASTERY_THRESHOLD = 0.5
# Public alias — the battle screen shows this same number live (see
# app/mathematics/routes.py) so a player watching their mastery bar climb
# during a fight sees the exact threshold that will unlock next_topic_for
# below, not a second number that happens to mean something similar.
PREREQUISITE_MASTERY_THRESHOLD = _PREREQUISITE_MASTERY_THRESHOLD


def next_topic_for(topic: Topic) -> Topic | None:
    """The topic that immediately follows this one along the overall
    curriculum — i.e. the topic that would drop out of
    unmet_prerequisites once *this* topic's mastery clears
    PREREQUISITE_MASTERY_THRESHOLD. Used to auto-advance the battle screen
    instead of leaving the player to find "tabuada do 2" on the map
    themselves.

    Normally the next topic in the same subject's linear chain (see
    scripts/seed.py: each topic's prerequisite_slugs is just the one
    right before it). But when `topic` is the *last* one in its subject —
    the boss fight — the journey doesn't just stop there: it continues
    into the first topic of the next active subject, same as picking the
    next region on the adventure map by hand. Only None once the very
    last subject's boss has been reached, with nowhere left to go."""
    within_subject = (
        Topic.query.filter_by(subject_id=topic.subject_id, order=topic.order + 1, is_active=True)
        .first()
    )
    if within_subject:
        return within_subject

    next_subject = (
        Subject.query.filter(Subject.order > topic.subject.order, Subject.is_active.is_(True))
        .order_by(Subject.order.asc())
        .first()
    )
    if next_subject is None:
        return None
    return (
        Topic.query.filter_by(subject_id=next_subject.id, order=0, is_active=True)
        .first()
    )


def unmet_prerequisites(user_id: int, topic: Topic) -> list[Topic]:
    """Prerequisite topics (see Topic.prerequisite_slugs) this user hasn't
    reasonably mastered yet. Purely advisory — the caller decides how to
    show it (a badge, a note); nothing here blocks access to `topic`. An
    empty list means either there are no prerequisites or they're all
    already solid."""
    if not topic.prerequisite_slugs:
        return []

    prereq_topics = Topic.query.filter(Topic.slug.in_(topic.prerequisite_slugs)).all()
    if not prereq_topics:
        return []

    masteries = {
        m.topic_id: m.mastery_score
        for m in Mastery.query.filter(
            Mastery.user_id == user_id,
            Mastery.topic_id.in_([t.id for t in prereq_topics]),
        ).all()
    }
    return [
        t for t in prereq_topics
        if masteries.get(t.id, 0.0) < _PREREQUISITE_MASTERY_THRESHOLD
    ]


# Below this mastery score a topic is still worth focusing on even if it
# never dropped low enough to trip needs_review — see
# recommend_focus_topic below.
_FOCUS_MASTERY_THRESHOLD = 0.85

# Mirrors MIN_HITS_FOR_VICTORY in battle-arena.js: the battle arena won't
# actually let a fight end before this many correct answers land, so
# correct-attempt count // this threshold is a reasonable server-side
# proxy for "how many fights this player has effectively finished" in a
# subject — used to gate how many chronicle chapters are readable (see
# chronicle_chapters_unlocked below), instead of the whole story being
# available the instant the subject is merely discovered.
_CHRONICLE_CHAPTER_WIN_THRESHOLD = 10


def chronicle_chapters_unlocked(user_id: int, subject_id: int) -> int:
    """How many chronicle chapters this player has earned in a subject —
    always at least 1 once called (the opening chapter reads as soon as
    the subject is discovered; the caller is responsible for not calling
    this before that), climbing roughly one chapter per battle actually
    finished. Not capped against the chronicle's real chapter count here
    since this module has no idea how many chapters a chronicle has —
    the caller (app/mathematics/routes.py, which does) clamps it."""
    correct_count = (
        db.session.query(func.count(Attempt.id))
        .join(Topic, Attempt.topic_id == Topic.id)
        .filter(
            Attempt.user_id == user_id,
            Topic.subject_id == subject_id,
            Attempt.is_correct.is_(True),
        )
        .scalar()
    ) or 0
    return max(1, correct_count // _CHRONICLE_CHAPTER_WIN_THRESHOLD + 1)


def recommend_focus_topic(user_id: int) -> Topic | None:
    """The single topic this player would most benefit from practicing
    right now — built entirely from their own recorded performance
    (Mastery rows), not a fixed curriculum order. This is what "the
    system learns from the player" means here: no separate model to
    train, just reading the same mastery/review signals progression
    already tracks and picking the one topic they'd get the most value
    out of next.

    Priority: (1) the worst topic already flagged needs_review, so a
    real regression always wins; (2) failing that, the weakest topic
    they've attempted at all, as long as it's not already solid; (3)
    failing that (everything they've tried is solid), a brand-new topic
    they haven't attempted yet, to keep the curriculum moving. Returns
    None only if there's truly nothing left to recommend (no topics
    exist, or everything is both mastered and attempted)."""
    worst_needing_review = (
        Mastery.query.filter_by(user_id=user_id, needs_review=True)
        .order_by(Mastery.mastery_score.asc())
        .first()
    )
    if worst_needing_review is not None:
        return worst_needing_review.topic

    masteries = Mastery.query.filter_by(user_id=user_id).all()
    attempted_ids = {m.topic_id for m in masteries}
    if masteries:
        weakest = min(masteries, key=lambda m: m.mastery_score)
        if weakest.mastery_score < _FOCUS_MASTERY_THRESHOLD:
            return weakest.topic

    query = Topic.query.filter(Topic.is_active.is_(True))
    if attempted_ids:
        query = query.filter(~Topic.id.in_(attempted_ids))
    return query.order_by(Topic.subject_id, Topic.order).first()


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


def _update_mastery(attempt: Attempt) -> tuple[Mastery, bool, bool]:
    """Returns (mastery, just_started_needing_review, just_recovered) —
    the two *transitions* of the needs_review flag, not just its current
    value. needs_review stays true across every attempt while mastery
    sits below threshold, so a caller reading only the current value would
    re-notify "mastery dropped" on every single correct answer for as long
    as it takes to climb back over the line. Only the edges are
    notification-worthy."""
    mastery = Mastery.query.filter_by(
        user_id=attempt.user_id, topic_id=attempt.topic_id
    ).first()
    if mastery is None:
        mastery = Mastery(user_id=attempt.user_id, topic_id=attempt.topic_id)
        db.session.add(mastery)
        db.session.flush()

    was_needs_review = mastery.needs_review
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
    just_started_needing_review = (not was_needs_review) and mastery.needs_review
    just_recovered = was_needs_review and not mastery.needs_review

    return mastery, just_started_needing_review, just_recovered


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

    if unlocked:
        # Title is a cosmetic, ever-changing badge — the most recently
        # unlocked achievement in this batch becomes the displayed title.
        profile = Profile.query.filter_by(user_id=user_id).first()
        if profile is not None:
            profile.title = unlocked[-1].name

    return unlocked


def progress_for_achievement(user_id: int, stats: PlayerStats, criteria: dict) -> tuple[int, int] | None:
    """(current, target) for one achievement's criteria — the same numbers
    _meets_criteria compares, just handed back instead of collapsed into a
    bool, so the achievements page can render a real progress bar for
    anything still locked. Returns None for an unrecognized criteria type
    (nothing meaningful to show)."""
    criteria_type = criteria.get("type")
    value = criteria.get("value")

    if criteria_type == "attempts_correct_total":
        return stats.total_correct, value

    if criteria_type == "attempts_total":
        return stats.total_correct + stats.total_wrong, value

    if criteria_type == "distinct_practice_days":
        distinct_days = (
            db.session.query(func.count(func.distinct(func.date(Attempt.created_at))))
            .filter(Attempt.user_id == user_id)
            .scalar()
        )
        return distinct_days, value

    if criteria_type == "best_streak":
        return stats.best_streak, value

    if criteria_type == "level_reached":
        return (stats.level.number if stats.level else 0), value

    # value is the target Rank's `order` (not its slug) — comparing orders
    # means reaching any *later* tier still satisfies an earlier
    # milestone, same "at least this far" semantics as level_reached.
    if criteria_type == "rank_reached":
        return (stats.rank.order if stats.rank else 0), value

    if criteria_type == "attempts_correct_in_subject":
        count = (
            db.session.query(func.count(Attempt.id))
            .join(Topic, Attempt.topic_id == Topic.id)
            .join(Subject, Topic.subject_id == Subject.id)
            .filter(
                Attempt.user_id == user_id,
                Subject.slug == criteria.get("subject"),
                Attempt.is_correct.is_(True),
            )
            .scalar()
        )
        return count, value

    return None


def _meets_criteria(user_id: int, stats: PlayerStats, criteria: dict) -> bool:
    """Declarative achievement criteria, read straight from the DB row —
    new achievement types just need a new branch in progress_for_achievement
    above, not a schema change."""
    progress = progress_for_achievement(user_id, stats, criteria)
    if progress is None:
        return False
    current, target = progress
    return current >= target
