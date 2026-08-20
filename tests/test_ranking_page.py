from app.extensions import db
from app.models import User, PlayerStats, Rank, Profile


def _make_player(email, xp, character_class=None):
    user = User(email=email, username=email.split("@")[0])
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.flush()
    db.session.add(PlayerStats(user_id=user.id, xp=xp))
    if character_class:
        db.session.add(Profile(user_id=user.id, display_name=user.username, character_class=character_class))
    db.session.commit()
    return user


def _login(client, email):
    client.post("/auth/login", data={"email": email, "password": "senhaforte123"})


def test_ranking_page_requires_login(client, db):
    resp = client.get("/ranking/")
    assert resp.status_code in (301, 302)


def test_ranking_page_renders_podium_ladder_and_class_badges(client, db, app):
    with app.app_context():
        db.session.add(Rank(slug="iniciante", name="Iniciante", order=1, min_level=1))
        db.session.add(Rank(slug="bronze", name="Bronze", order=2, min_level=5))
        db.session.add(Rank(slug="grao-mestre", name="Grão-Mestre", order=8, min_level=100))
        db.session.commit()

        _make_player("first@example.com", 500, character_class="mago")
        _make_player("second@example.com", 300)
        _make_player("third@example.com", 200)
        _make_player("fourth@example.com", 100)

    _login(client, "first@example.com")
    resp = client.get("/ranking/")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Podium + table both render for 4 players.
    assert body.count("XP") >= 3
    # New rank tier shows up in the ladder even without dedicated art
    # (falls back to a 2-letter initial in rank_badge).
    assert "Grão-Mestre" in body
    # The podium's #1 player picked a class — its icon badge should render.
    assert "fa-hat-wizard" in body


def test_ranking_page_handles_players_with_no_profile_or_class(client, db, app):
    with app.app_context():
        db.session.add(Rank(slug="iniciante", name="Iniciante", order=1, min_level=1))
        db.session.commit()
        _make_player("solo@example.com", 50)

    _login(client, "solo@example.com")
    resp = client.get("/ranking/")
    assert resp.status_code == 200
