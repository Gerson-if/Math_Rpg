from app.extensions import db
from app.models.base import TimestampMixin


class LeaderboardEntry(db.Model, TimestampMixin):
    """A generated snapshot row rather than a live query, so leaderboards
    stay cheap to read and can be recomputed on a schedule (e.g. nightly
    for weekly/monthly boards).
    """

    __tablename__ = "leaderboards"
    __table_args__ = (
        db.Index("ix_leaderboard_scope_period", "scope", "period_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    # global | weekly | monthly | topic | mastery | streak
    scope = db.Column(db.String(20), nullable=False)
    # e.g. "2026-W33", "2026-08", or a topic slug when scope == "topic"
    period_key = db.Column(db.String(40), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    score = db.Column(db.Float, nullable=False)
    position = db.Column(db.Integer, nullable=False)

    user = db.relationship("User")
