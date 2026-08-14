from app.models import User, Profile, Level, PlayerStats
from app.services import classes


def _create_and_login(client, db, email="aluno@example.com", level_number=1):
    user = User(email=email, username="aluno")
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.flush()
    db.session.add(Profile(user_id=user.id, display_name="Aluno"))
    level = Level.query.filter_by(number=level_number).first()
    if level is None:
        level = Level(number=level_number, xp_required=0)
        db.session.add(level)
        db.session.flush()
    db.session.add(PlayerStats(user_id=user.id, level_id=level.id))
    db.session.commit()
    client.post("/auth/login", data={"email": email, "password": "senhaforte123"})
    return user


# ---------------- app/services/classes.py unit tests ----------------

def test_current_tier_matches_the_highest_unlocked_milestone():
    assert classes.current_tier(1) == 0
    assert classes.current_tier(9) == 0
    assert classes.current_tier(10) == 1
    assert classes.current_tier(24) == 1
    assert classes.current_tier(25) == 2
    assert classes.current_tier(99) == 2


def test_can_choose_class_is_always_true_before_a_first_pick():
    assert classes.can_choose_class(1, -1) is True
    assert classes.can_choose_class(30, -1) is True


def test_can_choose_class_is_false_until_a_new_tier_unlocks():
    assert classes.can_choose_class(5, 0) is False
    assert classes.can_choose_class(9, 0) is False


def test_can_choose_class_is_true_once_a_new_tier_unlocks():
    assert classes.can_choose_class(10, 0) is True
    assert classes.can_choose_class(25, 1) is True


def test_ability_for_returns_the_named_ability_for_the_tier():
    assert classes.ability_for("guerreiro", 0) == "Golpe Poderoso"
    assert classes.ability_for("guerreiro", 2) == "Ira Implacável"
    assert classes.ability_for("nao-existe", 0) is None


def test_class_buff_is_empty_when_nothing_was_claimed():
    assert classes.class_buff(None, -1) == {
        "danoPct": 0.0, "critBonus": 0.0, "furiaBonus": 0.0,
        "comboBonus": 0.0, "vidaBonus": 0.0, "vampirismoPct": 0.0,
    }
    assert classes.class_buff("guerreiro", -1) == classes.class_buff(None, -1)


def test_class_buff_scales_with_the_claimed_tier():
    tier0 = classes.class_buff("guerreiro", 0)
    tier2 = classes.class_buff("guerreiro", 2)
    assert tier0["danoPct"] > 0
    assert tier2["danoPct"] > tier0["danoPct"]
    # Only the class's own buff_type category should move.
    assert tier0["critBonus"] == 0.0


# ---------------- routes: GET/POST /profile/classe ----------------

def test_choosing_a_class_for_the_first_time_is_always_allowed(client, db, app):
    user = _create_and_login(client, db, level_number=1)

    resp = client.get("/profile/classe")
    assert resp.status_code == 200
    assert "Mago" in resp.data.decode()

    resp = client.post("/profile/classe", data={"character_class": "mago"}, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        profile = Profile.query.filter_by(user_id=user.id).first()
        assert profile.character_class == "mago"
        assert profile.class_tier_claimed == 0


def test_reclassing_is_blocked_before_the_next_ability_tier_unlocks(client, db, app):
    user = _create_and_login(client, db, level_number=5)
    with app.app_context():
        profile = Profile.query.filter_by(user_id=user.id).first()
        profile.character_class = "guerreiro"
        profile.class_tier_claimed = 0
        db.session.commit()

    resp = client.get("/profile/classe", follow_redirects=True)
    assert resp.status_code == 200
    # Redirected back to the profile page instead of showing the picker.
    assert "Escolha sua classe" not in resp.data.decode()

    resp = client.post("/profile/classe", data={"character_class": "mago"})
    with app.app_context():
        profile = Profile.query.filter_by(user_id=user.id).first()
        assert profile.character_class == "guerreiro"
        assert profile.class_tier_claimed == 0


def test_reclassing_is_allowed_once_the_next_ability_tier_unlocks(client, db, app):
    user = _create_and_login(client, db, level_number=10)
    with app.app_context():
        profile = Profile.query.filter_by(user_id=user.id).first()
        profile.character_class = "guerreiro"
        profile.class_tier_claimed = 0
        db.session.commit()

    resp = client.get("/profile/classe")
    assert resp.status_code == 200
    assert "Trocar de classe" in resp.data.decode() or "Fúria de Batalha" in resp.data.decode()

    resp = client.post("/profile/classe", data={"character_class": "clerigo"}, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        profile = Profile.query.filter_by(user_id=user.id).first()
        assert profile.character_class == "clerigo"
        assert profile.class_tier_claimed == 1


def test_profile_page_shows_the_chosen_class_and_ability(client, db):
    _create_and_login(client, db, level_number=1)
    client.post("/profile/classe", data={"character_class": "arqueiro"})

    resp = client.get("/profile")
    body = resp.data.decode()
    assert "Arqueiro" in body
    assert "Tiro Certeiro" in body


def test_compute_buffs_includes_the_claimed_class_bonus(client, db, app):
    from app.services import loot_service

    user = _create_and_login(client, db, level_number=1)
    client.post("/profile/classe", data={"character_class": "mago"})

    with app.app_context():
        buffs = loot_service.compute_buffs(user.id)
        assert buffs["critBonus"] > 0
