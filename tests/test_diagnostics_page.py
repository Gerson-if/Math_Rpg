from app.extensions import db
from app.models import User, Subject, Topic, Mastery


def _create_and_login(client, db, email="diag@example.com", username="diag"):
    user = User(email=email, username=username)
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    client.post("/auth/login", data={"email": email, "password": "senhaforte123"})
    return user


def test_diagnostics_page_requires_login(client, db):
    resp = client.get("/diagnostico/")
    assert resp.status_code in (301, 302)


def test_diagnostics_page_shows_the_weakest_area_and_a_practice_link(client, db, app):
    user = _create_and_login(client, db)
    with app.app_context():
        subject = Subject(slug="fracoes", name="Frações", order=0)
        db.session.add(subject)
        db.session.flush()
        topic = Topic(slug="fracoes-basicas", name="Frações básicas", subject_id=subject.id, order=0, base_difficulty=1)
        db.session.add(topic)
        db.session.flush()
        db.session.add(Mastery(user_id=user.id, topic_id=topic.id, mastery_score=0.2, correct_count=1, wrong_count=4))
        db.session.commit()
        topic_slug = topic.slug

    resp = client.get("/diagnostico/")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Frações e Números Racionais" in body
    assert "Sua maior lacuna agora" in body
    assert f'/math/praticar/{topic_slug}' in body


def test_diagnostics_page_renders_with_no_practice_history(client, db):
    _create_and_login(client, db)
    resp = client.get("/diagnostico/")
    assert resp.status_code == 200
