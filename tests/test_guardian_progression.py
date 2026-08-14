from app.extensions import db
from app.models import User, Subject, Topic
from app.services import guardians


def _make_subject_with_topics(slugs, subject_slug="tabuada"):
    subject = Subject(slug=subject_slug, name="Tabuada", order=0)
    db.session.add(subject)
    db.session.flush()
    topics = []
    for i, slug in enumerate(slugs):
        topic = Topic(slug=slug, name=slug.capitalize(), subject_id=subject.id, order=i, base_difficulty=1)
        db.session.add(topic)
        topics.append(topic)
    db.session.flush()
    return subject, topics


def test_for_topic_gives_the_real_guardian_only_to_the_subjects_last_topic(app, db):
    with app.app_context():
        subject, topics = _make_subject_with_topics(["a", "b", "c"])
        db.session.commit()

        real_guardian = guardians.for_subject("tabuada")

        first, is_final_first = guardians.for_topic(topics[0])
        last, is_final_last = guardians.for_topic(topics[-1])

        assert is_final_first is False
        assert first["name"] != real_guardian["name"]

        assert is_final_last is True
        assert last["name"] == real_guardian["name"]


def test_minion_shares_the_guardians_icon_and_color(app, db):
    with app.app_context():
        subject, topics = _make_subject_with_topics(["a", "b"])
        db.session.commit()

        real_guardian = guardians.for_subject("tabuada")
        minion, is_final = guardians.for_topic(topics[0])

        assert is_final is False
        assert minion["icon"] == real_guardian["icon"]
        assert minion["color"] == real_guardian["color"]
        assert minion["name"] != real_guardian["name"]


def test_a_subject_with_a_single_topic_treats_it_as_the_final_boss(app, db):
    with app.app_context():
        subject, topics = _make_subject_with_topics(["only"])
        db.session.commit()

        guardian, is_final = guardians.for_topic(topics[0])
        assert is_final is True
        assert guardian["name"] == guardians.for_subject("tabuada")["name"]


def test_every_seeded_subject_has_a_minion_name_or_a_sane_fallback():
    seeded_subjects = [
        "fundamentos", "tabuada", "operacoes-fundamentais", "potenciacao",
        "radiciacao", "fracoes", "numeros-decimais", "porcentagem", "algebra",
    ]
    for slug in seeded_subjects:
        assert slug in guardians.MINION_NAMES, f"missing minion name for {slug}"


def test_practice_route_shows_the_minion_for_a_non_final_topic(client, db, app):
    user = User(email="p@example.com", username="p")
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    client.post("/auth/login", data={"email": "p@example.com", "password": "senhaforte123"})

    with app.app_context():
        subject, topics = _make_subject_with_topics(["adicao", "subtracao"], subject_slug="operacoes-fundamentais")
        db.session.commit()

    real_guardian_name = guardians.for_subject("operacoes-fundamentais")["name"]
    # "Enfrentar X" (the battle button) is unambiguous, unlike a bare name
    # search — a CSS comment elsewhere on the page can legitimately
    # mention a guardian's name as an example without that being a bug.
    enfrentar_real_guardian = "Enfrentar " + real_guardian_name

    resp = client.get("/math/praticar/adicao")
    body = resp.data.decode()
    assert enfrentar_real_guardian not in body

    resp2 = client.get("/math/praticar/subtracao")
    body2 = resp2.data.decode()
    assert enfrentar_real_guardian in body2
