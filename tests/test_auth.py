from app.extensions import db
from app.models import User, Level, Rank


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_codice_is_publicly_reachable_without_login(client):
    resp = client.get("/auth/codice")
    assert resp.status_code == 200
    assert "Códice" in resp.data.decode()


def test_salao_dos_herois_is_publicly_reachable_without_login(client, db):
    resp = client.get("/auth/salao-dos-herois")
    assert resp.status_code == 200
    assert "Salão dos Heróis" in resp.data.decode()


def test_salao_dos_herois_shows_current_activity_for_a_recently_active_player(client, db, app):
    from datetime import datetime
    from app.models import Profile, PlayerStats, Subject, Topic, Attempt

    user = User(email="ativo@example.com", username="ativo")
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.flush()
    db.session.add(Profile(user_id=user.id, display_name="Ativo"))
    db.session.add(PlayerStats(user_id=user.id, xp=100))

    subject = Subject(slug="tabuada", name="Tabuada", order=0)
    db.session.add(subject)
    db.session.flush()
    topic = Topic(slug="tabuada-do-7", name="Tabuada do 7", subject_id=subject.id, order=0, base_difficulty=1)
    db.session.add(topic)
    db.session.flush()
    db.session.add(Attempt(
        user_id=user.id, topic_id=topic.id, difficulty=1, is_correct=True,
        response_time_ms=1000, created_at=datetime.utcnow(),
    ))
    db.session.commit()

    resp = client.get("/auth/salao-dos-herois")
    body = resp.data.decode()
    assert "Ativo" in body
    assert "Tabuada do 7" in body
    assert "agora" in body


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

