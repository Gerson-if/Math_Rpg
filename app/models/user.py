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
    avatar_key = db.Column(db.String(120), default="characters/idle")
    title = db.Column(db.String(60), nullable=True)  # earned via achievements
    bio = db.Column(db.String(280), nullable=True)

    user = db.relationship("User", back_populates="profile")
