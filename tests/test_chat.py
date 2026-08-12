import pytest

from app.models import User, ChatMessage
from app.services import chat_service


def _create_and_login(client, db, email="aluno@example.com", username="aluno"):
    user = User(email=email, username=username)
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    client.post("/auth/login", data={"email": email, "password": "senhaforte123"})
    return user


def _create_user(db, email="outro@example.com", username="outro"):
    user = User(email=email, username=username)
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    return user


def test_send_message_persists_and_returns_it(app, db):
    user = _create_user(db)
    message = chat_service.send_message(user.id, "  Olá pessoal!  ")

    assert message.content == "Olá pessoal!"
    assert message.room == "global"
    assert ChatMessage.query.count() == 1


def test_send_message_rejects_empty_content(app, db):
    user = _create_user(db)
    with pytest.raises(chat_service.ChatError):
        chat_service.send_message(user.id, "   ")


def test_send_message_rejects_too_long_content(app, db):
    user = _create_user(db)
    with pytest.raises(chat_service.ChatError):
        chat_service.send_message(user.id, "x" * 501)


def test_send_message_enforces_cooldown(app, db):
    user = _create_user(db)
    chat_service.send_message(user.id, "primeira mensagem")
    with pytest.raises(chat_service.ChatError):
        chat_service.send_message(user.id, "segunda mensagem, sem esperar")


def test_send_message_rejects_duplicate_within_window(app, db):
    user = _create_user(db)
    msg = chat_service.send_message(user.id, "spam")
    # Backdate the message so the cooldown has passed but the duplicate
    # window (60s) has not, isolating the duplicate-content check.
    from datetime import datetime, timedelta
    msg.created_at = datetime.utcnow() - timedelta(seconds=10)
    db.session.commit()

    with pytest.raises(chat_service.ChatError):
        chat_service.send_message(user.id, "spam")


def test_looks_like_spam_flags_all_caps_and_repeated_chars():
    assert chat_service._looks_like_spam("ISSO AQUI É SPAM") is True
    assert chat_service._looks_like_spam("aaaaaaah bom dia") is True
    assert chat_service._looks_like_spam("bom dia pessoal") is False


def test_chat_index_requires_login(client, db):
    resp = client.get("/chat/")
    assert resp.status_code in (301, 302)


def test_send_message_via_route_appends_to_list(client, db):
    _create_and_login(client, db)
    resp = client.post("/chat/enviar", data={"content": "oi turma"})
    assert resp.status_code == 200
    assert "oi turma" in resp.data.decode()


def test_send_message_via_route_rate_limited_shows_error(client, db):
    _create_and_login(client, db)
    client.post("/chat/enviar", data={"content": "primeira"})
    resp = client.post("/chat/enviar", data={"content": "segunda"})
    assert resp.status_code == 200
    assert "Aguarde" in resp.data.decode()
