from datetime import datetime, timedelta

from app.extensions import db
from app.models import (
    User,
    Subject,
    Topic,
    Attempt,
    Level,
    Rank,
    Achievement,
    PlayerStats,
    Mastery,
)
from app.services import progression_service


def _make_user():
    user = User(email="p@example.com", username="p")
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.flush()
    return user


def _make_topic(slug="tabuada-do-7"):
    subject = Subject(slug="tabuada", name="Tabuada", order=0)
    db.session.add(subject)
    db.session.flush()
    topic = Topic(slug=slug, name="Tabuada do 7", subject_id=subject.id, order=0, base_difficulty=1)
    db.session.add(topic)
    db.session.flush()
    return topic


def _seed_levels_and_ranks():
    for number in range(1, 6):
        db.session.add(Level(number=number, xp_required=int(50 * (number - 1) ** 1.4)))
    db.session.add(Rank(slug="iniciante", name="Iniciante", order=1, min_level=1))
    db.session.add(Rank(slug="bronze", name="Bronze", order=2, min_level=3))
    db.session.commit()


def _make_attempt(user, topic, *, correct, difficulty=1, response_time_ms=2000):
    attempt = Attempt(
        user_id=user.id,
        topic_id=topic.id,
        difficulty=difficulty,
        is_correct=correct,
        response_time_ms=response_time_ms,
    )
    db.session.add(attempt)
    db.session.flush()
    return attempt


def test_correct_answer_awards_xp(app, db):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()
        _seed_levels_and_ranks()

        attempt = _make_attempt(user, topic, correct=True, difficulty=3)
        result = progression_service.process_attempt(attempt)

        assert result["xp_awarded"] == 20  # difficulty 3 -> 20 XP
        stats = PlayerStats.query.filter_by(user_id=user.id).first()
        assert stats.xp == 20
        assert stats.total_correct == 1
        assert stats.current_streak == 1


def test_wrong_answer_awards_no_xp_and_resets_streak(app, db):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()
        _seed_levels_and_ranks()

        progression_service.process_attempt(_make_attempt(user, topic, correct=True))
        result = progression_service.process_attempt(_make_attempt(user, topic, correct=False))

        assert result["xp_awarded"] == 0
        stats = PlayerStats.query.filter_by(user_id=user.id).first()
        assert stats.current_streak == 0
        assert stats.total_wrong == 1


def test_level_up_is_detected(app, db):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()
        _seed_levels_and_ranks()

        leveled_up_at_least_once = False
        for _ in range(20):
            result = progression_service.process_attempt(
                _make_attempt(user, topic, correct=True, difficulty=5)
            )
            if result["leveled_up"]:
                leveled_up_at_least_once = True

        assert leveled_up_at_least_once
        stats = PlayerStats.query.filter_by(user_id=user.id).first()
        assert stats.level.number > 1


def test_mastery_score_increases_with_repeated_correct_answers(app, db):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()
        _seed_levels_and_ranks()

        for _ in range(10):
            progression_service.process_attempt(_make_attempt(user, topic, correct=True))

        mastery = Mastery.query.filter_by(user_id=user.id, topic_id=topic.id).first()
        assert mastery.mastery_score > 0.5
        assert mastery.correct_count == 10


def test_needs_review_flag_after_poor_performance(app, db):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()
        _seed_levels_and_ranks()

        for _ in range(6):
            progression_service.process_attempt(_make_attempt(user, topic, correct=False))

        mastery = Mastery.query.filter_by(user_id=user.id, topic_id=topic.id).first()
        assert mastery.needs_review is True


def test_retention_decay_reduces_mastery_after_a_long_gap(app, db):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()
        _seed_levels_and_ranks()

        for _ in range(10):
            progression_service.process_attempt(_make_attempt(user, topic, correct=True))

        mastery = Mastery.query.filter_by(user_id=user.id, topic_id=topic.id).first()
        score_before_gap = mastery.mastery_score
        mastery.last_practiced_at = datetime.utcnow() - timedelta(days=30)
        db.session.commit()

        progression_service.process_attempt(_make_attempt(user, topic, correct=True))
        mastery = Mastery.query.filter_by(user_id=user.id, topic_id=topic.id).first()

        # The decay should have pulled it down before this attempt's own
        # (positive) update was applied, so it shouldn't simply keep
        # climbing at the same pace as an uninterrupted streak would.
        assert mastery.mastery_score <= 1.0
        assert score_before_gap > 0


def test_achievement_unlocks_once_threshold_is_met(app, db):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()
        _seed_levels_and_ranks()
        db.session.add(Achievement(
            code="primeiro_acerto",
            name="Primeiro Acerto",
            description="Responda sua primeira questão corretamente.",
            criteria={"type": "attempts_correct_total", "value": 1},
        ))
        db.session.commit()

        result = progression_service.process_attempt(_make_attempt(user, topic, correct=True))
        assert len(result["new_achievements"]) == 1
        assert result["new_achievements"][0].code == "primeiro_acerto"

        # Doesn't unlock a second time.
        result2 = progression_service.process_attempt(_make_attempt(user, topic, correct=True))
        assert result2["new_achievements"] == []


def test_achievement_unlocks_by_correct_answers_in_a_specific_subject(app, db):
    """Fase 7: achievements scoped to one of the new subjects (e.g.
    'Mestre da Potenciação') must only count attempts under that subject,
    not correct answers from any topic."""
    with app.app_context():
        user = _make_user()
        _seed_levels_and_ranks()

        potenciacao = Subject(slug="potenciacao", name="Potenciação", order=1)
        db.session.add(potenciacao)
        db.session.flush()
        power_topic = Topic(
            slug="potencias-basicas", name="Potências básicas",
            subject_id=potenciacao.id, order=0, base_difficulty=1,
        )
        other_topic = _make_topic()  # unrelated "tabuada" subject
        db.session.add(power_topic)
        db.session.flush()

        db.session.add(Achievement(
            code="dominou_potenciacao",
            name="Mestre da Potenciação",
            description="Acerte 2 questões de Potenciação.",
            criteria={"type": "attempts_correct_in_subject", "subject": "potenciacao", "value": 2},
        ))
        db.session.commit()

        # Correct answers in an unrelated subject don't count toward it.
        result = progression_service.process_attempt(_make_attempt(user, other_topic, correct=True))
        assert result["new_achievements"] == []

        result2 = progression_service.process_attempt(_make_attempt(user, power_topic, correct=True))
        assert result2["new_achievements"] == []  # only 1 of 2 required so far

        result3 = progression_service.process_attempt(_make_attempt(user, power_topic, correct=True))
        assert [a.code for a in result3["new_achievements"]] == ["dominou_potenciacao"]
