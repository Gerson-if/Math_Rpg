"""
Mathematics engine blueprint: browse topics, practice a topic (question in,
answer out, immediately loop to the next question), and view answer
history. XP/mastery/streak updates are deliberately NOT done here — that's
app.services.progression_service, which reads from the Attempt rows this
blueprint writes. Keeping the two separated means the mathematics engine
has no idea progression even exists, matching the "XP calculation
centralized in one service" requirement from the spec.
"""
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, abort, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user

import random

from app.extensions import db, limiter
from app.models import Subject, Topic, Attempt, Mastery
from app.services import (
    mathematics_service,
    question_token,
    progression_service,
    mentor_tips,
    dungeon_service,
    loot_service,
    guardians,
    lore,
)

mathematics_bp = Blueprint("mathematics", __name__, url_prefix="/math")

# Flags the "castelo final" region on the adventure map as freshly added,
# progressive advanced content — purely a visual badge, never a gate (see
# scripts/seed.py's entry_prereqs for the advisory recommendation instead).
NEW_SUBJECT_SLUGS = {"algebra"}


# Purely cosmetic response-time rating shown per answer — never affects
# XP/mastery (those are already fully decided by process_attempt before
# this even runs). A slow-but-correct answer still counts fully for real
# progression; it just earns fewer stars on screen.
STAR_TIME_THRESHOLDS_MS = (3000, 7000)  # <=3s: 3 stars, <=7s: 2 stars, else: 1


def _stars_for(is_correct: bool, elapsed_ms: int) -> int:
    if not is_correct:
        return 0
    fast, medium = STAR_TIME_THRESHOLDS_MS
    if elapsed_ms <= fast:
        return 3
    if elapsed_ms <= medium:
        return 2
    return 1


_normalize = mathematics_service.normalize_answer


@mathematics_bp.route("/")
@login_required
def index():
    subjects = (
        Subject.query.filter_by(is_active=True).order_by(Subject.order).all()
    )
    # Advisory only (see progression_service.unmet_prerequisites) — every
    # topic stays reachable, this just tells the adventure map which nodes
    # to flag as "pratique isso primeiro" instead of hard-locking anything.
    recommend_first = {
        topic.id: progression_service.unmet_prerequisites(current_user.id, topic)
        for subject in subjects
        for topic in subject.topics
    }
    subject_guardians = {subject.slug: guardians.for_subject(subject.slug) for subject in subjects}

    # The map's guardian landmark is now a real "fight the boss" shortcut,
    # not just an anchor scroll — but only once the topic right before it
    # (its chain prerequisite, same rule as everywhere else) is reasonably
    # mastered. boss_unmet[subject.id] being non-empty is what locks it.
    boss_topics = {}
    boss_unmet = {}
    for subject in subjects:
        topics_sorted = sorted(subject.topics, key=lambda t: t.order)
        if not topics_sorted:
            continue
        boss_topic = topics_sorted[-1]
        boss_topics[subject.id] = boss_topic
        boss_unmet[subject.id] = progression_service.unmet_prerequisites(current_user.id, boss_topic)

    # The "Início" landmark used to be purely decorative (no href at all)
    # — now it's a real onboarding shortcut straight into the easiest
    # topic in the curriculum (first topic of the first active subject,
    # by Subject.order/Topic.order), so a brand-new player always has an
    # obvious "start here" to click instead of guessing which node to try.
    first_topic = subjects[0].topics[0] if subjects and subjects[0].topics else None

    return render_template(
        "mathematics/index.html",
        subjects=subjects,
        recommend_first=recommend_first,
        guardians=subject_guardians,
        new_subjects=NEW_SUBJECT_SLUGS,
        boss_topics=boss_topics,
        boss_unmet=boss_unmet,
        first_topic=first_topic,
    )


@mathematics_bp.route("/topics")
def list_topics():
    """JSON view of the curriculum — used by the frontend build and handy
    for debugging without a browser."""
    subjects = Subject.query.order_by(Subject.order).all()
    return jsonify([
        {
            "slug": s.slug,
            "name": s.name,
            "topics": [{"slug": t.slug, "name": t.name} for t in s.topics],
        }
        for s in subjects
    ])


@mathematics_bp.route("/praticar/<topic_slug>")
@login_required
def practice(topic_slug):
    topic = Topic.query.filter_by(slug=topic_slug, is_active=True).first_or_404()
    display_guardian, boss_tier = guardians.for_topic(topic)
    if boss_tier == "boss":
        already_defeated = (
            Attempt.query.filter_by(user_id=current_user.id, topic_id=topic.id, is_correct=True).first()
            is not None
        )
        if already_defeated:
            display_guardian = dict(display_guardian, name=guardians.supreme_name_for(topic.subject.slug))
            boss_tier = "supreme"

    topic_mastery = Mastery.query.filter_by(user_id=current_user.id, topic_id=topic.id).first()
    # Best-ever star rating on this topic, derived from real Attempt
    # history (fastest correct answer) rather than a separately tracked
    # "high score" column — same STAR_TIME_THRESHOLDS_MS used to rate
    # each answer live during a battle (see answer_question below).
    best_correct = (
        Attempt.query.filter_by(user_id=current_user.id, topic_id=topic.id, is_correct=True)
        .order_by(Attempt.response_time_ms.asc())
        .first()
    )
    best_stars = _stars_for(True, best_correct.response_time_ms) if best_correct else None

    return render_template(
        "mathematics/practice.html",
        topic=topic,
        guardian=display_guardian,
        boss_tier=boss_tier,
        recommend_first=progression_service.unmet_prerequisites(current_user.id, topic),
        mentor_tip=mentor_tips.random_tip(),
        ally=dungeon_service.active_ally(current_user.id, topic.id),
        equipped=loot_service.list_equipped(current_user.id),
        buffs=loot_service.compute_buffs(current_user.id),
        chronicle=lore.for_subject(topic.subject.slug),
        special_attacks=guardians.special_attacks_for(topic.subject.slug),
        battle_taunts=guardians.battle_taunts_for(topic.subject.slug),
        topic_mastery=topic_mastery,
        best_stars=best_stars,
    )


@mathematics_bp.route("/praticar/<topic_slug>/questao")
@login_required
def new_question(topic_slug):
    topic = Topic.query.filter_by(slug=topic_slug, is_active=True).first_or_404()
    difficulty = progression_service.get_effective_difficulty(current_user.id, topic)
    try:
        q = mathematics_service.generate_question(topic.slug, difficulty)
    except ValueError:
        abort(404)

    token = question_token.make_token(topic.slug, difficulty, q["answer"])
    return render_template(
        "mathematics/_question.html", topic=topic, prompt=q["prompt"], token=token
    )


@mathematics_bp.route("/praticar/<topic_slug>/responder", methods=["POST"])
@login_required
@limiter.limit("120 per minute")
def answer_question(topic_slug):
    topic = Topic.query.filter_by(slug=topic_slug, is_active=True).first_or_404()

    token = request.form.get("token", "")
    submitted_answer = request.form.get("answer", "")

    try:
        payload, signed_at = question_token.read_token(token, return_timestamp=True)
    except question_token.TokenError:
        abort(400, description="Questão expirada ou inválida — carregue uma nova.")

    if payload.get("topic") != topic.slug:
        abort(400)

    is_correct = _normalize(submitted_answer) == _normalize(payload["answer"])

    elapsed_ms = int((datetime.now(timezone.utc) - signed_at).total_seconds() * 1000)
    elapsed_ms = max(0, min(elapsed_ms, 10 * 60 * 1000))  # clamp to [0, 10min]

    attempt = Attempt(
        user_id=current_user.id,
        topic_id=topic.id,
        difficulty=payload["difficulty"],
        is_correct=is_correct,
        response_time_ms=elapsed_ms,
    )
    db.session.add(attempt)
    db.session.flush()  # need attempt.id before progression can reference it

    ally = dungeon_service.active_ally(current_user.id, topic.id)
    bonus_xp = dungeon_service.COOP_BONUS_XP if ally else 0
    progress = progression_service.process_attempt(attempt, bonus_xp=bonus_xp)

    # Crit (and whatever it drops) is rolled here, server-side, using the
    # player's real equipped buffs — the client only ever animates what
    # already happened, never decides it. See loot_service module docstring.
    is_crit = is_correct and loot_service.roll_crit(current_user.id)
    crit_item = None
    if is_crit and random.random() < loot_service.LOOT_CHANCE_ON_CRIT:
        crit_item = loot_service.generate_item(current_user.id)

    # Keep the loop going: hand back feedback + the next question in one
    # response so practicing doesn't require a full page reload per item.
    # Difficulty is recomputed *after* process_attempt() above, so it
    # already reflects the mastery update from the answer just submitted.
    next_difficulty = progression_service.get_effective_difficulty(current_user.id, topic)
    next_q = mathematics_service.generate_question(topic.slug, next_difficulty)
    next_token = question_token.make_token(topic.slug, next_difficulty, next_q["answer"])

    return render_template(
        "mathematics/_question.html",
        topic=topic,
        prompt=next_q["prompt"],
        token=next_token,
        feedback={
            "is_correct": is_correct,
            "correct_answer": payload["answer"],
            "xp_awarded": progress["xp_awarded"],
            "bonus_xp": progress["bonus_xp"],
            "ally_name": ally.username if ally else None,
            "leveled_up": progress["leveled_up"],
            "level_number": progress["level_number"],
            "mastery_score": progress["mastery_score"],
            "needs_review": progress["mastery_just_dropped"],
            "mastery_recovered": progress["mastery_just_recovered"],
            "new_achievements": progress["new_achievements"],
            "is_crit": is_crit,
            "crit_item": crit_item,
            "stars": _stars_for(is_correct, elapsed_ms),
        },
    )


@mathematics_bp.route("/praticar/<topic_slug>/vitoria", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def claim_victory(topic_slug):
    """Guaranteed loot drop for cosmetically defeating the boss in the
    battle arena — see loot_service.claim_boss_kill_loot for the (modest,
    proportional) integrity check behind this."""
    topic = Topic.query.filter_by(slug=topic_slug, is_active=True).first_or_404()
    try:
        item = loot_service.claim_boss_kill_loot(current_user.id, topic.id)
    except ValueError as exc:
        abort(400, description=str(exc))

    return jsonify({
        "name": item.name,
        "icon_key": item.icon_key,
        "passive_type": item.passive_type,
        "passive_value": item.passive_value,
        "rarity": item.rarity,
    })


def _discovered_subject_ids(user_id: int) -> set[int]:
    return {
        row[0]
        for row in (
            db.session.query(Topic.subject_id)
            .join(Attempt, Attempt.topic_id == Topic.id)
            .filter(Attempt.user_id == user_id)
            .distinct()
            .all()
        )
    }


@mathematics_bp.route("/cronicas")
@login_required
def chronicles():
    """The kingdom's lore, one chronicle per subject — discovered as soon
    as the player has practiced anything in that subject at all (no
    mastery threshold; this is flavor, not a gate). How many chapters of
    each are actually *readable* is a separate, gradual thing — see
    chronicle_detail below."""
    subjects = Subject.query.filter_by(is_active=True).order_by(Subject.order).all()
    discovered_subject_ids = _discovered_subject_ids(current_user.id)
    chronicles_by_subject = []
    for subject in subjects:
        chronicle = lore.for_subject(subject.slug)
        if chronicle is None:
            continue
        discovered = subject.id in discovered_subject_ids
        unlocked = 0
        if discovered:
            unlocked = min(
                len(chronicle["stages"]),
                progression_service.chronicle_chapters_unlocked(current_user.id, subject.id),
            )
        chronicles_by_subject.append((subject, chronicle, discovered, unlocked))
    subject_guardians = {subject.slug: guardians.for_subject(subject.slug) for subject in subjects}
    return render_template(
        "mathematics/chronicles.html", chronicles=chronicles_by_subject, guardians=subject_guardians,
    )


@mathematics_bp.route("/cronicas/<subject_slug>")
@login_required
def chronicle_detail(subject_slug):
    """A single chronicle read as its own immersive, page-by-page story —
    not the whole thing dumped as one wall of text on the index. Chapters
    unlock gradually as the player actually wins battles in that subject
    (see progression_service.chronicle_chapters_unlocked) rather than the
    entire story being available the moment the subject is discovered —
    reading ahead of your own progress would spoil the pacing the battle
    arena's own chapter-reveal-per-victory is built around."""
    subject = Subject.query.filter_by(slug=subject_slug, is_active=True).first_or_404()
    chronicle = lore.for_subject(subject_slug)
    if chronicle is None:
        abort(404)
    if subject.id not in _discovered_subject_ids(current_user.id):
        flash(f"Pratique algo de {subject.name} para revelar esta crônica.", "warning")
        return redirect(url_for("mathematics.chronicles"))
    unlocked_chapters = min(
        len(chronicle["stages"]),
        progression_service.chronicle_chapters_unlocked(current_user.id, subject.id),
    )
    return render_template(
        "mathematics/chronicle_detail.html", subject=subject, chronicle=chronicle,
        unlocked_chapters=unlocked_chapters,
    )


@mathematics_bp.route("/historico")
@login_required
def history():
    attempts = (
        Attempt.query.filter_by(user_id=current_user.id)
        .order_by(Attempt.created_at.desc())
        .limit(50)
        .all()
    )
    return render_template("mathematics/history.html", attempts=attempts)
