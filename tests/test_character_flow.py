from app.extensions import db
from app.models import User
from app.services import loot_service


def _create_and_login(client, db, email="aluno@example.com"):
    user = User(email=email, username="aluno")
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    client.post("/auth/login", data={"email": email, "password": "senhaforte123"})
    return user


def test_equipamentos_page_requires_login(client, db):
    resp = client.get("/personagem/equipamentos")
    assert resp.status_code in (301, 302)


def test_equipamentos_and_espolios_pages_render(client, db, app):
    _create_and_login(client, db)
    assert client.get("/personagem/equipamentos").status_code == 200
    assert client.get("/personagem/espolios").status_code == 200


def test_equip_via_route_moves_item_into_the_slot(client, db, app):
    user = _create_and_login(client, db)
    with app.app_context():
        item = loot_service.generate_item(user.id)
        item_id, item_slot = item.id, item.slot

    resp = client.post(f"/personagem/equipar/{item_id}", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        equipped = loot_service.list_equipped(user.id)
        assert equipped[item_slot] is not None
        assert equipped[item_slot].id == item_id


def test_cannot_equip_another_users_item_via_route(client, db, app):
    _create_and_login(client, db, email="a@example.com")
    with app.app_context():
        other = User(email="b@example.com", username="outro")
        other.set_password("senhaforte123")
        db.session.add(other)
        db.session.commit()
        other_item = loot_service.generate_item(other.id)
        other_item_id = other_item.id

    resp = client.post(f"/personagem/equipar/{other_item_id}", follow_redirects=True)
    assert resp.status_code == 200  # flashes an error, doesn't crash

    with app.app_context():
        from app.models import ItemInstance
        refreshed = ItemInstance.query.get(other_item_id)
        assert refreshed.is_equipped is False


def test_desequipar_via_route_clears_the_slot(client, db, app):
    user = _create_and_login(client, db)
    with app.app_context():
        item = loot_service.generate_item(user.id)
        loot_service.equip(item.id, user.id)
        slot = item.slot

    resp = client.post(f"/personagem/desequipar/{slot}", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        assert loot_service.list_equipped(user.id)[slot] is None
