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

from app.extensions import db
from app.models import Subject, Topic, Attempt
from app.services import mathematics_service, question_token, progression_service

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
    return render_template("mathematics/index.html", subjects=subjects)


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
    return render_template("mathematics/practice.html", topic=topic)


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

    progress = progression_service.process_attempt(attempt)

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
            "leveled_up": progress["leveled_up"],
            "level_number": progress["level_number"],
            "mastery_score": progress["mastery_score"],
            "needs_review": progress["needs_review"],
            "new_achievements": progress["new_achievements"],
        },
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
