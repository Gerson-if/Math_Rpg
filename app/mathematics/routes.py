"""
Mathematics engine blueprint: browse topics, practice a topic (question in,
answer out, immediately loop to the next question), and view answer
history. XP/mastery/streak updates are deliberately NOT done here — that's
Fase 4 (Progressão), which reads from the Attempt rows this blueprint
writes. Keeping the two separated means the mathematics engine has no idea
progression even exists, matching the "XP calculation centralized in one
service" requirement from the spec.
"""
from datetime import datetime, timezone

from flask import Blueprint, render_template, request, abort, jsonify
from flask_login import login_required, current_user

import random

from app.extensions import db, limiter
from app.models import Subject, Topic, Attempt
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


def _normalize(value: str) -> str:
    """Numeric-aware comparison: '007' == '7', '0,3' == '0.3' (pt-BR decimal
    comma) == '0.30', and whole-valued floats collapse to plain ints ('3.0'
    == '3') so decimal-operation answers that land on a whole number still
    match. Falls back to a trimmed/lowered/space-stripped string compare for
    non-numeric answers (e.g. fractions like '5/6')."""
    value = (value or "").strip().replace(",", ".")
    try:
        return str(int(value))
    except (TypeError, ValueError):
        pass
    try:
        as_float = float(value)
        return str(int(as_float)) if as_float.is_integer() else repr(as_float)
    except (TypeError, ValueError):
        return value.lower().replace(" ", "")


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
    return render_template(
        "mathematics/index.html",
        subjects=subjects,
        recommend_first=recommend_first,
        guardians=subject_guardians,
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
    return render_template(
        "mathematics/practice.html",
        topic=topic,
        guardian=guardians.for_subject(topic.subject.slug),
        recommend_first=progression_service.unmet_prerequisites(current_user.id, topic),
        mentor_tip=mentor_tips.random_tip(),
        ally=dungeon_service.active_ally(current_user.id, topic.id),
        equipped=loot_service.list_equipped(current_user.id),
        buffs=loot_service.compute_buffs(current_user.id),
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
            "needs_review": progress["needs_review"],
            "new_achievements": progress["new_achievements"],
            "is_crit": is_crit,
            "crit_item": crit_item,
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


@mathematics_bp.route("/cronicas")
@login_required
def chronicles():
    """The kingdom's lore, one chronicle per subject — discovered as soon
    as the player has practiced anything in that subject at all (no
    mastery threshold; this is flavor, not a gate)."""
    subjects = Subject.query.filter_by(is_active=True).order_by(Subject.order).all()
    discovered_subject_ids = {
        row[0]
        for row in (
            db.session.query(Topic.subject_id)
            .join(Attempt, Attempt.topic_id == Topic.id)
            .filter(Attempt.user_id == current_user.id)
            .distinct()
            .all()
        )
    }
    chronicles_by_subject = [
        (subject, lore.for_subject(subject.slug), subject.id in discovered_subject_ids)
        for subject in subjects
        if lore.for_subject(subject.slug) is not None
    ]
    return render_template("mathematics/chronicles.html", chronicles=chronicles_by_subject)


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
