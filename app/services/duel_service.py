"""Real-time 1v1 duels between accepted friends — the one part of this
app that's genuinely synchronized live between two sessions. Everything
that decides the OUTCOME of a round still happens here, server-side,
exactly like the solo battle's answer_question route: a submitted answer
is graded against a value the server generated and kept to itself, never
trusted from the client. app/duels/socket_events.py is purely the
transport layer on top of this — it's how both clients get told about a
state change instantly instead of via HTMX polling; it holds no game
logic of its own.

Friendly reminder for anyone tempted to add a third player: this module
assumes exactly two participants (challenger/opponent) throughout.
"""
import secrets
import threading
from datetime import datetime, timedelta

from app.extensions import db
from app.models import Duel, Notification, Topic, User
from app.services import mathematics_service

CHALLENGE_EXPIRY_MINUTES = 10
STARTING_HP = 100
DAMAGE_PER_ROUND = 20
ROUND_DIFFICULTY = 2  # fixed and moderate — a duel is a speed contest, not a curriculum-pacing exercise

# One lock per active duel, so two near-simultaneous submit_answer calls
# for the same duel can't both read the round as still open and both
# apply damage for it. Process-local by design (matches this app's
# "in-memory by default" pattern elsewhere, e.g. rate limiting) — a
# multi-worker deployment needs both players' sockets pinned to the same
# worker (or a proper distributed lock) for this to hold; see
# SOCKETIO_MESSAGE_QUEUE in config/config.py for the related multi-worker
# broadcast concern.
_round_locks: dict[int, threading.Lock] = {}
_round_locks_guard = threading.Lock()


class DuelError(Exception):
    pass


def _lock_for(duel_id: int) -> threading.Lock:
    with _round_locks_guard:
        lock = _round_locks.get(duel_id)
        if lock is None:
            lock = threading.Lock()
            _round_locks[duel_id] = lock
        return lock


def _room_code() -> str:
    return secrets.token_urlsafe(9)


def create_challenge(challenger_id: int, opponent_id: int, topic_id: int) -> Duel:
    if challenger_id == opponent_id:
        raise DuelError("Você não pode desafiar a si mesmo.")
    topic = Topic.query.get(topic_id)
    if topic is None:
        raise DuelError("Tópico não encontrado.")

    # Without this, nothing stopped the same pair from racking up several
    # pending challenges (or challenging each other in both directions at
    # once) — confusing on the receiving end (which one do I accept?) and
    # easy to spam by mashing the button.
    existing = Duel.query.filter(
        Duel.status.in_((Duel.STATUS_PENDING, Duel.STATUS_ACTIVE)),
        db.or_(
            db.and_(Duel.challenger_id == challenger_id, Duel.opponent_id == opponent_id),
            db.and_(Duel.challenger_id == opponent_id, Duel.opponent_id == challenger_id),
        ),
    ).first()
    if existing is not None:
        raise DuelError("Já existe um desafio pendente ou duelo em andamento com este jogador.")

    duel = Duel(
        room_code=_room_code(),
        challenger_id=challenger_id,
        opponent_id=opponent_id,
        topic_id=topic_id,
        status=Duel.STATUS_PENDING,
        challenger_hp=STARTING_HP,
        opponent_hp=STARTING_HP,
    )
    db.session.add(duel)
    db.session.flush()

    db.session.add(Notification(
        user_id=opponent_id,
        type="duel_challenge",
        payload={"duel_id": duel.id, "challenger_id": challenger_id, "topic_name": topic.name},
    ))
    db.session.commit()
    return duel


def is_challenge_expired(duel: Duel) -> bool:
    return duel.status == Duel.STATUS_PENDING and (
        datetime.utcnow() - duel.created_at > timedelta(minutes=CHALLENGE_EXPIRY_MINUTES)
    )


def respond_to_challenge(duel_id: int, user_id: int, accept: bool) -> Duel:
    duel = Duel.query.filter_by(id=duel_id, opponent_id=user_id, status=Duel.STATUS_PENDING).first()
    if duel is None:
        raise DuelError("Desafio não encontrado (ou já respondido).")
    if is_challenge_expired(duel):
        duel.status = Duel.STATUS_DECLINED
        db.session.commit()
        raise DuelError("Esse desafio expirou.")

    if accept:
        duel.status = Duel.STATUS_ACTIVE
        _start_round(duel)
    else:
        duel.status = Duel.STATUS_DECLINED
    db.session.commit()
    return duel


def _start_round(duel: Duel) -> None:
    question = mathematics_service.generate_question(duel.topic.slug, ROUND_DIFFICULTY)
    duel.current_prompt = question["prompt"]
    duel.current_answer = str(question["answer"])
    duel.round_number = (duel.round_number or 0) + 1


def get_active_duel(duel_id: int, user_id: int) -> Duel:
    duel = Duel.query.filter_by(id=duel_id).first()
    if duel is None or user_id not in (duel.challenger_id, duel.opponent_id):
        raise DuelError("Duelo não encontrado.")
    return duel


def submit_answer(duel_id: int, user_id: int, submitted_answer: str) -> dict:
    """Grades one player's guess at the duel's current shared question.
    Whoever lands the first CORRECT answer for a round wins it and damages
    the other player; a wrong answer just... doesn't do anything, so both
    players can keep guessing the same round. Returns a plain dict, not
    the Duel row itself, since this is handed almost directly to the
    Socket.IO broadcast in app/duels/socket_events.py."""
    with _lock_for(duel_id):
        duel = Duel.query.filter_by(id=duel_id, status=Duel.STATUS_ACTIVE).first()
        if duel is None:
            raise DuelError("Duelo não encontrado ou já encerrado.")
        if user_id not in (duel.challenger_id, duel.opponent_id):
            raise DuelError("Você não faz parte deste duelo.")

        is_correct = (
            mathematics_service.normalize_answer(submitted_answer)
            == mathematics_service.normalize_answer(duel.current_answer)
        )
        result = {
            "duel_id": duel.id,
            "answered_by": user_id,
            "is_correct": is_correct,
            "finished": False,
        }
        if not is_correct:
            return result

        result["correct_answer"] = duel.current_answer
        if user_id == duel.challenger_id:
            duel.opponent_hp = max(0, duel.opponent_hp - DAMAGE_PER_ROUND)
        else:
            duel.challenger_hp = max(0, duel.challenger_hp - DAMAGE_PER_ROUND)

        result["challenger_hp"] = duel.challenger_hp
        result["opponent_hp"] = duel.opponent_hp
        result["round_number"] = duel.round_number

        if duel.challenger_hp <= 0 or duel.opponent_hp <= 0:
            duel.status = Duel.STATUS_FINISHED
            duel.winner_id = duel.challenger_id if duel.opponent_hp <= 0 else duel.opponent_id
            result["finished"] = True
            result["winner_id"] = duel.winner_id
            _notify_result(duel)
        else:
            _start_round(duel)
            result["next_prompt"] = duel.current_prompt
            result["next_round_number"] = duel.round_number

        db.session.commit()
        return result


def forfeit(duel_id: int, user_id: int) -> Duel:
    duel = Duel.query.filter_by(id=duel_id, status=Duel.STATUS_ACTIVE).first()
    if duel is None:
        raise DuelError("Duelo não encontrado ou já encerrado.")
    if user_id not in (duel.challenger_id, duel.opponent_id):
        raise DuelError("Você não faz parte deste duelo.")

    duel.status = Duel.STATUS_FINISHED
    duel.winner_id = duel.opponent_of(user_id)
    if user_id == duel.challenger_id:
        duel.challenger_hp = 0
    else:
        duel.opponent_hp = 0
    _notify_result(duel)
    db.session.commit()
    return duel


def _notify_result(duel: Duel) -> None:
    for participant_id in (duel.challenger_id, duel.opponent_id):
        db.session.add(Notification(
            user_id=participant_id,
            type="duel_result",
            payload={
                "duel_id": duel.id,
                "won": participant_id == duel.winner_id,
                "opponent_id": duel.opponent_of(participant_id),
            },
        ))


def list_pending_challenges(user_id: int) -> list[Duel]:
    return (
        Duel.query.filter_by(opponent_id=user_id, status=Duel.STATUS_PENDING)
        .order_by(Duel.created_at.desc())
        .all()
    )
