import re

import pytest

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


# --- Fase 7: new topic families, exercised through the real HTTP cycle ----

def test_fraction_answer_is_accepted_through_the_real_flow(client, db, app):
    user = _create_and_login(client, db)
    topic = _create_topic(db, slug="fracoes-basicas")

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    assert resp.status_code == 200
    token = _extract_token(resp.data.decode())

    with app.app_context():
        payload = question_token.read_token(token)
    correct_answer = payload["answer"]  # e.g. "3/4" or a whole number like "2"

    resp2 = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": token, "answer": correct_answer},
    )
    assert "Correto" in resp2.data.decode()

    attempt = Attempt.query.filter_by(user_id=user.id, topic_id=topic.id).first()
    assert attempt.is_correct is True


def test_decimal_answer_with_pt_br_comma_is_accepted(client, db, app):
    """Brazilian users naturally type '0,3', not '0.3' — the answer
    comparison must treat the comma as a decimal separator."""
    _create_and_login(client, db)
    topic = _create_topic(db, slug="leitura-de-decimais")

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    token = _extract_token(resp.data.decode())

    with app.app_context():
        payload = question_token.read_token(token)
    comma_answer = payload["answer"].replace(".", ",")

    resp2 = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": token, "answer": comma_answer},
    )
    assert "Correto" in resp2.data.decode()


def test_decimal_operation_whole_result_matches_plain_integer_input(client, db, app):
    """A decimal subtraction that lands on a whole number (e.g. '3.0')
    must still accept a plain '3' from the user."""
    _create_and_login(client, db)
    topic = _create_topic(db, slug="operacoes-com-decimais")

    for _ in range(30):  # only some draws land on a whole-number result
        resp = client.get(f"/math/praticar/{topic.slug}/questao")
        token = _extract_token(resp.data.decode())
        with app.app_context():
            payload = question_token.read_token(token)
        answer = payload["answer"]
        if float(answer).is_integer():
            resp2 = client.post(
                f"/math/praticar/{topic.slug}/responder",
                data={"token": token, "answer": str(int(float(answer)))},
            )
            assert "Correto" in resp2.data.decode()
            return
    raise AssertionError("did not draw a whole-number decimal result in 30 tries")


def test_dynamic_difficulty_rises_after_a_streak_of_correct_answers(client, db, app):
    """Pendência: difficulty was static per topic; it now adapts to
    mastery/streak. A long streak of correct answers on a base-difficulty-1
    topic should eventually serve a harder question, end to end through
    the real HTTP flow (not just the service function in isolation)."""
    _create_and_login(client, db)
    topic = _create_topic(db, slug="adicao")
    assert topic.base_difficulty == 1

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    token = _extract_token(resp.data.decode())

    difficulties = []
    for _ in range(8):
        with app.app_context():
            payload = question_token.read_token(token)
        difficulties.append(payload["difficulty"])
        resp = client.post(
            f"/math/praticar/{topic.slug}/responder",
            data={"token": token, "answer": payload["answer"]},
        )
        token = _extract_token(resp.data.decode())

    assert max(difficulties) > topic.base_difficulty


@pytest.mark.parametrize("slug", ["numeros-e-contagem", "comparacao-de-quantidades"])
def test_fundamentos_topic_is_reachable_through_the_real_flow(client, db, app, slug):
    """Regression: these two topics are seeded in the curriculum
    (scripts/seed.py) but had no generator registered in
    mathematics_service — every question load 404'd because
    new_question() catches the resulting ValueError and aborts."""
    _create_and_login(client, db)
    topic = _create_topic(db, slug=slug)

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    assert resp.status_code == 200
    token = _extract_token(resp.data.decode())

    with app.app_context():
        payload = question_token.read_token(token)

    resp2 = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": token, "answer": payload["answer"]},
    )
    assert resp2.status_code == 200
    assert "Correto" in resp2.data.decode()
