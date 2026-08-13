from datetime import datetime

from app.extensions import db
from app.models.base import TimestampMixin


class Friendship(db.Model, TimestampMixin):
    """One row per requested friendship, directional (requester ->
    addressee) but symmetric once accepted — app/services/friends_service.py
    is the only place that should query this table, so "am I friends with
    X" logic lives in one spot instead of being re-derived per template."""

    __tablename__ = "friendships"
    __table_args__ = (
        db.UniqueConstraint("requester_id", "addressee_id", name="uq_friendship_pair"),
    )

    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"

    id = db.Column(db.Integer, primary_key=True)
    requester_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    addressee_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(db.String(20), nullable=False, default=STATUS_PENDING)

    requester = db.relationship("User", foreign_keys=[requester_id])
    addressee = db.relationship("User", foreign_keys=[addressee_id])


class DungeonInvite(db.Model, TimestampMixin):
    """A nudge to practice a topic together. Deliberately NOT a synced
    multiplayer battle — this app has no realtime transport, so "helping"
    means the ally shows up next to your hero on the battle screen and you
    both get a small, server-verified XP bonus while practicing the same
    topic inside the accepted window (see dungeon_service.active_ally)."""

    __tablename__ = "dungeon_invites"

    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"

    id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    to_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=STATUS_PENDING)
    expires_at = db.Column(db.DateTime, nullable=True)

    from_user = db.relationship("User", foreign_keys=[from_user_id])
    to_user = db.relationship("User", foreign_keys=[to_user_id])
    topic = db.relationship("Topic")

    def is_live(self, now: datetime | None = None) -> bool:
        now = now or datetime.utcnow()
        return self.status == self.STATUS_ACCEPTED and self.expires_at is not None and self.expires_at > now
