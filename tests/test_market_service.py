from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import User, ItemInstance, PlayerStats, ShopOffer
from app.services import loot_service, market_service


def _make_user(username="trader"):
    user = User(email=f"{username}@example.com", username=username)
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.flush()
    return user


def _give_gold(user, amount):
    stats = PlayerStats.query.filter_by(user_id=user.id).first()
    if stats is None:
        stats = PlayerStats(user_id=user.id)
        db.session.add(stats)
    stats.gold = amount
    db.session.commit()


# --- Loja do Reino (NPC shop) -------------------------------------------

def test_get_shop_stock_generates_a_fresh_batch_when_empty(app, db):
    with app.app_context():
        stock = market_service.get_shop_stock()
        assert len(stock) == market_service.SHOP_SIZE
        assert all(o.price > 0 for o in stock)


def test_get_shop_stock_does_not_regenerate_when_still_fresh(app, db):
    with app.app_context():
        first = market_service.get_shop_stock()
        first_ids = {o.id for o in first}
        second = market_service.get_shop_stock()
        second_ids = {o.id for o in second}
        assert first_ids == second_ids


def test_get_shop_stock_refreshes_once_stale(app, db):
    with app.app_context():
        market_service.get_shop_stock()
        # Simulate the batch aging past the refresh interval. SQLite
        # reuses row ids after a full DELETE, so comparing ids across the
        # refresh isn't reliable — compare timestamps instead.
        stale_cutoff = datetime.utcnow() - market_service.SHOP_REFRESH_INTERVAL - timedelta(hours=1)
        ShopOffer.query.update({ShopOffer.created_at: stale_cutoff})
        db.session.commit()

        refreshed = market_service.get_shop_stock()
        assert all(o.created_at > stale_cutoff for o in refreshed)


def test_buy_from_shop_deducts_gold_and_grants_the_item(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()
        _give_gold(user, 1000)

        offer = market_service.get_shop_stock()[0]
        offer_id, price = offer.id, offer.price

        item = market_service.buy_from_shop(offer_id, user.id)

        stats = PlayerStats.query.filter_by(user_id=user.id).first()
        assert stats.gold == 1000 - price
        assert item.user_id == user.id
        assert item.is_equipped is False
        assert ShopOffer.query.filter_by(id=offer_id).first() is None


def test_buy_from_shop_rejects_insufficient_gold(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()
        _give_gold(user, 0)

        offer = market_service.get_shop_stock()[0]
        with pytest.raises(ValueError):
            market_service.buy_from_shop(offer.id, user.id)


def test_buy_from_shop_rejects_an_already_bought_offer(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()
        _give_gold(user, 10000)

        offer = market_service.get_shop_stock()[0]
        market_service.buy_from_shop(offer.id, user.id)
        with pytest.raises(ValueError):
            market_service.buy_from_shop(offer.id, user.id)


# --- Loja dos Jogadores (peer marketplace) -------------------------------

def test_list_for_sale_marks_the_item_listed(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()
        item = loot_service.generate_item(user.id)

        market_service.list_for_sale(item.id, user.id, 50)

        assert item.is_listed is True
        assert item.list_price == 50
        assert item.listed_at is not None


def test_list_for_sale_rejects_an_equipped_item(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()
        item = loot_service.generate_item(user.id)
        item.rarity = "comum"
        db.session.commit()
        loot_service.equip(item.id, user.id)

        with pytest.raises(ValueError):
            market_service.list_for_sale(item.id, user.id, 50)


def test_list_for_sale_rejects_a_non_positive_price(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()
        item = loot_service.generate_item(user.id)

        with pytest.raises(ValueError):
            market_service.list_for_sale(item.id, user.id, 0)


def test_cancel_listing_returns_the_item_to_normal_inventory(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()
        item = loot_service.generate_item(user.id)
        market_service.list_for_sale(item.id, user.id, 50)

        market_service.cancel_listing(item.id, user.id)

        assert item.is_listed is False
        assert item.list_price is None
        assert item in loot_service.list_unequipped(user.id)


def test_list_market_listings_excludes_the_sellers_own_items(app, db):
    with app.app_context():
        seller = _make_user("seller")
        buyer = _make_user("buyer")
        db.session.commit()
        item = loot_service.generate_item(seller.id)
        market_service.list_for_sale(item.id, seller.id, 50)

        as_seller = market_service.list_market_listings(exclude_user_id=seller.id)
        as_buyer = market_service.list_market_listings(exclude_user_id=buyer.id)

        assert item not in as_seller
        assert item in as_buyer


def test_expire_stale_listings_returns_old_listings_to_the_seller(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()
        item = loot_service.generate_item(user.id)
        market_service.list_for_sale(item.id, user.id, 50)
        item.listed_at = datetime.utcnow() - market_service.LISTING_DURATION - timedelta(hours=1)
        db.session.commit()

        expired_count = market_service.expire_stale_listings()

        assert expired_count == 1
        assert item.is_listed is False
        assert item.list_price is None


def test_buy_listing_transfers_item_and_gold_between_players(app, db):
    with app.app_context():
        seller = _make_user("seller2")
        buyer = _make_user("buyer2")
        db.session.commit()
        _give_gold(buyer, 100)

        item = loot_service.generate_item(seller.id)
        market_service.list_for_sale(item.id, seller.id, 40)

        bought = market_service.buy_listing(item.id, buyer.id)

        assert bought.user_id == buyer.id
        assert bought.is_listed is False

        buyer_stats = PlayerStats.query.filter_by(user_id=buyer.id).first()
        seller_stats = PlayerStats.query.filter_by(user_id=seller.id).first()
        assert buyer_stats.gold == 60
        assert seller_stats.gold == 40


def test_buy_listing_rejects_buying_your_own_item(app, db):
    with app.app_context():
        user = _make_user()
        db.session.commit()
        _give_gold(user, 1000)
        item = loot_service.generate_item(user.id)
        market_service.list_for_sale(item.id, user.id, 40)

        with pytest.raises(ValueError):
            market_service.buy_listing(item.id, user.id)


def test_buy_listing_rejects_insufficient_gold(app, db):
    with app.app_context():
        seller = _make_user("seller3")
        buyer = _make_user("buyer3")
        db.session.commit()
        _give_gold(buyer, 5)
        item = loot_service.generate_item(seller.id)
        market_service.list_for_sale(item.id, seller.id, 40)

        with pytest.raises(ValueError):
            market_service.buy_listing(item.id, buyer.id)
        assert ItemInstance.query.filter_by(id=item.id).first().user_id == seller.id
