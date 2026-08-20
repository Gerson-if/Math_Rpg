from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db
from app.models.base import TimestampMixin


class User(db.Model, UserMixin, TimestampMixin):
    """Authentication identity. Everything about "who is playing" — display
    name, avatar, XP, rank — lives elsewhere so this table stays small and
    auth-only."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)

    profile = db.relationship(
        "Profile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    stats = db.relationship(
        "PlayerStats", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    mastery_records = db.relationship(
        "Mastery", back_populates="user", cascade="all, delete-orphan"
    )
    attempts = db.relationship(
        "Attempt", back_populates="user", cascade="all, delete-orphan"
    )
    achievements = db.relationship(
        "UserAchievement", back_populates="user", cascade="all, delete-orphan"
    )

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class Profile(db.Model, TimestampMixin):
    """Public-facing identity: display name, avatar, title, bio."""

    __tablename__ = "profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    display_name = db.Column(db.String(60), nullable=False)
    # Registration always sets this explicitly to a random pick from
    # AVATAR_CHOICES (see auth.routes.register) — this default is only a
    # safety net for any other path that might create a Profile without
    # specifying one. Must be a key avatar_icon's `valid` list recognizes
    # (app/templates/_macros.html), unlike the old "characters/idle"
    # placeholder this replaced, which silently made every profile that
    # never visited the editor render the exact same fallback icon.
    avatar_key = db.Column(db.String(120), default="fa-user-shield")
    title = db.Column(db.String(60), nullable=True)  # earned via achievements
    bio = db.Column(db.String(280), nullable=True)

    # Character class (see app/services/classes.py) — chosen freely the
    # first time (character_class stays None until then), then evolving
    # within that same family automatically as the player levels up (see
    # progression_service._update_class_tier). class_tier_claimed tracks
    # the highest ability/evolution tier reached — switching to a
    # *different* family costs gold (users.choose_class) and resets this
    # to the tier the player's current level already earns, not to 0.
    character_class = db.Column(db.String(20), nullable=True)
    class_tier_claimed = db.Column(db.Integer, default=-1, nullable=False)

    user = db.relationship("User", back_populates="profile")
