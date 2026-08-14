from app.extensions import db
from app.models import User, Subject, Topic, Mastery
from app.services import progression_service, guardians, lore


def _make_user(username="aprendiz"):
    user = User(email=f"{username}@example.com", username=username)
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.flush()
    return user


def _make_subject_with_topics(slugs, subject_slug="operacoes-fundamentais"):
    subject = Subject(slug=subject_slug, name="Operações Fundamentais", order=0)
    db.session.add(subject)
    db.session.flush()
    topics = []
    for i, slug in enumerate(slugs):
        prereqs = [slugs[i - 1]] if i > 0 else []
        topic = Topic(
            slug=slug, name=slug.capitalize(), subject_id=subject.id, order=i,
            base_difficulty=1, prerequisite_slugs=prereqs,
        )
        db.session.add(topic)
        topics.append(topic)
    db.session.flush()
    return subject, topics


def test_topic_without_prerequisites_has_none_unmet(app, db):
    with app.app_context():
        user = _make_user()
        _, topics = _make_subject_with_topics(["adicao", "subtracao"])
        db.session.commit()

        assert progression_service.unmet_prerequisites(user.id, topics[0]) == []


def test_topic_with_unpracticed_prerequisite_is_flagged(app, db):
    with app.app_context():
        user = _make_user()
        _, topics = _make_subject_with_topics(["adicao", "subtracao"])
        db.session.commit()

        unmet = progression_service.unmet_prerequisites(user.id, topics[1])
        assert [t.slug for t in unmet] == ["adicao"]


def test_topic_with_solid_prerequisite_mastery_is_not_flagged(app, db):
    with app.app_context():
        user = _make_user()
        _, topics = _make_subject_with_topics(["adicao", "subtracao"])
        db.session.add(Mastery(user_id=user.id, topic_id=topics[0].id, mastery_score=0.8))
        db.session.commit()

        assert progression_service.unmet_prerequisites(user.id, topics[1]) == []


def test_topic_with_weak_prerequisite_mastery_is_still_flagged(app, db):
    with app.app_context():
        user = _make_user()
        _, topics = _make_subject_with_topics(["adicao", "subtracao"])
        db.session.add(Mastery(user_id=user.id, topic_id=topics[0].id, mastery_score=0.2))
        db.session.commit()

        unmet = progression_service.unmet_prerequisites(user.id, topics[1])
        assert [t.slug for t in unmet] == ["adicao"]


def test_prerequisites_never_block_the_real_practice_route(client, db, app):
    """Advisory only — a topic with unmet prerequisites must still be
    fully practicable end to end through the real HTTP flow."""
    user = User(email="aluno@example.com", username="aluno")
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    client.post("/auth/login", data={"email": "aluno@example.com", "password": "senhaforte123"})

    with app.app_context():
        _make_subject_with_topics(["adicao", "subtracao"])
        db.session.commit()

    resp = client.get("/math/praticar/subtracao")
    assert resp.status_code == 200
    assert "Recomendado praticar primeiro" in resp.data.decode()


def test_every_curriculum_subject_has_a_distinct_guardian_and_lore_entry():
    """Not exhaustive, but the eight subjects scripts/seed.py ships today
    should each get their own guardian/chronicle, not silently fall back
    to the generic one — that's the whole point of this feature."""
    seeded_subjects = [
        "fundamentos", "tabuada", "operacoes-fundamentais", "potenciacao",
        "radiciacao", "fracoes", "numeros-decimais", "porcentagem", "algebra",
    ]
    seen_names = set()
    for slug in seeded_subjects:
        guardian = guardians.for_subject(slug)
        assert guardian["name"] not in seen_names, f"duplicate guardian for {slug}"
        seen_names.add(guardian["name"])
        assert lore.for_subject(slug) is not None, f"missing lore for {slug}"


def test_unknown_subject_falls_back_to_a_generic_guardian_without_erroring():
    guardian = guardians.for_subject("materia-que-nao-existe")
    assert guardian["name"]
    assert guardian["icon"]


def test_chronicle_is_locked_until_the_subject_has_been_practiced(client, db, app):
    user = User(email="cronista@example.com", username="cronista")
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    client.post("/auth/login", data={"email": "cronista@example.com", "password": "senhaforte123"})

    with app.app_context():
        subject = Subject(slug="fundamentos", name="Fundamentos", order=0)
        db.session.add(subject)
        db.session.flush()
        db.session.add(Topic(slug="numeros-e-contagem", name="Números e contagem", subject_id=subject.id, order=0))
        db.session.commit()

    resp = client.get("/math/cronicas")
    assert resp.status_code == 200
    assert "???" in resp.data.decode()
    assert "Os Primeiros Passos" not in resp.data.decode()
