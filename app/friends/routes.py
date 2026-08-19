"""Friends + dungeon co-op invites. Two related-but-separate concerns
share one blueprint/page (friends/index.html) because in practice you
only ever invite someone to a dungeon from the friends list — there's no
scenario where a user visits one without the other."""
from urllib.parse import urlparse

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.extensions import limiter
from app.models import Subject
from app.services import friends_service, dungeon_service, duel_service

friends_bp = Blueprint("friends", __name__, url_prefix="/amigos")


def _redirect_back(default_endpoint):
    # Lets a friend-request form on some OTHER page (a public profile,
    # say) send the player back to where they were instead of always
    # dumping them on /amigos — only trusts request.referrer when it's
    # same-origin, so this can't be turned into an open redirect.
    referrer = request.referrer
    if referrer and urlparse(referrer).netloc in ("", urlparse(request.host_url).netloc):
        return redirect(referrer)
    return redirect(url_for(default_endpoint))


@friends_bp.route("/")
@login_required
def index():
    subjects = Subject.query.filter_by(is_active=True).order_by(Subject.order).all()
    return render_template(
        "friends/index.html",
        friend_rows=friends_service.list_friend_rows(current_user.id),
        incoming=friends_service.list_incoming_requests(current_user.id),
        outgoing=friends_service.list_outgoing_requests(current_user.id),
        dungeon_invites=dungeon_service.list_incoming(current_user.id),
        duel_challenges=duel_service.list_pending_challenges(current_user.id),
        subjects=subjects,
    )


@friends_bp.route("/solicitar", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def send_request():
    username = request.form.get("username", "")
    try:
        friendship = friends_service.send_request(current_user.id, username)
        flash(f"Convite de amizade enviado para {friendship.addressee.username}.", "info")
    except friends_service.FriendError as exc:
        flash(str(exc), "error")
    return _redirect_back("friends.index")


@friends_bp.route("/<int:friendship_id>/aceitar", methods=["POST"])
@login_required
def accept_request(friendship_id):
    try:
        friendship = friends_service.respond(friendship_id, current_user.id, accept=True)
        flash(f"Você agora é amigo de {friendship.requester.username}!", "info")
    except friends_service.FriendError as exc:
        flash(str(exc), "error")
    return redirect(url_for("friends.index"))


@friends_bp.route("/<int:friendship_id>/recusar", methods=["POST"])
@login_required
def decline_request(friendship_id):
    try:
        friends_service.respond(friendship_id, current_user.id, accept=False)
    except friends_service.FriendError as exc:
        flash(str(exc), "error")
    return redirect(url_for("friends.index"))


@friends_bp.route("/<int:friendship_id>/remover", methods=["POST"])
@login_required
def remove_friend(friendship_id):
    try:
        friends_service.remove(friendship_id, current_user.id)
    except friends_service.FriendError as exc:
        flash(str(exc), "error")
    return redirect(url_for("friends.index"))


@friends_bp.route("/masmorra/convidar", methods=["POST"])
@login_required
@limiter.limit("30 per hour")
def invite_to_dungeon():
    to_user_id = request.form.get("friend_id", type=int)
    topic_id = request.form.get("topic_id", type=int)
    if not to_user_id or not topic_id or not friends_service.are_friends(current_user.id, to_user_id):
        flash("Convide apenas amigos de verdade para a masmorra.", "error")
        return redirect(url_for("friends.index"))
    try:
        invite = dungeon_service.send_invite(current_user.id, to_user_id, topic_id)
        flash(f"Convite de masmorra enviado para {invite.to_user.username}.", "info")
    except dungeon_service.DungeonError as exc:
        flash(str(exc), "error")
    return redirect(url_for("friends.index"))


@friends_bp.route("/masmorra/<int:invite_id>/aceitar", methods=["POST"])
@login_required
def accept_dungeon_invite(invite_id):
    try:
        invite = dungeon_service.respond(invite_id, current_user.id, accept=True)
        flash(f"Você está ajudando {invite.from_user.username} em {invite.topic.name}!", "info")
        return redirect(url_for("mathematics.practice", topic_slug=invite.topic.slug))
    except dungeon_service.DungeonError as exc:
        flash(str(exc), "error")
        return redirect(url_for("friends.index"))


@friends_bp.route("/masmorra/<int:invite_id>/recusar", methods=["POST"])
@login_required
def decline_dungeon_invite(invite_id):
    try:
        dungeon_service.respond(invite_id, current_user.id, accept=False)
    except dungeon_service.DungeonError as exc:
        flash(str(exc), "error")
    return redirect(url_for("friends.index"))
