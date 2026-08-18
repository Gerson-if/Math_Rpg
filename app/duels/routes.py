"""Real-time duel HTTP surface: the challenge flow (create/accept/decline
— plain request/response, same as every other invite in this app) and
the arena page itself. Once inside the arena, everything that actually
happens during the fight goes over Socket.IO (see socket_events.py) —
this blueprint never touches round/HP state directly.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user

from app.extensions import limiter
from app.models import Duel
from app.services import duel_service, friends_service

duels_bp = Blueprint("duels", __name__, url_prefix="/duelo")


@duels_bp.route("/desafiar", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def challenge():
    opponent_id = request.form.get("friend_id", type=int)
    topic_id = request.form.get("topic_id", type=int)
    if not opponent_id or not topic_id or not friends_service.are_friends(current_user.id, opponent_id):
        flash("Desafie apenas amigos de verdade para um duelo.", "error")
        return redirect(url_for("friends.index"))
    try:
        duel = duel_service.create_challenge(current_user.id, opponent_id, topic_id)
        flash(f"Desafio de duelo enviado para {duel.opponent.username}!", "info")
    except duel_service.DuelError as exc:
        flash(str(exc), "error")
    return redirect(url_for("friends.index"))


@duels_bp.route("/<int:duel_id>/aceitar", methods=["POST"])
@login_required
def accept(duel_id):
    try:
        duel_service.respond_to_challenge(duel_id, current_user.id, accept=True)
        return redirect(url_for("duels.arena", duel_id=duel_id))
    except duel_service.DuelError as exc:
        flash(str(exc), "error")
        return redirect(url_for("friends.index"))


@duels_bp.route("/<int:duel_id>/recusar", methods=["POST"])
@login_required
def decline(duel_id):
    try:
        duel_service.respond_to_challenge(duel_id, current_user.id, accept=False)
    except duel_service.DuelError as exc:
        flash(str(exc), "error")
    return redirect(url_for("friends.index"))


@duels_bp.route("/<int:duel_id>")
@login_required
def arena(duel_id):
    duel = Duel.query.filter_by(id=duel_id).first_or_404()
    if current_user.id not in (duel.challenger_id, duel.opponent_id):
        abort(404)
    if duel.status == Duel.STATUS_PENDING:
        flash("Esse duelo ainda não foi aceito.", "warning")
        return redirect(url_for("friends.index"))

    opponent = duel.opponent if current_user.id == duel.challenger_id else duel.challenger
    return render_template(
        "duels/arena.html",
        duel=duel,
        opponent=opponent,
        is_challenger=(current_user.id == duel.challenger_id),
    )
