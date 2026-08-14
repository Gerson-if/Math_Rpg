from app.extensions import db
from app.models import User, PlayerStats, ItemInstance
from app.services import loot_service, market_service


def _create_and_login(client, db, email="mkt@example.com", username="mkt"):
    user = User(email=email, username=username)
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    client.post("/auth/login", data={"email": email, "password": "senhaforte123"})
    return user


def test_market_page_requires_login(client, db):
    resp = client.get("/mercado/")
    assert resp.status_code in (301, 302)


def test_market_page_renders_with_shop_stock(client, db, app):
    _create_and_login(client, db)
    resp = client.get("/mercado/")
    assert resp.status_code == 200
    assert "Loja do Reino" in resp.data.decode()
    assert "Loja dos Jogadores" in resp.data.decode()


def test_buy_from_shop_via_route_grants_the_item(client, db, app):
    user = _create_and_login(client, db)
    with app.app_context():
        db.session.add(PlayerStats(user_id=user.id, gold=10000))
        db.session.commit()
        offer_id = market_service.get_shop_stock()[0].id

    resp = client.post(f"/mercado/comprar-da-loja/{offer_id}", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        stats = PlayerStats.query.filter_by(user_id=user.id).first()
        assert stats.gold < 10000


def test_anunciar_via_route_lists_the_item(client, db, app):
    user = _create_and_login(client, db)
    with app.app_context():
        item = loot_service.generate_item(user.id)
        item_id = item.id

    resp = client.post(f"/mercado/anunciar/{item_id}", data={"price": "30"}, follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        item = ItemInstance.query.filter_by(id=item_id).first()
        assert item.is_listed is True
        assert item.list_price == 30


def test_buy_listing_via_route_transfers_ownership(client, db, app):
    seller = User(email="seller@example.com", username="seller")
    seller.set_password("senhaforte123")
    db.session.add(seller)
    db.session.commit()

    with app.app_context():
        item = loot_service.generate_item(seller.id)
        market_service.list_for_sale(item.id, seller.id, 20)
        item_id = item.id

    buyer = _create_and_login(client, db, email="buyer@example.com", username="buyer")
    with app.app_context():
        db.session.add(PlayerStats(user_id=buyer.id, gold=100))
        db.session.commit()

    resp = client.post(f"/mercado/comprar/{item_id}", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        item = ItemInstance.query.filter_by(id=item_id).first()
        assert item.user_id == buyer.id
        assert item.is_listed is False
