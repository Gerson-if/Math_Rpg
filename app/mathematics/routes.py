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

from flask import Blueprint, render_template, request, abort, jsonify, flash, redirect, url_for, session
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
    concepts_service,
    math_areas,
    recall_service,
)
from app.services import classes as classes_service

mathematics_bp = Blueprint("mathematics", __name__, url_prefix="/math")

# Flags the "castelo final" region on the adventure map as freshly added,
# progressive advanced content — purely a visual badge, never a gate (see
# scripts/seed.py's entry_prereqs for the advisory recommendation instead).
NEW_SUBJECT_SLUGS = {"algebra", "equacoes-2-grau", "geometria-basica"}

# How many of the most-recently-served prompts (per topic/subject, kept in
# the session — no DB row for something this disposable) generate_question
# tries to avoid repeating immediately. Small on purpose: the goal is
# killing the "same '2×3=?' twice in a row" feeling, not building a full
# history — a topic with a genuinely small number space still needs room
# to legitimately reuse a prompt after a few others have gone by.
_RECENT_PROMPTS_LIMIT = 4


def _recent_prompts(session_key: str) -> set[str]:
    return set(session.get(session_key, []))


def _remember_prompt(session_key: str, prompt: str) -> None:
    recent = session.get(session_key, [])
    recent.append(prompt)
    session[session_key] = recent[-_RECENT_PROMPTS_LIMIT:]
    session.modified = True


# Purely cosmetic response-time rating shown per answer — never affects
# XP/mastery (those are already fully decided by process_attempt before
# this even runs). A slow-but-correct answer still counts fully for real
# progression; it just earns fewer stars on screen.
STAR_TIME_THRESHOLDS_MS = (3000, 7000)  # <=3s: 3 stars, <=7s: 2 stars, else: 1


# Concept/vocabulary questions ("o que é numerador?") used to be mixed in
# at random alongside the numeric drills, right in the middle of a battle
# — a player mid-combo would suddenly get a text question with no warning.
# They're now their own dedicated exercise (see the /math/conceitos/
# routes below and mathematics/concepts.html), reached deliberately from
# the adventure map instead of sprung on the player mid-fight. The battle
# loop stays 100% numeric.


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

    # The map used to render all 11 subjects — each with its own guardian
    # AND full topic-dot grid — in one long scroll, regardless of how far
    # along the player actually was. That's the "muito confuso" the map
    # got redone for: a brand-new player scrolling past nine regions of
    # content they haven't touched yet has no idea where to even start.
    # Now only subjects the player has already engaged with (has at least
    # one Attempt in) render in full, plus exactly one "peek" ahead — the
    # very next subject in the trail — shown misty/collapsed (guardian
    # silhouette only, no topic grid) as a preview of what's coming, not
    # a wall of content to parse. Nothing is hard-locked (same philosophy
    # as unmet_prerequisites/boss_unmet above): the rest of the trail
    # still exists past that point, just folded into a single "further
    # ahead" marker instead of being dumped on screen all at once.
    discovered_ids = _discovered_subject_ids(current_user.id)
    last_discovered_idx = -1
    for i, subject in enumerate(subjects):
        if subject.id in discovered_ids:
            last_discovered_idx = i
    # Subject 0 is always shown in full — it's the trail's entry point,
    # reachable via "Início" even before the player has a single Attempt
    # anywhere — so the reveal frontier never sits behind index 0.
    full_reveal_idx = max(0, last_discovered_idx) if subjects else -1
    reveal_count = min(len(subjects), full_reveal_idx + 2)
    visible_subjects = subjects[:reveal_count]
    hidden_count = len(subjects) - len(visible_subjects)
    preview_subject_id = (
        visible_subjects[full_reveal_idx + 1].id
        if len(visible_subjects) > full_reveal_idx + 1
        else None
    )

    # One "Conceitos" node per subject, next to its guardian — a distinct
    # kind of waypoint (book, not a star-dotted trail) so a player looking
    # at the map can tell at a glance "this teaches me the vocabulary" vs
    # "this drills the calculation", instead of the two being mixed inside
    # the same practice screen the way concept questions used to be.
    subject_areas = {subject.id: math_areas.area_slugs_for_subject(subject) for subject in subjects}

    return render_template(
        "mathematics/index.html",
        subjects=visible_subjects,
        hidden_count=hidden_count,
        preview_subject_id=preview_subject_id,
        recommend_first=recommend_first,
        guardians=subject_guardians,
        new_subjects=NEW_SUBJECT_SLUGS,
        boss_topics=boss_topics,
        boss_unmet=boss_unmet,
        first_topic=first_topic,
        subject_areas=subject_areas,
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


@mathematics_bp.route("/conceitos/<subject_slug>")
@login_required
def concepts(subject_slug):
    """Dedicated concept/vocabulary exercise for one Subject — deliberately
    separate from the numeric battle loop (see the module docstring near
    the top of this file for why they used to be mixed). No XP/loot/mastery
    is touched here: this is a quiet reading-and-recall exercise, not
    another arena, so it never competes with the battle screen's own
    progression for the player's attention."""
    subject = Subject.query.filter_by(slug=subject_slug, is_active=True).first_or_404()
    area_slugs = math_areas.area_slugs_for_subject(subject)
    session_key = f"recent_q:concepts:{subject.slug}"
    question = concepts_service.random_concept_question_for_areas(
        area_slugs, avoid_prompts=_recent_prompts(session_key)
    )
    if question is None:
        flash("Esta trilha ainda não tem conceitos cadastrados.", "info")
        return redirect(url_for("mathematics.index"))
    _remember_prompt(session_key, question["prompt"])

    token = question_token.make_token(subject.slug, 0, question["answer"])
    return render_template(
        "mathematics/concepts.html",
        subject=subject,
        prompt=question["prompt"],
        options=concepts_service.build_options(question),
        token=token,
    )


@mathematics_bp.route("/conceitos/<subject_slug>/responder", methods=["POST"])
@login_required
@limiter.limit("120 per minute")
def concepts_answer(subject_slug):
    subject = Subject.query.filter_by(slug=subject_slug, is_active=True).first_or_404()
    area_slugs = math_areas.area_slugs_for_subject(subject)

    token = request.form.get("token", "")
    submitted_answer = request.form.get("answer", "")
    try:
        payload = question_token.read_token(token)
    except question_token.TokenError:
        abort(400, description="Pergunta expirada ou inválida — carregue uma nova.")
    if payload.get("topic") != subject.slug:
        abort(400)

    is_correct = _normalize(submitted_answer) == _normalize(payload["answer"])

    session_key = f"recent_q:concepts:{subject.slug}"
    next_question = concepts_service.random_concept_question_for_areas(
        area_slugs, avoid_prompts=_recent_prompts(session_key)
    )
    if next_question:
        _remember_prompt(session_key, next_question["prompt"])
    next_token = (
        question_token.make_token(subject.slug, 0, next_question["answer"])
        if next_question
        else None
    )

    return render_template(
        "mathematics/_concept_question.html",
        subject=subject,
        prompt=next_question["prompt"] if next_question else None,
        options=concepts_service.build_options(next_question) if next_question else None,
        token=next_token,
        feedback={
            "is_correct": is_correct,
            "correct_answer": payload["answer"],
            "picked_answer": submitted_answer,
        },
    )


def _practice_context(topic):
    """Everything the story screen / battle config need for one topic —
    factored out of practice() so the same data can also be served as JSON
    (see practice_summary below), used to build the next topic's story
    screen dynamically when advancing from a victory instead of a full
    page reload."""
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

    # The battle's "ultimate" attack used to always be the same generic
    # "Fúria Arcana Suprema" regardless of class — a Guerreiro casting an
    # arcane spell made no sense. Now it uses the player's own class
    # ability name (see classes_service.ability_for), same one shown on
    # their profile, falling back to the old generic name for anyone who
    # hasn't picked a class yet.
    profile = current_user.profile
    class_key = profile.character_class if profile else None
    ultimate_name = "Fúria Arcana Suprema"
    class_info = None
    if class_key and profile.class_tier_claimed >= 0:
        class_info = classes_service.display_for(class_key, profile.class_tier_claimed)
        ultimate_name = classes_service.ability_for(class_key, profile.class_tier_claimed) or ultimate_name

    return {
        "topic": topic,
        "guardian": display_guardian,
        "boss_tier": boss_tier,
        "recommend_first": progression_service.unmet_prerequisites(current_user.id, topic),
        "mentor_tip": mentor_tips.random_tip(),
        "ally": dungeon_service.active_ally(current_user.id, topic.id),
        "equipped": loot_service.list_equipped(current_user.id),
        "buffs": loot_service.compute_buffs(current_user.id),
        "chronicle": lore.for_subject(topic.subject.slug),
        "special_attacks": guardians.special_attacks_for(topic.subject.slug),
        "battle_taunts": guardians.battle_taunts_for(topic.subject.slug),
        "topic_mastery": topic_mastery,
        "best_stars": best_stars,
        "ultimate_name": ultimate_name,
        "class_info": class_info,
        "next_topic": progression_service.next_topic_for(topic),
        "mastery_threshold": progression_service.PREREQUISITE_MASTERY_THRESHOLD,
    }


@mathematics_bp.route("/praticar/<topic_slug>")
@login_required
def practice(topic_slug):
    topic = Topic.query.filter_by(slug=topic_slug, is_active=True).first_or_404()
    return render_template("mathematics/practice.html", **_practice_context(topic))


@mathematics_bp.route("/praticar/<topic_slug>/resumo")
@login_required
def practice_summary(topic_slug):
    """JSON snapshot of a topic's story-screen data — used by the battle
    arena to build the next phase's "resumo" screen dynamically (the exact
    same data the story screen would render, generated on the fly instead
    of a full page navigation) right after a victory, before playing the
    invocation animation into the new fight. See advanceToNextTopic in
    battle-arena.js."""
    topic = Topic.query.filter_by(slug=topic_slug, is_active=True).first_or_404()
    ctx = _practice_context(topic)
    topic_mastery = ctx["topic_mastery"]
    ally = ctx["ally"]
    next_topic = ctx["next_topic"]

    return jsonify({
        "topicSlug": topic.slug,
        "topicName": topic.name,
        "practiceUrl": url_for("mathematics.practice", topic_slug=topic.slug),
        "victoryUrl": url_for("mathematics.claim_victory", topic_slug=topic.slug),
        "newQuestionUrl": url_for("mathematics.new_question", topic_slug=topic.slug),
        "guardian": ctx["guardian"],
        "bossTier": ctx["boss_tier"],
        "topicMastery": ({
            "score": topic_mastery.mastery_score,
            "pct": int(round(topic_mastery.mastery_score * 100)),
            "correctCount": topic_mastery.correct_count,
            "wrongCount": topic_mastery.wrong_count,
        } if topic_mastery else None),
        "bestStars": ctx["best_stars"],
        "ally": ({"username": ally.username} if ally else None),
        "recommendFirst": [
            {"slug": t.slug, "name": t.name, "url": url_for("mathematics.practice", topic_slug=t.slug)}
            for t in ctx["recommend_first"]
        ],
        "mentorTip": ctx["mentor_tip"],
        "equippedCount": len([v for v in ctx["equipped"].values() if v]),
        "equipamentosUrl": url_for("character.equipamentos"),
        "buffs": ctx["buffs"],
        "chronicle": ctx["chronicle"],
        "specialAttacks": ctx["special_attacks"],
        "battleTaunts": ctx["battle_taunts"],
        "ultimateName": ctx["ultimate_name"],
        "masteryThreshold": ctx["mastery_threshold"],
        "nextTopic": ({
            "slug": next_topic.slug,
            "name": next_topic.name,
            "url": url_for("mathematics.practice", topic_slug=next_topic.slug),
            "resumoUrl": url_for("mathematics.practice_summary", topic_slug=next_topic.slug),
        } if next_topic else None),
    })


@mathematics_bp.route("/praticar/<topic_slug>/questao")
@login_required
def new_question(topic_slug):
    topic = Topic.query.filter_by(slug=topic_slug, is_active=True).first_or_404()
    difficulty = progression_service.get_effective_difficulty(current_user.id, topic)
    session_key = f"recent_q:{topic.slug}"
    try:
        q = mathematics_service.generate_question(
            topic.slug, difficulty,
            due_fingerprint=recall_service.due_fingerprint(current_user.id, topic.id),
            avoid_prompts=_recent_prompts(session_key),
        )
    except ValueError:
        abort(404)
    _remember_prompt(session_key, q["prompt"])

    token = question_token.make_token(topic.slug, difficulty, q["answer"], fingerprint=q["meta"].get("fingerprint"))
    return render_template(
        "mathematics/_question.html", topic=topic, prompt=q["prompt"], token=token,
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

    # Per-fact memory (see app/services/recall_service) — separate from,
    # and read alongside, the per-topic Mastery row updated by
    # process_attempt below. Only ever set on the token when the question
    # came from a family that tracks individual facts (currently just
    # tabuada — see mathematics_service._tabuada_prompt); a bare .get
    # keeps this a no-op for every other topic.
    recall_service.record_result(current_user.id, topic.id, payload.get("fp"), is_correct)

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
    # next_difficulty is re-read *after* process_attempt() above, so it
    # already reflects the update from the answer just submitted — and so
    # does due_fingerprint: a fact just missed becomes eligible for review
    # on THIS same next question rather than waiting a full round-trip.
    next_difficulty = progression_service.get_effective_difficulty(current_user.id, topic)
    session_key = f"recent_q:{topic.slug}"
    next_q = mathematics_service.generate_question(
        topic.slug, next_difficulty,
        due_fingerprint=recall_service.due_fingerprint(current_user.id, topic.id),
        avoid_prompts=_recent_prompts(session_key),
    )
    _remember_prompt(session_key, next_q["prompt"])
    next_token = question_token.make_token(
        topic.slug, next_difficulty, next_q["answer"], fingerprint=next_q["meta"].get("fingerprint")
    )

    next_topic = progression_service.next_topic_for(topic)

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
            "mastery_threshold": progression_service.PREREQUISITE_MASTERY_THRESHOLD,
            "next_topic_slug": next_topic.slug if next_topic else None,
            "next_topic_name": next_topic.name if next_topic else None,
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
