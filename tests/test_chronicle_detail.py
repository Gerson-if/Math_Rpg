from app.extensions import db
from app.models import User, Subject, Topic, Attempt


def _create_and_login(client, db, email="reader@example.com"):
    user = User(email=email, username="reader")
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    client.post("/auth/login", data={"email": email, "password": "senhaforte123"})
    return user


def test_chronicle_detail_requires_login(client, db):
    resp = client.get("/math/cronicas/fundamentos")
    assert resp.status_code in (301, 302)


def test_chronicle_detail_redirects_when_not_yet_discovered(client, db, app):
    _create_and_login(client, db)
    with app.app_context():
        subject = Subject(slug="fundamentos", name="Fundamentos", order=0)
        db.session.add(subject)
        db.session.commit()

    resp = client.get("/math/cronicas/fundamentos", follow_redirects=True)
    assert resp.status_code == 200
    assert "/math/cronicas" in [r.request.path for r in resp.history] or resp.request.path == "/math/cronicas"


def test_chronicle_detail_renders_all_chapters_once_discovered(client, db, app):
    user = _create_and_login(client, db)
    with app.app_context():
        subject = Subject(slug="fundamentos", name="Fundamentos", order=0)
        db.session.add(subject)
        db.session.flush()
        topic = Topic(slug="numeros-e-contagem", name="Números e contagem", subject_id=subject.id, order=0)
        db.session.add(topic)
        db.session.flush()
        db.session.add(Attempt(
            user_id=user.id, topic_id=topic.id, difficulty=1,
            is_correct=True, response_time_ms=1000,
        ))
        db.session.commit()

    resp = client.get("/math/cronicas/fundamentos")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Os Primeiros Passos" in body
    assert "Capítulo 1" in body


def test_chronicle_detail_404s_for_a_subject_without_lore(client, db, app):
    _create_and_login(client, db)
    with app.app_context():
        subject = Subject(slug="sem-lore", name="Sem Lore", order=0)
        db.session.add(subject)
        db.session.commit()

    resp = client.get("/math/cronicas/sem-lore")
    assert resp.status_code == 404
