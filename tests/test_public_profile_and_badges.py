from app.extensions import db
from app.models import User, Achievement, UserAchievement


def _create_and_login(client, db, email="a@example.com", username="a"):
    user = User(email=email, username=username)
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    client.post("/auth/login", data={"email": email, "password": "senhaforte123"})
    return user


def _make_achievement(code, name="Conquista"):
    a = Achievement(code=code, name=name, description="desc", criteria={})
    db.session.add(a)
    db.session.flush()
    return a


def _unlock(user, achievement):
    ua = UserAchievement(user_id=user.id, achievement_id=achievement.id)
    db.session.add(ua)
    db.session.flush()
    return ua


def test_public_profile_requires_login(client, db):
    resp = client.get("/jogador/someone")
    assert resp.status_code in (301, 302)


def test_public_profile_404s_for_an_unknown_username(client, db):
    _create_and_login(client, db)
    resp = client.get("/jogador/does-not-exist")
    assert resp.status_code == 404


def test_public_profile_redirects_to_own_profile_for_yourself(client, db):
    user = _create_and_login(client, db)
    resp = client.get(f"/jogador/{user.username}", follow_redirects=True)
    assert resp.status_code == 200
    assert resp.request.path == "/profile"


def test_public_profile_never_shows_the_targets_email(client, db, app):
    with app.app_context():
        other = User(email="secret@example.com", username="other")
        other.set_password("senhaforte123")
        db.session.add(other)
        db.session.commit()

    _create_and_login(client, db)
    resp = client.get("/jogador/other")
    assert "secret@example.com" not in resp.data.decode()


def test_public_profile_shows_featured_achievements(client, db, app):
    with app.app_context():
        other = User(email="hero@example.com", username="hero")
        other.set_password("senhaforte123")
        db.session.add(other)
        db.session.commit()
        a = _make_achievement("first", "Primeira Vitória")
        ua = _unlock(other, a)
        ua.is_featured = True
        db.session.commit()

    _create_and_login(client, db)
    resp = client.get("/jogador/hero")
    assert "Primeira Vitória" in resp.data.decode()


def test_toggle_featured_marks_an_unlocked_achievement(client, db, app):
    user = _create_and_login(client, db)
    with app.app_context():
        a = _make_achievement("badge1")
        _unlock(user, a)
        db.session.commit()
        achievement_id = a.id

    resp = client.post(f"/achievements/destacar/{achievement_id}", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        ua = UserAchievement.query.filter_by(user_id=user.id, achievement_id=achievement_id).first()
        assert ua.is_featured is True


def test_toggle_featured_untoggles_when_already_featured(client, db, app):
    user = _create_and_login(client, db)
    with app.app_context():
        a = _make_achievement("badge2")
        ua = _unlock(user, a)
        ua.is_featured = True
        db.session.commit()
        achievement_id = a.id

    client.post(f"/achievements/destacar/{achievement_id}")

    with app.app_context():
        ua = UserAchievement.query.filter_by(user_id=user.id, achievement_id=achievement_id).first()
        assert ua.is_featured is False


def test_toggle_featured_rejects_a_fourth_badge(client, db, app):
    user = _create_and_login(client, db)
    with app.app_context():
        ids = []
        for i in range(4):
            a = _make_achievement(f"badge{i}")
            ua = _unlock(user, a)
            if i < 3:
                ua.is_featured = True
            ids.append(a.id)
        db.session.commit()
        fourth_id = ids[3]

    resp = client.post(f"/achievements/destacar/{fourth_id}", follow_redirects=True)
    assert resp.status_code == 200
    assert "já tem 3 conquistas em destaque" in resp.data.decode()

    with app.app_context():
        ua = UserAchievement.query.filter_by(user_id=user.id, achievement_id=fourth_id).first()
        assert ua.is_featured is False


def test_toggle_featured_rejects_a_locked_achievement(client, db, app):
    _create_and_login(client, db)
    with app.app_context():
        a = _make_achievement("locked")
        db.session.commit()
        achievement_id = a.id

    resp = client.post(f"/achievements/destacar/{achievement_id}", follow_redirects=True)
    assert resp.status_code == 200
    assert "não desbloqueou" in resp.data.decode()


def test_public_profile_shows_add_friend_button_for_a_stranger(client, db):
    _create_and_login(client, db, email="viewer@example.com", username="viewer")
    stranger = User(email="stranger@example.com", username="stranger")
    stranger.set_password("senhaforte123")
    db.session.add(stranger)
    db.session.commit()

    resp = client.get("/jogador/stranger")
    body = resp.data.decode()
    assert "Adicionar Amigo" in body


def test_public_profile_shows_pending_badge_after_sending_a_request(client, db):
    _create_and_login(client, db, email="viewer2@example.com", username="viewer2")
    target = User(email="target2@example.com", username="target2")
    target.set_password("senhaforte123")
    db.session.add(target)
    db.session.commit()

    client.post("/amigos/solicitar", data={"username": "target2"})

    resp = client.get("/jogador/target2")
    body = resp.data.decode()
    assert "Convite de amizade enviado" in body
    assert "Adicionar Amigo" not in body


def test_public_profile_shows_accept_button_for_an_incoming_request(client, db, app):
    from app.services import friends_service

    _create_and_login(client, db, email="viewer3@example.com", username="viewer3")

    sender = User(email="sender3@example.com", username="sender3")
    sender.set_password("senhaforte123")
    db.session.add(sender)
    db.session.commit()
    friends_service.send_request(sender.id, "viewer3")

    resp = client.get("/jogador/sender3")
    body = resp.data.decode()
    assert "Aceitar convite de amizade" in body


def test_public_profile_shows_friends_badge_once_accepted(client, db, app):
    from app.services import friends_service

    other = User(email="other4@example.com", username="other4")
    other.set_password("senhaforte123")
    db.session.add(other)
    db.session.commit()

    user = _create_and_login(client, db, email="viewer4@example.com", username="viewer4")
    friendship = friends_service.send_request(other.id, "viewer4")
    friends_service.respond(friendship.id, user.id, accept=True)

    resp = client.get("/jogador/other4")
    body = resp.data.decode()
    assert "Vocês são amigos" in body
