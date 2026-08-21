from app.extensions import db
from app.models import User, Subject, Topic, MissedFact
from app.services import recall_service


def _make_user(email="learner@example.com"):
    user = User(email=email, username=email.split("@")[0])
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.flush()
    return user


def _make_topic(slug="tabuada-do-7"):
    subject = Subject.query.filter_by(slug="tabuada").first()
    if subject is None:
        subject = Subject(slug="tabuada", name="Tabuada", order=0)
        db.session.add(subject)
        db.session.flush()
    topic = Topic(slug=slug, name=slug, subject_id=subject.id, order=0, base_difficulty=1)
    db.session.add(topic)
    db.session.flush()
    return topic


def test_record_result_creates_a_row_on_a_miss(app, db):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()

        recall_service.record_result(user.id, topic.id, "7x8", is_correct=False)
        db.session.commit()

        row = MissedFact.query.filter_by(user_id=user.id, topic_id=topic.id, fingerprint="7x8").first()
        assert row is not None
        assert row.miss_count == 1
        assert row.correct_streak == 0


def test_record_result_does_nothing_without_a_fingerprint(app, db):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()

        recall_service.record_result(user.id, topic.id, None, is_correct=False)
        db.session.commit()

        assert MissedFact.query.count() == 0


def test_record_result_ignores_a_correct_answer_for_a_fact_never_missed(app, db):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()

        recall_service.record_result(user.id, topic.id, "7x8", is_correct=True)
        db.session.commit()

        # A correct answer to something that was never a tracked miss
        # shouldn't create a row — there's nothing to "resolve".
        assert MissedFact.query.count() == 0


def test_record_result_increments_miss_count_on_repeated_misses(app, db):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()

        recall_service.record_result(user.id, topic.id, "7x8", is_correct=False)
        db.session.commit()
        recall_service.record_result(user.id, topic.id, "7x8", is_correct=False)
        db.session.commit()

        row = MissedFact.query.filter_by(user_id=user.id, topic_id=topic.id, fingerprint="7x8").first()
        assert row.miss_count == 2


def test_record_result_resolves_the_fact_after_enough_correct_answers_in_a_row(app, db):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()

        recall_service.record_result(user.id, topic.id, "7x8", is_correct=False)
        db.session.commit()

        for _ in range(recall_service.RESOLVE_STREAK):
            recall_service.record_result(user.id, topic.id, "7x8", is_correct=True)
            db.session.commit()

        assert MissedFact.query.filter_by(user_id=user.id, topic_id=topic.id, fingerprint="7x8").first() is None


def test_record_result_a_wrong_answer_mid_streak_resets_the_correct_streak(app, db):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()

        recall_service.record_result(user.id, topic.id, "7x8", is_correct=False)
        db.session.commit()
        recall_service.record_result(user.id, topic.id, "7x8", is_correct=True)
        db.session.commit()
        recall_service.record_result(user.id, topic.id, "7x8", is_correct=False)
        db.session.commit()

        row = MissedFact.query.filter_by(user_id=user.id, topic_id=topic.id, fingerprint="7x8").first()
        assert row is not None
        assert row.correct_streak == 0
        assert row.miss_count == 2


def test_due_fingerprint_is_none_with_no_missed_facts(app, db, monkeypatch):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()
        monkeypatch.setattr(recall_service.random, "random", lambda: 0.0)  # always "review" if anything's due

        assert recall_service.due_fingerprint(user.id, topic.id) is None


def test_due_fingerprint_returns_a_tracked_fact_when_the_roll_favors_review(app, db, monkeypatch):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()
        recall_service.record_result(user.id, topic.id, "7x8", is_correct=False)
        db.session.commit()

        monkeypatch.setattr(recall_service.random, "random", lambda: 0.0)
        assert recall_service.due_fingerprint(user.id, topic.id) == "7x8"


def test_due_fingerprint_returns_none_when_the_roll_favors_a_fresh_question(app, db, monkeypatch):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()
        recall_service.record_result(user.id, topic.id, "7x8", is_correct=False)
        db.session.commit()

        monkeypatch.setattr(recall_service.random, "random", lambda: 0.99)  # above DUE_BIAS_CHANCE
        assert recall_service.due_fingerprint(user.id, topic.id) is None


def test_due_fingerprint_is_scoped_to_the_right_user_and_topic(app, db, monkeypatch):
    with app.app_context():
        user_a = _make_user("a@example.com")
        user_b = _make_user("b@example.com")
        topic = _make_topic()
        other_topic = _make_topic("tabuada-do-9")

        recall_service.record_result(user_a.id, topic.id, "7x8", is_correct=False)
        db.session.commit()

        monkeypatch.setattr(recall_service.random, "random", lambda: 0.0)
        assert recall_service.due_fingerprint(user_b.id, topic.id) is None
        assert recall_service.due_fingerprint(user_a.id, other_topic.id) is None
        assert recall_service.due_fingerprint(user_a.id, topic.id) == "7x8"
