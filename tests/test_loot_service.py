from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import User, Subject, Topic, Attempt, ItemInstance, Level, PlayerStats
from app.services import loot_service


def _make_user(username="loot"):
    user = User(email=f"{username}@example.com", username=username)
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.flush()
    return user


def _make_topic(slug="adicao"):
    subject = Subject(slug="operacoes-fundamentais", name="Operações Fundamentais", order=0)
    db.session.add(subject)
    db.session.flush()
    topic = Topic(slug=slug, name="Adição", subject_id=subject.id, order=0, base_difficulty=1)
    db.session.add(topic)
    db.session.flush()
    return topic


def _set_level(user, number):
    level = Level.query.filter_by(number=number).first()
    if level is None:
        level = Level(number=number, xp_required=0)
        db.session.add(level)
        db.session.flush()
    stats = PlayerStats.query.filter_by(user_id=user.id).first()
    if stats is None:
        stats = PlayerStats(user_id=user.id)
        db.session.add(stats)
    stats.level_id = level.id
    db.session.commit()


def test_generate_item_persists_unequipped(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()

        item = loot_service.generate_item(user.id)

        assert item.id is not None
        assert item.is_equipped is False
        assert item.slot in ItemInstance.SLOTS
        assert item.rarity in {r["id"] for r in loot_service.RARITIES}
        assert item.passive_value > 0


def test_rarity_distribution_covers_all_four_tiers(app, db):
    seen = {loot_service.roll_rarity()["id"] for _ in range(400)}
    assert seen == {r["id"] for r in loot_service.RARITIES}


def test_equip_swaps_previous_item_in_same_slot_back_to_inventory(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()

        first = loot_service.generate_item(user.id)
        first.slot = "arma"
        first.rarity = "comum"  # rarity is irrelevant here — pin it so the level gate never interferes
        second = loot_service.generate_item(user.id)
        second.slot = "arma"
        second.rarity = "comum"
        db.session.commit()

        loot_service.equip(first.id, user.id)
        loot_service.equip(second.id, user.id)

        db.session.refresh(first)
        db.session.refresh(second)
        assert first.is_equipped is False
        assert second.is_equipped is True
        assert loot_service.list_equipped(user.id)["arma"].id == second.id


def test_equip_rejects_another_users_item(app, db):
    with app.app_context():
        owner = _make_user("owner")
        intruder = _make_user("intruder")
        db.session.commit()

        item = loot_service.generate_item(owner.id)

        with pytest.raises(ValueError):
            loot_service.equip(item.id, intruder.id)


def test_unequip_clears_the_slot(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()
        item = loot_service.generate_item(user.id)
        item.slot = "anel"
        item.rarity = "comum"  # pin so the level gate never interferes
        db.session.commit()
        loot_service.equip(item.id, user.id)

        loot_service.unequip(user.id, "anel")

        assert loot_service.list_equipped(user.id)["anel"] is None
        assert item in loot_service.list_unequipped(user.id)


def test_compute_buffs_sums_all_equipped_slots(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()

        weapon = ItemInstance(
            user_id=user.id, slot="arma", name="Lâmina", icon_key="fa-khanda",
            passive_type="dano", passive_value=0.1, rarity="raro", is_equipped=True,
        )
        ring = ItemInstance(
            user_id=user.id, slot="anel", name="Anel", icon_key="fa-ring",
            passive_type="critico", passive_value=0.05, rarity="comum", is_equipped=True,
        )
        db.session.add_all([weapon, ring])
        db.session.commit()

        buffs = loot_service.compute_buffs(user.id)
        assert buffs["danoPct"] == pytest.approx(0.1)
        assert buffs["critBonus"] == pytest.approx(0.05)
        assert buffs["furiaBonus"] == 0
        assert buffs["vidaBonus"] == 0


def test_claim_boss_kill_loot_requires_a_recent_correct_attempt(app, db):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()
        db.session.commit()

        with pytest.raises(ValueError):
            loot_service.claim_boss_kill_loot(user.id, topic.id)

        db.session.add(Attempt(
            user_id=user.id, topic_id=topic.id, difficulty=1,
            is_correct=True, response_time_ms=1000,
        ))
        db.session.commit()

        item = loot_service.claim_boss_kill_loot(user.id, topic.id)
        assert item.id is not None


def test_claim_boss_kill_loot_ignores_old_attempts(app, db):
    with app.app_context():
        user = _make_user()
        topic = _make_topic()
        db.session.commit()

        old_attempt = Attempt(
            user_id=user.id, topic_id=topic.id, difficulty=1,
            is_correct=True, response_time_ms=1000,
        )
        db.session.add(old_attempt)
        db.session.flush()
        old_attempt.created_at = datetime.utcnow() - timedelta(hours=1)
        db.session.commit()

        with pytest.raises(ValueError):
            loot_service.claim_boss_kill_loot(user.id, topic.id)


# --- Level gate on equipping rare items -------------------------------

def test_equip_rejects_a_legendary_item_below_the_required_level(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()
        _set_level(user, 1)

        item = loot_service.generate_item(user.id)
        item.rarity = "lendario"
        db.session.commit()

        with pytest.raises(ValueError):
            loot_service.equip(item.id, user.id)
        assert loot_service.list_equipped(user.id)[item.slot] is None


def test_equip_allows_a_legendary_item_once_the_level_is_reached(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()
        _set_level(user, loot_service.MIN_LEVEL_BY_RARITY["lendario"])

        item = loot_service.generate_item(user.id)
        item.rarity = "lendario"
        db.session.commit()

        loot_service.equip(item.id, user.id)
        assert loot_service.list_equipped(user.id)[item.slot].id == item.id


def test_equip_never_gates_common_items(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()
        _set_level(user, 1)

        item = loot_service.generate_item(user.id)
        item.rarity = "comum"
        db.session.commit()

        loot_service.equip(item.id, user.id)
        assert loot_service.list_equipped(user.id)[item.slot].id == item.id


# --- Discard / sell -----------------------------------------------------

def test_discard_removes_an_unequipped_item(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()
        item = loot_service.generate_item(user.id)
        item_id = item.id

        loot_service.discard(item_id, user.id)

        assert ItemInstance.query.filter_by(id=item_id).first() is None


def test_discard_rejects_an_equipped_item(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()
        item = loot_service.generate_item(user.id)
        item.rarity = "comum"
        db.session.commit()
        loot_service.equip(item.id, user.id)

        with pytest.raises(ValueError):
            loot_service.discard(item.id, user.id)
        assert ItemInstance.query.filter_by(id=item.id).first() is not None


def test_sell_removes_item_and_credits_gold_by_rarity(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()
        item = loot_service.generate_item(user.id)
        item.rarity = "raro"
        db.session.commit()
        item_id = item.id

        amount = loot_service.sell(item_id, user.id)

        assert amount == loot_service.GOLD_BY_RARITY["raro"]
        assert ItemInstance.query.filter_by(id=item_id).first() is None
        stats = PlayerStats.query.filter_by(user_id=user.id).first()
        assert stats.gold == amount


def test_sell_rejects_an_equipped_item(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()
        item = loot_service.generate_item(user.id)
        item.rarity = "comum"
        db.session.commit()
        loot_service.equip(item.id, user.id)

        with pytest.raises(ValueError):
            loot_service.sell(item.id, user.id)
        assert ItemInstance.query.filter_by(id=item.id).first() is not None
