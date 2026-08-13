"""Lightweight co-op: invite an accepted friend to practice a topic
alongside you. This is deliberately NOT a synced multiplayer battle — the
app has no realtime transport (no WebSocket/SSE layer), so building a
shared, live HP bar over two independent HTTP sessions would mean either
faking it (dishonest — one player's screen showing "damage" the other
didn't actually cause) or a much bigger infrastructure project.

What this *does* give: your ally shows up next to your hero on the battle
screen for the invite's window, and both of you get a small, real XP bonus
while you're both actually practicing the same topic in that window —
verified server-side via this table, not cosmetic.
"""
from datetime import datetime, timedelta

from app.extensions import db
from app.models import DungeonInvite, Topic, User

INVITE_WINDOW_MINUTES = 30
COOP_BONUS_XP = 5


class DungeonError(Exception):
    pass


def send_invite(from_user_id: int, to_user_id: int, topic_id: int) -> DungeonInvite:
    if from_user_id == to_user_id:
        raise DungeonError("Você não pode convidar a si mesmo para uma masmorra.")
    topic = Topic.query.get(topic_id)
    if topic is None:
        raise DungeonError("Tópico não encontrado.")
    invite = DungeonInvite(from_user_id=from_user_id, to_user_id=to_user_id, topic_id=topic_id)
    db.session.add(invite)
    db.session.commit()
    return invite


def respond(invite_id: int, to_user_id: int, accept: bool) -> DungeonInvite:
    invite = DungeonInvite.query.filter_by(
        id=invite_id, to_user_id=to_user_id, status=DungeonInvite.STATUS_PENDING,
    ).first()
    if invite is None:
        raise DungeonError("Convite não encontrado (ou já respondido).")
    if accept:
        invite.status = DungeonInvite.STATUS_ACCEPTED
        invite.expires_at = datetime.utcnow() + timedelta(minutes=INVITE_WINDOW_MINUTES)
    else:
        invite.status = DungeonInvite.STATUS_DECLINED
    db.session.commit()
    return invite


def list_incoming(user_id: int) -> list[DungeonInvite]:
    return DungeonInvite.query.filter_by(
        to_user_id=user_id, status=DungeonInvite.STATUS_PENDING,
    ).all()


def active_ally(user_id: int, topic_id: int) -> User | None:
    """The other player, if there's a live accepted invite between
    user_id and someone else for this exact topic right now."""
    now = datetime.utcnow()
    invite = DungeonInvite.query.filter(
        DungeonInvite.topic_id == topic_id,
        DungeonInvite.status == DungeonInvite.STATUS_ACCEPTED,
        DungeonInvite.expires_at.isnot(None),
        DungeonInvite.expires_at > now,
        db.or_(DungeonInvite.from_user_id == user_id, DungeonInvite.to_user_id == user_id),
    ).order_by(DungeonInvite.expires_at.desc()).first()
    if invite is None:
        return None
    ally_id = invite.to_user_id if invite.from_user_id == user_id else invite.from_user_id
    return User.query.get(ally_id)
