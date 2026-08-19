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


def test_report_message_flags_a_message_with_offensive_language(app, db):
    author = _create_user(db, email="autor@example.com", username="autor")
    reporter = _create_user(db, email="rep@example.com", username="rep")
    message = chat_service.send_message(author.id, "isso é uma grande merda")

    result = chat_service.report_message(message.id, reporter.id)

    assert message.is_flagged is True
    assert result.is_violation is True


def test_report_message_does_not_flag_a_clean_message(app, db):
    author = _create_user(db, email="autorclean@example.com", username="autorclean")
    reporter = _create_user(db, email="repclean@example.com", username="repclean")
    message = chat_service.send_message(author.id, "bom dia, pessoal!")

    result = chat_service.report_message(message.id, reporter.id)

    assert message.is_flagged is False
    assert result.is_violation is False


def test_report_message_rejects_reporting_your_own_message(app, db):
    author = _create_user(db, email="autor2@example.com", username="autor2")
    message = chat_service.send_message(author.id, "minha mensagem")

    with pytest.raises(chat_service.ChatError):
        chat_service.report_message(message.id, author.id)


def test_report_message_rejects_a_duplicate_report_from_the_same_reporter(app, db):
    author = _create_user(db, email="autordup@example.com", username="autordup")
    reporter = _create_user(db, email="repdup@example.com", username="repdup")
    message = chat_service.send_message(author.id, "mensagem qualquer")

    chat_service.report_message(message.id, reporter.id)
    with pytest.raises(chat_service.ChatError):
        chat_service.report_message(message.id, reporter.id)


def test_report_message_rejects_a_second_report_against_the_same_player_via_a_different_message(app, db):
    author = _create_user(db, email="autordup2@example.com", username="autordup2")
    reporter = _create_user(db, email="repdup2@example.com", username="repdup2")
    first_message = chat_service.send_message(author.id, "primeira mensagem qualquer")

    chat_service.report_message(first_message.id, reporter.id)

    from datetime import datetime, timedelta
    first_message.created_at = datetime.utcnow() - timedelta(seconds=10)
    from app.extensions import db as _db
    _db.session.commit()
    second_message = chat_service.send_message(author.id, "segunda mensagem, totalmente diferente")

    with pytest.raises(chat_service.ChatError, match="jogador"):
        chat_service.report_message(second_message.id, reporter.id)


def test_report_message_notifies_both_the_reporter_and_the_reported_user(app, db):
    from app.models import Notification

    author = _create_user(db, email="autornotif@example.com", username="autornotif")
    reporter = _create_user(db, email="repnotif@example.com", username="repnotif")
    message = chat_service.send_message(author.id, "porra, que ódio")

    chat_service.report_message(message.id, reporter.id)

    reporter_notif = Notification.query.filter_by(user_id=reporter.id, type="report_result").first()
    reported_notif = Notification.query.filter_by(user_id=author.id, type="report_against_you").first()
    assert reporter_notif is not None
    assert reporter_notif.payload["is_violation"] is True
    assert reported_notif is not None
    assert reported_notif.payload["is_violation"] is True


def test_report_message_via_route_marks_it_flagged_in_the_rendered_list(client, db):
    author = _create_user(db, email="autor3@example.com", username="autor3")
    message = chat_service.send_message(author.id, "outra mensagem cheia de merda")
    _create_and_login(client, db, email="rep2@example.com", username="rep2")

    resp = client.post(f"/chat/denunciar/{message.id}")
    assert resp.status_code == 200
    body = resp.data.decode()
    assert "outline-blood" in body
    assert "violação confirmada" in body


def test_report_message_via_route_shows_no_violation_for_a_clean_message(client, db):
    author = _create_user(db, email="autor3b@example.com", username="autor3b")
    message = chat_service.send_message(author.id, "boa tarde a todos")
    _create_and_login(client, db, email="rep2b@example.com", username="rep2b")

    resp = client.post(f"/chat/denunciar/{message.id}")
    assert resp.status_code == 200
    assert "nenhuma violação encontrada" in resp.data.decode()


def test_chat_message_username_links_to_public_profile(client, db):
    author = _create_user(db, email="autor4@example.com", username="autor4")
    chat_service.send_message(author.id, "ola")
    _create_and_login(client, db, email="viewer@example.com", username="viewer")

    resp = client.get("/chat/")
    assert "/jogador/autor4" in resp.data.decode()


def test_unread_count_is_zero_before_anything_was_ever_posted(app, db):
    user = _create_user(db)
    assert chat_service.unread_count(user.id) == 0


def test_unread_count_ignores_the_users_own_messages(app, db):
    user = _create_user(db)
    chat_service.send_message(user.id, "minha propria mensagem")
    assert chat_service.unread_count(user.id) == 0


def test_unread_count_counts_others_messages_posted_after_last_seen(app, db):
    author = _create_user(db, email="autor5@example.com", username="autor5")
    reader = _create_user(db, email="leitor@example.com", username="leitor")

    chat_service.mark_seen(reader.id)
    chat_service.send_message(author.id, "mensagem nova")

    assert chat_service.unread_count(reader.id) == 1


def test_mark_seen_resets_the_unread_count_back_to_zero(app, db):
    author = _create_user(db, email="autor6@example.com", username="autor6")
    reader = _create_user(db, email="leitor2@example.com", username="leitor2")

    chat_service.send_message(author.id, "primeira mensagem")
    assert chat_service.unread_count(reader.id) == 1

    chat_service.mark_seen(reader.id)
    assert chat_service.unread_count(reader.id) == 0


def test_navbar_shows_a_chat_badge_for_unread_messages(client, db):
    author = _create_user(db, email="autor7@example.com", username="autor7")
    chat_service.send_message(author.id, "alguma novidade")
    _create_and_login(client, db, email="viewer2@example.com", username="viewer2")

    # Login itself doesn't mark chat as seen — a fresh page load elsewhere
    # in the app should still show the badge for this unread message.
    resp = client.get("/math/")
    assert "bg-blood text-white text-[0.6rem] rounded-full" in resp.data.decode()

    # Visiting the chat page itself marks it seen; the badge should be
    # gone on the very next page load.
    client.get("/chat/")
    resp2 = client.get("/math/")
    body2 = resp2.data.decode()
    assert body2.count("bg-blood text-white text-[0.6rem] rounded-full") == 0
