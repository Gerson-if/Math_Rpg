from app.extensions import db
from app.models import User, Subject, Topic, Attempt
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
        subject, topics = _make_subject_with_topics(["a", "b", "c", "d"])
        db.session.commit()

        real_guardian = guardians.for_subject("tabuada")

        first, tier_first = guardians.for_topic(topics[0])
        last, tier_last = guardians.for_topic(topics[-1])

        assert tier_first in ("minion", "elite")
        assert first["name"] != real_guardian["name"]

        assert tier_last == "boss"
        assert last["name"] == real_guardian["name"]


def test_for_topic_escalates_from_minion_to_elite_before_the_boss(app, db):
    with app.app_context():
        # 5 topics: index 0,1 minion (ceil(5/2)=3 minions: 0,1,2), 3 elite, 4 boss
        subject, topics = _make_subject_with_topics(["a", "b", "c", "d", "e"])
        db.session.commit()

        tiers = [guardians.for_topic(t)[1] for t in topics]
        assert tiers[-1] == "boss"
        assert "minion" in tiers
        assert "elite" in tiers
        # Minions never appear after an elite, and elites never appear after the boss.
        first_elite = tiers.index("elite") if "elite" in tiers else len(tiers)
        assert all(t == "minion" for t in tiers[:first_elite])
        assert all(t in ("elite", "boss") for t in tiers[first_elite:])


def test_minion_and_elite_share_the_guardians_icon_and_color(app, db):
    with app.app_context():
        subject, topics = _make_subject_with_topics(["a", "b", "c"])
        db.session.commit()

        real_guardian = guardians.for_subject("tabuada")
        for topic in topics[:-1]:
            variant, tier = guardians.for_topic(topic)
            assert tier in ("minion", "elite")
            assert variant["icon"] == real_guardian["icon"]
            assert variant["color"] == real_guardian["color"]
            assert variant["name"] != real_guardian["name"]


def test_a_subject_with_a_single_topic_treats_it_as_the_final_boss(app, db):
    with app.app_context():
        subject, topics = _make_subject_with_topics(["only"])
        db.session.commit()

        guardian, tier = guardians.for_topic(topics[0])
        assert tier == "boss"
        assert guardian["name"] == guardians.for_subject("tabuada")["name"]


def test_every_seeded_subject_has_minion_elite_and_supreme_names():
    seeded_subjects = [
        "fundamentos", "tabuada", "operacoes-fundamentais", "potenciacao",
        "radiciacao", "fracoes", "numeros-decimais", "porcentagem", "algebra",
    ]
    for slug in seeded_subjects:
        assert slug in guardians.MINION_NAMES, f"missing minion name for {slug}"
        assert slug in guardians.ELITE_MINION_NAMES, f"missing elite name for {slug}"
        assert slug in guardians.SUPREME_NAMES, f"missing supreme name for {slug}"


def test_practice_route_shows_a_lesser_variant_for_a_non_final_topic(client, db, app):
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


def test_practice_route_shows_the_supreme_guardian_after_a_prior_victory(client, db, app):
    user = User(email="q@example.com", username="q")
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    client.post("/auth/login", data={"email": "q@example.com", "password": "senhaforte123"})

    with app.app_context():
        subject, topics = _make_subject_with_topics(["so-adicao"], subject_slug="operacoes-fundamentais")
        db.session.commit()
        db.session.add(Attempt(
            user_id=user.id, topic_id=topics[0].id, difficulty=1,
            is_correct=True, response_time_ms=1000,
        ))
        db.session.commit()

    supreme_name = guardians.supreme_name_for("operacoes-fundamentais")
    resp = client.get("/math/praticar/so-adicao")
    assert ("Enfrentar " + supreme_name) in resp.data.decode()
