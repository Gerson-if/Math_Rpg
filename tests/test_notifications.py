from app.extensions import db
from app.models import Notification, User


def _create_and_login(client, db, email="aluno@example.com", username="aluno"):
    user = User(email=email, username=username)
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    client.post("/auth/login", data={"email": email, "password": "senhaforte123"})
    return user


def test_notifications_requires_login(client, db):
    resp = client.get("/notificacoes")
    assert resp.status_code in (301, 302)


def test_notifications_page_renders_report_result_and_achievement_types(client, db, app):
    user = _create_and_login(client, db)
    with app.app_context():
        db.session.add(Notification(
            user_id=user.id, type="report_result",
            payload={"is_violation": True, "reason": "A mensagem contém linguagem ofensiva.", "snippet": "xyz"},
        ))
        db.session.add(Notification(
            user_id=user.id, type="achievement",
            payload={"code": "primeiro_acerto", "name": "Primeiro Acerto"},
        ))
        db.session.commit()

    resp = client.get("/notificacoes")
    body = resp.data.decode()
    assert resp.status_code == 200
    assert "violação confirmada" in body
    assert "Primeiro Acerto" in body


def test_visiting_notifications_marks_them_read(client, db, app):
    user = _create_and_login(client, db)
    with app.app_context():
        notif = Notification(user_id=user.id, type="achievement", payload={"name": "Teste"})
        db.session.add(notif)
        db.session.commit()
        notif_id = notif.id

    client.get("/notificacoes")

    with app.app_context():
        assert Notification.query.get(notif_id).is_read is True


def test_delete_notification_removes_it(client, db, app):
    user = _create_and_login(client, db)
    with app.app_context():
        notif = Notification(user_id=user.id, type="achievement", payload={"name": "Teste"})
        db.session.add(notif)
        db.session.commit()
        notif_id = notif.id

    resp = client.post(f"/notificacoes/{notif_id}/excluir")
    assert resp.status_code in (301, 302)
    with app.app_context():
        assert Notification.query.get(notif_id) is None


def test_cannot_delete_another_users_notification(client, db, app):
    other = User(email="outro2@example.com", username="outro2")
    other.set_password("senhaforte123")
    db.session.add(other)
    db.session.commit()
    with app.app_context():
        notif = Notification(user_id=other.id, type="achievement", payload={"name": "Teste"})
        db.session.add(notif)
        db.session.commit()
        notif_id = notif.id

    _create_and_login(client, db)
    resp = client.post(f"/notificacoes/{notif_id}/excluir")
    assert resp.status_code == 404
    with app.app_context():
        assert Notification.query.get(notif_id) is not None


def test_navbar_shows_notification_bell_badge_and_clears_after_visiting(client, db, app):
    # Direct Notification creation (not via chat_service) keeps this test
    # isolated to the notifications badge — routing it through a real
    # chat report would also trip the separate chat-unread badge, which
    # shares the exact same CSS classes and would make the "no badge
    # left" assertion ambiguous.
    user = _create_and_login(client, db, email="viewernotif@example.com", username="viewernotif")
    with app.app_context():
        db.session.add(Notification(user_id=user.id, type="achievement", payload={"name": "Teste"}))
        db.session.commit()

    resp = client.get("/math/")
    body = resp.data.decode()
    bell_section = body.split('title="Notificações"')[1][:400]
    assert "bg-blood text-white text-[0.6rem] rounded-full" in bell_section

    client.get("/notificacoes")
    resp2 = client.get("/math/")
    body2 = resp2.data.decode()
    bell_section2 = body2.split('title="Notificações"')[1][:400]
    assert "bg-blood text-white text-[0.6rem] rounded-full" not in bell_section2
