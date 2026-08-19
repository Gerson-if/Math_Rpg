from datetime import datetime, timedelta

import pytest

from app.models import ChatModeration, User
from app.services import chat_service


def _create_user(db, email="autor@example.com", username="autor"):
    user = User(email=email, username=username)
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    return user


def _create_and_login(client, db, email="aluno@example.com", username="aluno"):
    user = User(email=email, username=username)
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    client.post("/auth/login", data={"email": email, "password": "senhaforte123"})
    return user


def _send_backdated(user_id, content):
    """Sends a message and immediately backdates it past the cooldown/
    duplicate-window so the *next* call to send_message isn't rejected —
    same trick tests/test_chat.py already uses, just factored out since
    triggering several violations in a row needs it repeatedly."""
    message = chat_service.send_message(user_id, content)
    message.created_at = datetime.utcnow() - timedelta(seconds=90)
    from app.extensions import db
    db.session.commit()
    return message


def test_proactive_scan_flags_offensive_language_without_a_report(app, db):
    user = _create_user(db)
    message = chat_service.send_message(user.id, "isso é uma grande merda")

    assert message.is_flagged is True
    assert message.moderation_warning is not None
    assert message.moderation_warning.action == "warning"

    moderation = ChatModeration.query.filter_by(user_id=user.id).first()
    assert moderation is not None
    assert moderation.violation_count == 1
    assert moderation.muted_until is None


def test_clean_message_never_creates_a_moderation_row(app, db):
    user = _create_user(db)
    message = chat_service.send_message(user.id, "bom dia a todos")

    assert message.moderation_warning is None
    assert ChatModeration.query.filter_by(user_id=user.id).first() is None


def test_spam_heuristic_alone_warns_but_never_escalates(app, db):
    user = _create_user(db)
    for _ in range(3):
        message = _send_backdated(user.id, "AAAAAAAAAAAAAAAAAAAA " + str(_))

    assert message.moderation_warning is not None
    assert message.moderation_warning.action == "warning"
    # A caps/repeated-char hit is a heads-up, never a punishment — no
    # ChatModeration row at all, no matter how many times it happens.
    assert ChatModeration.query.filter_by(user_id=user.id).first() is None


def test_first_violation_warning_previews_what_the_second_one_costs(app, db):
    user = _create_user(db)
    message = chat_service.send_message(user.id, "seu idiota")

    assert message.moderation_warning.action == "warning"
    assert "15min" in message.moderation_warning.next_consequence


def test_banned_users_warning_has_no_next_consequence_to_preview(app, db):
    user = _create_user(db)
    outcome = None
    for i in range(5):
        message = _send_backdated(user.id, f"seu lixo idiota {i}")
        outcome = message.moderation_warning
        moderation = ChatModeration.query.filter_by(user_id=user.id).first()
        if moderation:
            moderation.muted_until = None
            db.session.commit()

    assert outcome.action == "banned"
    assert outcome.next_consequence is None


def test_second_offense_mutes_the_user_temporarily(app, db):
    user = _create_user(db)
    _send_backdated(user.id, "seu lixo")
    second = _send_backdated(user.id, "seu merda de novo")

    assert second.moderation_warning.action == "muted"
    moderation = ChatModeration.query.filter_by(user_id=user.id).first()
    assert moderation.violation_count == 2
    assert moderation.muted_until > datetime.utcnow()


def test_muted_user_cannot_send_further_messages(app, db):
    user = _create_user(db)
    _send_backdated(user.id, "seu lixo")
    _send_backdated(user.id, "seu merda de novo")

    with pytest.raises(chat_service.ChatError, match="silenciado"):
        chat_service.send_message(user.id, "mais uma mensagem qualquer")


def test_escalation_ladder_eventually_bans_the_account(app, db):
    user = _create_user(db)
    outcomes = []
    for i in range(5):
        message = _send_backdated(user.id, f"seu lixo idiota {i}")
        outcomes.append(message.moderation_warning.action)
        # A mute genuinely blocks further sends (see
        # test_muted_user_cannot_send_further_messages) — clearing it here
        # stands in for "time passed and the mute wore off", so the loop
        # can exercise every rung of the ladder instead of getting stuck
        # ChatError-ing on the second iteration.
        moderation = ChatModeration.query.filter_by(user_id=user.id).first()
        if moderation:
            moderation.muted_until = None
            db.session.commit()

    assert outcomes == ["warning", "muted", "muted", "muted", "banned"]
    moderation = ChatModeration.query.filter_by(user_id=user.id).first()
    assert moderation.violation_count == 5
    db.session.refresh(user)
    assert user.is_active is False


def test_report_does_not_double_count_a_message_already_flagged_at_send_time(app, db):
    author = _create_user(db, email="autor2@example.com", username="autor2")
    reporter = _create_user(db, email="rep2@example.com", username="rep2")
    message = chat_service.send_message(author.id, "seu idiota")

    moderation = ChatModeration.query.filter_by(user_id=author.id).first()
    assert moderation.violation_count == 1

    chat_service.report_message(message.id, reporter.id)

    db.session.refresh(moderation)
    assert moderation.violation_count == 1


def test_report_confirming_a_spam_only_message_does_escalate(app, db):
    author = _create_user(db, email="autor3@example.com", username="autor3")
    reporter = _create_user(db, email="rep3@example.com", username="rep3")
    message = chat_service.send_message(author.id, "AAAAAAAAAAAAAAAAAAAA")
    assert ChatModeration.query.filter_by(user_id=author.id).first() is None

    chat_service.report_message(message.id, reporter.id)

    moderation = ChatModeration.query.filter_by(user_id=author.id).first()
    assert moderation is not None
    assert moderation.violation_count == 1


def test_banned_account_cannot_log_in(client, db):
    user = User(email="banido@example.com", username="banido")
    user.set_password("senhaforte123")
    user.is_active = False
    db.session.add(user)
    db.session.commit()

    resp = client.post(
        "/auth/login",
        data={"email": "banido@example.com", "password": "senhaforte123"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert "suspensa" in resp.data.decode()
    # Still on/back at the login form, not redirected into the app.
    assert "Entrar no Reino" in resp.data.decode() or "form" in resp.data.decode()


def test_already_logged_in_user_is_forced_out_once_banned(client, db, app):
    user = _create_and_login(client, db, email="banidoativo@example.com", username="banidoativo")
    resp = client.get("/math/")
    assert resp.status_code == 200

    # No need for a fresh `with app.app_context()` here — the `app`
    # fixture already keeps one open for the whole test, so `user` is
    # still a live, attached ORM object on that same session.
    user.is_active = False
    db.session.commit()

    resp = client.get("/math/", follow_redirects=True)
    assert resp.status_code == 200
    assert "/auth/login" in resp.request.path
