from app.models import User, Profile


def _create_and_login(client, db, email="aluno@example.com"):
    user = User(email=email, username="aluno")
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.flush()
    db.session.add(Profile(user_id=user.id, display_name="Aluno"))
    db.session.commit()
    client.post("/auth/login", data={"email": email, "password": "senhaforte123"})
    return user


def test_edit_profile_requires_login(client, db):
    resp = client.get("/profile/editar")
    assert resp.status_code in (301, 302)


def test_edit_profile_updates_display_name_avatar_and_bio(client, db, app):
    user = _create_and_login(client, db)

    resp = client.post(
        "/profile/editar",
        data={
            "display_name": "Aventureiro Supremo",
            "avatar_key": "fa-dragon",
            "bio": "Caçador de números.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        profile = Profile.query.filter_by(user_id=user.id).first()
        assert profile.display_name == "Aventureiro Supremo"
        assert profile.avatar_key == "fa-dragon"
        assert profile.bio == "Caçador de números."


def test_edit_profile_rejects_an_avatar_outside_the_curated_list(client, db, app):
    user = _create_and_login(client, db)

    resp = client.post(
        "/profile/editar",
        data={"display_name": "Aluno", "avatar_key": "fa-not-a-real-choice", "bio": ""},
    )
    assert resp.status_code == 200  # re-renders the form with a validation error

    with app.app_context():
        profile = Profile.query.filter_by(user_id=user.id).first()
        assert profile.avatar_key != "fa-not-a-real-choice"


def test_profile_page_shows_the_chosen_avatar_icon(client, db):
    _create_and_login(client, db)
    client.post("/profile/editar", data={
        "display_name": "Aluno", "avatar_key": "fa-cat", "bio": "",
    })

    resp = client.get("/profile")
    assert "fa-cat" in resp.data.decode()
