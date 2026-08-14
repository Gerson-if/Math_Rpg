from app.extensions import db
from app.models import User, Level, Rank


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_register_creates_user_and_dependents(client, db):
    resp = client.post(
        "/auth/register",
        data={
            "username": "aluno1",
            "email": "aluno1@example.com",
            "password": "senhaforte123",
            "confirm_password": "senhaforte123",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    user = User.query.filter_by(email="aluno1@example.com").first()
    assert user is not None
    assert user.profile is not None
    assert user.stats is not None


def test_register_places_the_new_player_on_the_rank_ladder_immediately(client, db):
    """New players used to show a blank '-' rank/level in the ranking
    until their first answer — confusing. Registration now assigns level 1
    and the lowest rank right away, when the ladder is seeded."""
    db.session.add(Level(number=1, xp_required=0))
    db.session.add(Rank(slug="iniciante", name="Iniciante", order=1, min_level=1))
    db.session.commit()

    client.post(
        "/auth/register",
        data={
            "username": "novato",
            "email": "novato@example.com",
            "password": "senhaforte123",
            "confirm_password": "senhaforte123",
        },
        follow_redirects=True,
    )

    user = User.query.filter_by(email="novato@example.com").first()
    assert user.stats.level is not None
    assert user.stats.level.number == 1
    assert user.stats.rank is not None
    assert user.stats.rank.slug == "iniciante"


def test_login_wrong_password_shows_error(client, db):
    user = User(email="x@example.com", username="x")
    user.set_password("correcthorsebattery")
    db.session.add(user)
    db.session.commit()

    resp = client.post(
        "/auth/login",
        data={"email": "x@example.com", "password": "wrong"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    # Still on the login page, not redirected into the app.
    dashboard = client.get("/dashboard", follow_redirects=False)
    assert dashboard.status_code in (301, 302)  # bounced to login, not authenticated

