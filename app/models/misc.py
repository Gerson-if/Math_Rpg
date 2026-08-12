from app.extensions import db
from app.models.base import TimestampMixin


class Notification(db.Model, TimestampMixin):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    type = db.Column(db.String(40), nullable=False)  # achievement, review_due, rank_up, ...
    payload = db.Column(db.JSON, default=dict)
    is_read = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship("User")


class StudySession(db.Model, TimestampMixin):
    """A bounded block of practice (open the app, answer some questions,
    close it). This is the 'sessions' entity from the spec — named
    StudySession to avoid clashing with Flask's own session concept, which
    handles login state separately.
    """

    __tablename__ = "study_sessions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    started_at = db.Column(db.DateTime, nullable=False)
    ended_at = db.Column(db.DateTime, nullable=True)
    xp_earned = db.Column(db.Integer, default=0, nullable=False)
    questions_answered = db.Column(db.Integer, default=0, nullable=False)
    correct_count = db.Column(db.Integer, default=0, nullable=False)

    user = db.relationship("User")
