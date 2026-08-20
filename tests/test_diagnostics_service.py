from app.extensions import db
from app.models import User, Subject, Topic, Mastery
from app.services import diagnostics_service


def _make_user(email="learner@example.com"):
    user = User(email=email, username=email.split("@")[0])
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.flush()
    return user


def _make_topic(slug, subject, order):
    topic = Topic(slug=slug, name=slug, subject_id=subject.id, order=order, base_difficulty=1)
    db.session.add(topic)
    db.session.flush()
    return topic


def _set_mastery(user, topic, score):
    db.session.add(Mastery(user_id=user.id, topic_id=topic.id, mastery_score=score, correct_count=1, wrong_count=0))
    db.session.commit()


def test_area_report_treats_an_untouched_topic_as_zero_mastery(app, db):
    with app.app_context():
        user = _make_user()
        subject = Subject(slug="operacoes-fundamentais", name="Operações Fundamentais", order=0)
        db.session.add(subject)
        db.session.flush()
        _make_topic("adicao", subject, 0)  # never attempted
        subtracao = _make_topic("subtracao", subject, 1)
        _set_mastery(user, subtracao, score=1.0)

        report = diagnostics_service.area_report(user.id)
        area = next(r for r in report if r["slug"] == "operacoes-aritmeticas")
        # (0.0 + 1.0) / 2 topics = 50%
        assert area["mastery_pct"] == 50
        assert area["topics_practiced"] == 1
        assert area["topics_total"] == 2
        assert area["weakest_topic"].slug == "adicao"


def test_area_report_sorts_weakest_area_first(app, db):
    with app.app_context():
        user = _make_user()
        strong_subject = Subject(slug="tabuada", name="Tabuada", order=0)
        weak_subject = Subject(slug="fracoes", name="Frações", order=1)
        db.session.add_all([strong_subject, weak_subject])
        db.session.flush()

        strong_topic = _make_topic("tabuada-do-1", strong_subject, 0)
        weak_topic = _make_topic("fracoes-basicas", weak_subject, 0)
        _set_mastery(user, strong_topic, score=0.9)
        _set_mastery(user, weak_topic, score=0.1)

        report = diagnostics_service.area_report(user.id)
        assert report[0]["slug"] == "fracoes"
        assert report[0]["mastery_pct"] == 10
        assert report[-1]["mastery_pct"] >= report[0]["mastery_pct"]


def test_area_report_skips_topics_with_no_mapped_math_area(app, db):
    """A topic slug not present in math_areas.TOPIC_AREAS (e.g. curriculum
    content added ahead of updating that map) is quietly excluded rather
    than crashing the report."""
    with app.app_context():
        user = _make_user()
        subject = Subject(slug="mystery-subject", name="Mystery", order=0)
        db.session.add(subject)
        db.session.flush()
        _make_topic("not-a-mapped-slug", subject, 0)

        report = diagnostics_service.area_report(user.id)
        assert all(row["slug"] != "not-a-mapped-slug" for row in report)


def test_area_report_is_empty_when_no_topics_exist(app, db):
    with app.app_context():
        user = _make_user()
        assert diagnostics_service.area_report(user.id) == []
