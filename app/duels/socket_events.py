"""Socket.IO transport for real-time duels. Every handler here does the
same two things: check the connected user is actually allowed near this
duel, then delegate to app.services.duel_service for anything that
changes state. No game logic lives in this file — if a client could win
a round or deal damage by sending the "right" socket message without the
server re-deriving that outcome itself, that would be exactly the kind
of client-trusted result this app avoids everywhere else (see
answer_question in app/mathematics/routes.py for the same principle in
the solo battle).

Room name = Duel.room_code, not the raw numeric id, so a room can't be
casually guessed/joined from watching id sequences in the URL — though
join_duel() below re-checks real participancy regardless.
"""
from flask import request
from flask_login import current_user
from flask_socketio import emit, join_room, leave_room

from app.extensions import socketio
from app.models import Duel
from app.services import duel_service

# emote key -> the only values a client can ever trigger; never pass the
# client's raw string straight into the broadcast.
ALLOWED_EMOTES = {"wave", "laugh", "gg", "fire", "sweat", "angry"}


def _duel_or_none(duel_id):
    if not current_user.is_authenticated:
        return None
    duel = Duel.query.filter_by(id=duel_id).first()
    if duel is None or current_user.id not in (duel.challenger_id, duel.opponent_id):
        return None
    return duel


@socketio.on("join_duel")
def handle_join(data):
    duel = _duel_or_none((data or {}).get("duel_id"))
    if duel is None:
        return {"error": "Duelo não encontrado."}

    join_room(duel.room_code)
    return {
        "prompt": duel.current_prompt,
        "round_number": duel.round_number,
        "challenger_hp": duel.challenger_hp,
        "opponent_hp": duel.opponent_hp,
        "status": duel.status,
        "you_are": "challenger" if current_user.id == duel.challenger_id else "opponent",
    }


@socketio.on("leave_duel")
def handle_leave(data):
    duel = _duel_or_none((data or {}).get("duel_id"))
    if duel is None:
        return
    leave_room(duel.room_code)


@socketio.on("submit_answer")
def handle_submit_answer(data):
    data = data or {}
    duel = _duel_or_none(data.get("duel_id"))
    if duel is None:
        return {"error": "Duelo não encontrado."}

    try:
        result = duel_service.submit_answer(duel.id, current_user.id, str(data.get("answer", "")))
    except duel_service.DuelError as exc:
        return {"error": str(exc)}

    # Broadcast to the whole room (both players, including the one who
    # just answered) so the UI stays a single source of truth driven by
    # server events rather than the submitter also locally guessing at
    # its own result.
    emit("round_result", result, room=duel.room_code)
    return {"ok": True}


@socketio.on("forfeit_duel")
def handle_forfeit(data):
    duel = _duel_or_none((data or {}).get("duel_id"))
    if duel is None:
        return {"error": "Duelo não encontrado."}
    try:
        duel_service.forfeit(duel.id, current_user.id)
    except duel_service.DuelError as exc:
        return {"error": str(exc)}

    emit("duel_ended", {
        "duel_id": duel.id, "winner_id": duel.winner_id, "forfeited_by": current_user.id,
    }, room=duel.room_code)
    return {"ok": True}


@socketio.on("send_emote")
def handle_emote(data):
    data = data or {}
    duel = _duel_or_none(data.get("duel_id"))
    if duel is None:
        return
    emote = data.get("emote")
    if emote not in ALLOWED_EMOTES:
        return
    emit("emote_received", {"emote": emote, "from_user_id": current_user.id}, room=duel.room_code, include_self=True)
