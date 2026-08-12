from app.extensions import db
from app.models.base import TimestampMixin


class ChatMessage(db.Model, TimestampMixin):
    """Room is a plain string ('global' by default) so private rooms,
    groups etc. can be added later without a schema change."""

    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    room = db.Column(db.String(60), default="global", nullable=False, index=True)
    content = db.Column(db.String(500), nullable=False)
    is_flagged = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship("User")
