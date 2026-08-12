import re

from app.models import User, Subject, Topic, Attempt
from app.services import question_token


def _create_and_login(client, db, email="aluno@example.com"):
    user = User(email=email, username="aluno")
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    client.post("/auth/login", data={"email": email, "password": "senhaforte123"})
    return user


def _create_topic(db, slug="tabuada-do-7"):
    subject = Subject(slug="tabuada", name="Tabuada", order=0)
    db.session.add(subject)
    db.session.flush()
    topic = Topic(slug=slug, name="Tabuada do 7", subject_id=subject.id, order=0, base_difficulty=1)
    db.session.add(topic)
    db.session.commit()
    return topic


def _extract_token(html: str) -> str:
    match = re.search(r'name="token" value="([^"]+)"', html)
    assert match, "token field not found in question fragment"
    return match.group(1)


def test_new_question_requires_login(client, db):
    topic = _create_topic(db)
    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    assert resp.status_code in (301, 302)  # bounced to login


def test_correct_answer_is_recorded(client, db, app):
    user = _create_and_login(client, db)
    topic = _create_topic(db)

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    assert resp.status_code == 200
    token = _extract_token(resp.data.decode())

    with app.app_context():
        payload = question_token.read_token(token)
    correct_answer = payload["answer"]

    resp2 = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": token, "answer": correct_answer},
    )
    assert resp2.status_code == 200
    assert "Correto" in resp2.data.decode()
    assert "XP" in resp2.data.decode()

    attempt = Attempt.query.filter_by(user_id=user.id, topic_id=topic.id).first()
    assert attempt is not None
    assert attempt.is_correct is True
    assert attempt.response_time_ms >= 0


def test_wrong_answer_is_recorded_as_incorrect(client, db, app):
    user = _create_and_login(client, db)
    topic = _create_topic(db)

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    token = _extract_token(resp.data.decode())

    resp2 = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": token, "answer": "definitely-not-a-number"},
    )
    assert resp2.status_code == 200

    attempt = Attempt.query.filter_by(user_id=user.id, topic_id=topic.id).first()
    assert attempt is not None
    assert attempt.is_correct is False


def test_tampered_token_is_rejected(client, db):
    _create_and_login(client, db)
    topic = _create_topic(db)

    resp = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": "not-a-real-token", "answer": "42"},
    )
    assert resp.status_code == 400
