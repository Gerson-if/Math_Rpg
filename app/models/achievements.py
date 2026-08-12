from datetime import datetime

from app.extensions import db
from app.models.base import TimestampMixin


class Achievement(db.Model, TimestampMixin):
    """Catalog entry — new achievements are added via the database, not
    code, per the spec."""

    __tablename__ = "achievements"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(60), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    icon_key = db.Column(db.String(120), nullable=True)  # static/images/achievements
    # Declarative criteria, e.g. {"type": "attempts_correct_total", "value": 100}
    criteria = db.Column(db.JSON, nullable=False, default=dict)


class UserAchievement(db.Model):
    __tablename__ = "user_achievements"
    __table_args__ = (
        db.UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    achievement_id = db.Column(db.Integer, db.ForeignKey("achievements.id"), nullable=False)
    unlocked_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="achievements")
    achievement = db.relationship("Achievement")
