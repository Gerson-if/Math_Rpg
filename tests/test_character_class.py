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


def test_can_choose_class_is_true_only_before_a_first_pick():
    assert classes.can_choose_class(None) is True
    assert classes.can_choose_class("") is True
    assert classes.can_choose_class("guerreiro") is False


def test_switch_class_cost_is_zero_for_a_first_pick_and_flat_otherwise():
    assert classes.switch_class_cost(None) == 0
    assert classes.switch_class_cost("guerreiro") == classes.SWITCH_CLASS_GOLD_COST
    assert classes.switch_class_cost("guerreiro") > 0


def test_ability_for_returns_the_named_ability_for_the_tier():
    assert classes.ability_for("guerreiro", 0) == "Golpe Poderoso"
    assert classes.ability_for("guerreiro", 2) == "Ira Implacável"
    assert classes.ability_for("nao-existe", 0) is None


def test_display_for_returns_the_evolved_name_and_icon_per_tier():
    tier0 = classes.display_for("guerreiro", 0)
    tier1 = classes.display_for("guerreiro", 1)
    tier2 = classes.display_for("guerreiro", 2)
    assert tier0["name"] == "Guerreiro"
    assert tier1["name"] == "Cavaleiro"
    assert tier2["name"] == "Campeão Real"
    # Evolving changes identity, never what the class is good at.
    assert tier0["color"] == tier1["color"] == tier2["color"]
    assert tier0["buff_type"] == tier1["buff_type"] == tier2["buff_type"]
    assert tier0["icon"] != tier1["icon"] != tier2["icon"]


def test_display_for_falls_back_to_the_base_class_for_an_out_of_range_tier():
    base = classes.CLASSES["mago"]
    assert classes.display_for("mago", 99) == base


def test_display_for_returns_none_for_an_unknown_class():
    assert classes.display_for("nao-existe", 0) is None
    assert classes.display_for(None, 0) is None


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

def test_choosing_a_class_for_the_first_time_is_free(client, db, app):
    user = _create_and_login(client, db, level_number=1)

    resp = client.get("/profile/classe")
    assert resp.status_code == 200
    assert "Mago" in resp.data.decode()

    resp = client.post("/profile/classe", data={"character_class": "mago"}, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        profile = Profile.query.filter_by(user_id=user.id).first()
        stats = PlayerStats.query.filter_by(user_id=user.id).first()
        assert profile.character_class == "mago"
        assert profile.class_tier_claimed == 0
        assert stats.gold == 0  # first pick never costs anything


def test_choose_class_screen_is_always_reachable_once_a_class_is_claimed(client, db, app):
    """The old "come back once a new tier unlocks" gate is gone —
    evolution is automatic now (see progression_service._update_class_tier);
    this screen exists purely for a deliberate, paid family switch."""
    user = _create_and_login(client, db, level_number=5)
    with app.app_context():
        profile = Profile.query.filter_by(user_id=user.id).first()
        profile.character_class = "guerreiro"
        profile.class_tier_claimed = 0
        db.session.commit()

    resp = client.get("/profile/classe")
    assert resp.status_code == 200
    assert "Trocar de classe" in resp.data.decode()


def test_switching_to_the_same_class_again_is_a_free_no_op(client, db, app):
    user = _create_and_login(client, db, level_number=1)
    client.post("/profile/classe", data={"character_class": "guerreiro"})

    resp = client.post("/profile/classe", data={"character_class": "guerreiro"}, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        stats = PlayerStats.query.filter_by(user_id=user.id).first()
        assert stats.gold == 0


def test_switching_to_a_different_class_requires_enough_gold(client, db, app):
    user = _create_and_login(client, db, level_number=1)
    client.post("/profile/classe", data={"character_class": "guerreiro"})
    with app.app_context():
        stats = PlayerStats.query.filter_by(user_id=user.id).first()
        stats.gold = classes.SWITCH_CLASS_GOLD_COST - 1  # not quite enough
        db.session.commit()

    resp = client.post("/profile/classe", data={"character_class": "mago"}, follow_redirects=True)
    assert resp.status_code == 200
    assert "Ouro insuficiente" in resp.data.decode()

    with app.app_context():
        profile = Profile.query.filter_by(user_id=user.id).first()
        assert profile.character_class == "guerreiro"  # unchanged


def test_switching_to_a_different_class_charges_gold_and_keeps_the_earned_tier(client, db, app):
    user = _create_and_login(client, db, level_number=25)  # already tier 2
    client.post("/profile/classe", data={"character_class": "guerreiro"})
    with app.app_context():
        stats = PlayerStats.query.filter_by(user_id=user.id).first()
        stats.gold = 500
        db.session.commit()

    resp = client.post("/profile/classe", data={"character_class": "clerigo"}, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        profile = Profile.query.filter_by(user_id=user.id).first()
        stats = PlayerStats.query.filter_by(user_id=user.id).first()
        assert profile.character_class == "clerigo"
        # Switching preserves the tier their level already earns — not
        # reset to 0, since nothing about their level actually changed.
        assert profile.class_tier_claimed == 2
        assert stats.gold == 500 - classes.SWITCH_CLASS_GOLD_COST


def test_profile_page_shows_the_chosen_class_and_ability(client, db):
    _create_and_login(client, db, level_number=1)
    client.post("/profile/classe", data={"character_class": "arqueiro"})

    resp = client.get("/profile")
    body = resp.data.decode()
    assert "Arqueiro" in body
    assert "Tiro Certeiro" in body


def test_profile_page_shows_the_evolved_class_name_at_a_higher_tier(client, db, app):
    user = _create_and_login(client, db, level_number=10)
    with app.app_context():
        profile = Profile.query.filter_by(user_id=user.id).first()
        profile.character_class = "guerreiro"
        profile.class_tier_claimed = 1
        db.session.commit()

    resp = client.get("/profile")
    body = resp.data.decode()
    assert "Cavaleiro" in body


def test_compute_buffs_includes_the_claimed_class_bonus(client, db, app):
    from app.services import loot_service

    user = _create_and_login(client, db, level_number=1)
    client.post("/profile/classe", data={"character_class": "mago"})

    with app.app_context():
        buffs = loot_service.compute_buffs(user.id)
        assert buffs["critBonus"] > 0
