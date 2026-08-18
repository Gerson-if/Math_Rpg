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


class ChatReport(db.Model, TimestampMixin):
    """One row per denúncia — an audit trail of who reported what, and
    what the automatic content analysis decided (see
    chat_service._analyze_violation). content_snapshot is copied at
    report time rather than joined live off ChatMessage.content, so the
    record stays meaningful even if the message is later edited/removed.
    reported_user_id is denormalized from ChatMessage.user_id for the
    same reason, plus so a lookup of "reports against me" never needs to
    join through the message at all."""

    __tablename__ = "chat_reports"
    __table_args__ = (
        db.UniqueConstraint("message_id", "reporter_id", name="uq_chat_report_message_reporter"),
    )

    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey("chat_messages.id"), nullable=False, index=True)
    reporter_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    reported_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    content_snapshot = db.Column(db.String(500), nullable=False)
    is_violation = db.Column(db.Boolean, nullable=False)
    reason = db.Column(db.String(200), nullable=False)

    message = db.relationship("ChatMessage")
    reporter = db.relationship("User", foreign_keys=[reporter_id])
    reported_user = db.relationship("User", foreign_keys=[reported_user_id])
