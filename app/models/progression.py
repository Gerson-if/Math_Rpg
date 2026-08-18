from app.extensions import db
from app.models.base import TimestampMixin


class Level(db.Model, TimestampMixin):
    """XP-based level catalog (not per user — a shared ladder)."""

    __tablename__ = "levels"

    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String(60), nullable=True)
    xp_required = db.Column(db.Integer, nullable=False)


class Rank(db.Model, TimestampMixin):
    """Cosmetic tier (Iniciante, Bronze, Prata, ...). Names/art are
    placeholders until the full art pack defines the final identity."""

    __tablename__ = "ranks"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(40), unique=True, nullable=False)
    name = db.Column(db.String(60), nullable=False)
    order = db.Column(db.Integer, nullable=False)
    min_level = db.Column(db.Integer, nullable=False, default=1)
    icon_key = db.Column(db.String(120), nullable=True)  # path under static/images/ranks


class PlayerStats(db.Model, TimestampMixin):
    """The single source of truth for "how far has this player gotten" —
    XP, current level/rank, streaks. Mirrors User 1:1 on purpose, kept
    separate so auth stays lean and progression logic stays in one place.
    """

    __tablename__ = "player_stats"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    xp = db.Column(db.Integer, default=0, nullable=False)
    # Earned only by selling unwanted loot (see loot_service.sell) — no
    # shop to spend it in yet, so it's purely a running total for now.
    gold = db.Column(db.Integer, default=0, nullable=False)
    level_id = db.Column(db.Integer, db.ForeignKey("levels.id"), nullable=True)
    rank_id = db.Column(db.Integer, db.ForeignKey("ranks.id"), nullable=True)
    current_streak = db.Column(db.Integer, default=0, nullable=False)
    best_streak = db.Column(db.Integer, default=0, nullable=False)
    total_correct = db.Column(db.Integer, default=0, nullable=False)
    total_wrong = db.Column(db.Integer, default=0, nullable=False)
    last_active_at = db.Column(db.DateTime, nullable=True)
    # Timestamp of the last time this user opened the global chat — the
    # "new messages" badge in the navbar counts anything posted after this
    # (by someone else) as unread. Null just means "never opened it yet".
    last_seen_chat_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", back_populates="stats")
    level = db.relationship("Level")
    rank = db.relationship("Rank")


class Mastery(db.Model, TimestampMixin):
    """Per (user, topic) mastery — deliberately separate from XP. This is
    what review scheduling reads from, not the XP total.
    """

    __tablename__ = "mastery"
    __table_args__ = (db.UniqueConstraint("user_id", "topic_id", name="uq_mastery_user_topic"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=False, index=True)

    mastery_score = db.Column(db.Float, default=0.0, nullable=False)  # 0..1
    correct_count = db.Column(db.Integer, default=0, nullable=False)
    wrong_count = db.Column(db.Integer, default=0, nullable=False)
    avg_response_time_ms = db.Column(db.Integer, default=0, nullable=False)
    current_streak = db.Column(db.Integer, default=0, nullable=False)
    last_practiced_at = db.Column(db.DateTime, nullable=True)
    needs_review = db.Column(db.Boolean, default=False, nullable=False)

    user = db.relationship("User", back_populates="mastery_records")
    topic = db.relationship("Topic", back_populates="mastery_records")
