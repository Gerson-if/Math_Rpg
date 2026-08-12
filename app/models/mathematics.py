from app.extensions import db
from app.models.base import TimestampMixin


class Subject(db.Model, TimestampMixin):
    """Top-level curriculum branch, e.g. 'Fundamentos', 'Frações'."""

    __tablename__ = "subjects"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(60), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    order = db.Column(db.Integer, default=0, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    icon_key = db.Column(db.String(120), nullable=True)  # path under static/images/icons

    topics = db.relationship(
        "Topic", back_populates="subject", cascade="all, delete-orphan",
        order_by="Topic.order",
    )


class Topic(db.Model, TimestampMixin):
    """A practicable unit inside a subject, e.g. 'Tabuada do 7'.

    Mastery is tracked per (user, topic) — see Mastery model.
    """

    __tablename__ = "topics"

    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)
    order = db.Column(db.Integer, default=0, nullable=False)
    base_difficulty = db.Column(db.Integer, default=1, nullable=False)  # 1..5
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    # Slugs of topics that should be reasonably solid before this one
    # unlocks. Kept as a simple list rather than a rigid tree so the
    # curriculum can be reorganized without a schema change.
    prerequisite_slugs = db.Column(db.JSON, default=list)

    subject = db.relationship("Subject", back_populates="topics")
    questions = db.relationship(
        "Question", back_populates="topic", cascade="all, delete-orphan"
    )
    mastery_records = db.relationship("Mastery", back_populates="topic")
    attempts = db.relationship("Attempt", back_populates="topic")


class Question(db.Model, TimestampMixin):
    """A single exercise.

    Simple arithmetic (tabuada, four operations) is generated on the fly by
    the mathematics engine and doesn't need a row here. This table exists
    for topics where questions are authored/curated (word problems, mixed
    exercises) or where a generated question is worth caching for reuse.
    """

    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=False)
    difficulty = db.Column(db.Integer, nullable=False, default=1)  # 1..5
    prompt = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.String(120), nullable=False)
    # Free-form extra data: distractors, generation params, explanation text.
    meta = db.Column(db.JSON, default=dict)
    is_generated = db.Column(db.Boolean, default=True, nullable=False)

    topic = db.relationship("Topic", back_populates="questions")


class Attempt(db.Model, TimestampMixin):
    """One answered question. This is the raw signal that mastery, XP and
    streaks are all computed from."""

    __tablename__ = "attempts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=False, index=True)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=True)
    difficulty = db.Column(db.Integer, nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False)
    response_time_ms = db.Column(db.Integer, nullable=False)
    study_session_id = db.Column(
        db.Integer, db.ForeignKey("study_sessions.id"), nullable=True
    )

    user = db.relationship("User", back_populates="attempts")
    topic = db.relationship("Topic", back_populates="attempts")
