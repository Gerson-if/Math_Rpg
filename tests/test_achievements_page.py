from app.extensions import db
from app.models import User, Achievement, UserAchievement, PlayerStats


def _create_and_login(client, db, email="learner@example.com", username="learner"):
    user = User(email=email, username=username)
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    client.post("/auth/login", data={"email": email, "password": "senhaforte123"})
    return user


def test_achievements_page_requires_login(client, db):
    resp = client.get("/achievements/")
    assert resp.status_code in (301, 302)


def test_achievements_page_groups_by_criteria_type_and_shows_progress(client, db, app):
    user = _create_and_login(client, db)
    with app.app_context():
        db.session.add(PlayerStats(user_id=user.id, xp=0, total_correct=4, total_wrong=1, best_streak=2))
        db.session.add(Achievement(
            code="dez_acertos", name="Dez Acertos", description="Acerte 10 questões.",
            criteria={"type": "attempts_correct_total", "value": 10},
        ))
        db.session.add(Achievement(
            code="cinco_seguidos", name="Sequência de 5", description="Acerte 5 seguidas.",
            criteria={"type": "best_streak", "value": 5},
        ))
        db.session.commit()

    resp = client.get("/achievements/")
    assert resp.status_code == 200
    body = resp.data.decode()
    # Both group headings render (criteria-type based grouping).
    assert "Marcos de Acertos" in body
    assert "Sequências" in body
    # Locked achievement shows a real current/target progress readout.
    assert "4 / 10" in body
    assert "2 / 5" in body


def test_achievements_page_shows_unlocked_count_and_featured_toggle(client, db, app):
    user = _create_and_login(client, db)
    with app.app_context():
        achievement = Achievement(
            code="primeiro_acerto", name="Primeiro Acerto", description="desc",
            criteria={"type": "attempts_correct_total", "value": 1},
        )
        db.session.add(achievement)
        db.session.flush()
        db.session.add(UserAchievement(user_id=user.id, achievement_id=achievement.id))
        db.session.commit()
        achievement_id = achievement.id

    resp = client.get("/achievements/")
    body = resp.data.decode()
    assert "1</strong> / 1 conquistas desbloqueadas" in body
    assert f'action="/achievements/destacar/{achievement_id}"' in body


def test_achievements_page_handles_an_achievement_with_no_recognized_criteria_type(client, db, app):
    """Achievements seeded with an empty/unrecognized criteria dict (as
    some older test fixtures do) must fall into a generic group instead of
    crashing progress_for_achievement."""
    _create_and_login(client, db)
    with app.app_context():
        db.session.add(Achievement(code="misc", name="Misc", description="desc", criteria={}))
        db.session.commit()

    resp = client.get("/achievements/")
    assert resp.status_code == 200
    assert "Outras" in resp.data.decode()
