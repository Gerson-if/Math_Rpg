"""The kingdom's economy: two distinct ways to acquire an item with gold,
on top of loot_service's random drops.

- "Loja do Reino" — a rotating NPC shop stock (ShopOffer rows), refreshed
  periodically, bought outright and turned into a real ItemInstance.
- "Loja dos Jogadores" — a peer-to-peer marketplace: a player lists one of
  their own unequipped items (ItemInstance.is_listed/list_price/listed_at)
  for a limited time, another player buys it directly, gold changes hands
  between the two PlayerStats rows.

Buying never bypasses the level gate on *equipping* rare items (see
loot_service.MIN_LEVEL_BY_RARITY) — you can buy/hold anything, same as a
random drop, you just can't equip it early. Keeps this module from
becoming a second place that has to reason about that rule.
"""
import random
from datetime import datetime, timedelta

from app.extensions import db
from app.models import ItemInstance, PlayerStats, ShopOffer
from app.services.loot_service import ITEM_TEMPLATES, PASSIVE_BASE, RARITY_BY_ID, roll_rarity

SHOP_SIZE = 6
SHOP_REFRESH_INTERVAL = timedelta(hours=24)
# Buying costs more than selling gives (same rarity) — otherwise buying
# and instantly re-selling would print gold for free.
BUY_PRICE_BY_RARITY = {"comum": 15, "magico": 45, "raro": 120, "lendario": 300}

LISTING_DURATION = timedelta(days=3)


def _get_or_create_stats(user_id: int) -> PlayerStats:
    stats = PlayerStats.query.filter_by(user_id=user_id).first()
    if stats is None:
        stats = PlayerStats(user_id=user_id)
        db.session.add(stats)
    return stats


# ---------------------------------------------------------------------------
# Loja do Reino — rotating NPC shop
# ---------------------------------------------------------------------------

def _generate_offer() -> ShopOffer:
    template = random.choice(ITEM_TEMPLATES)
    rarity = roll_rarity()
    value = PASSIVE_BASE[template["passive_type"]] * rarity["mult"]
    return ShopOffer(
        slot=template["slot"],
        name=template["name"],
        icon_key=template["icon_key"],
        passive_type=template["passive_type"],
        passive_value=value,
        rarity=rarity["id"],
        price=BUY_PRICE_BY_RARITY[rarity["id"]],
    )


def get_shop_stock() -> list[ShopOffer]:
    """The kingdom shop's current stock, refreshing it first if the last
    batch is stale or the shop has never stocked anything. Refreshing
    lazily (on read) instead of on a cron job keeps this app dependency-
    free — the shop just "catches up" the next time anyone visits it."""
    latest = ShopOffer.query.order_by(ShopOffer.created_at.desc()).first()
    is_stale = latest is None or (datetime.utcnow() - latest.created_at) > SHOP_REFRESH_INTERVAL
    if is_stale:
        ShopOffer.query.delete()
        for _ in range(SHOP_SIZE):
            db.session.add(_generate_offer())
        db.session.commit()
    return ShopOffer.query.order_by(ShopOffer.id).all()


def buy_from_shop(offer_id: int, user_id: int) -> ItemInstance:
    offer = ShopOffer.query.filter_by(id=offer_id).first()
    if offer is None:
        raise ValueError("Esse item não está mais disponível na loja.")

    stats = _get_or_create_stats(user_id)
    if (stats.gold or 0) < offer.price:
        raise ValueError("Ouro insuficiente para comprar este item.")

    stats.gold -= offer.price
    item = ItemInstance(
        user_id=user_id, slot=offer.slot, name=offer.name, icon_key=offer.icon_key,
        passive_type=offer.passive_type, passive_value=offer.passive_value,
        rarity=offer.rarity, is_equipped=False,
    )
    db.session.add(item)
    db.session.delete(offer)
    db.session.commit()
    return item


# ---------------------------------------------------------------------------
# Loja dos Jogadores — peer-to-peer marketplace
# ---------------------------------------------------------------------------

def list_for_sale(item_id: int, user_id: int, price: int) -> ItemInstance:
    item = ItemInstance.query.filter_by(id=item_id, user_id=user_id).first()
    if item is None:
        raise ValueError("Item não encontrado.")
    if item.is_equipped:
        raise ValueError("Desequipe o item antes de anunciá-lo.")
    if item.is_listed:
        raise ValueError("Esse item já está anunciado.")
    if price <= 0:
        raise ValueError("Defina um preço válido.")

    item.is_listed = True
    item.list_price = price
    item.listed_at = datetime.utcnow()
    db.session.commit()
    return item


def cancel_listing(item_id: int, user_id: int) -> None:
    item = ItemInstance.query.filter_by(id=item_id, user_id=user_id, is_listed=True).first()
    if item is None:
        raise ValueError("Anúncio não encontrado.")
    item.is_listed = False
    item.list_price = None
    item.listed_at = None
    db.session.commit()


def expire_stale_listings() -> int:
    """Anything listed past LISTING_DURATION quietly returns to its
    seller's normal inventory — called before every marketplace read so
    stale listings never need a background job to clean up."""
    cutoff = datetime.utcnow() - LISTING_DURATION
    stale = ItemInstance.query.filter(
        ItemInstance.is_listed.is_(True), ItemInstance.listed_at < cutoff
    ).all()
    for item in stale:
        item.is_listed = False
        item.list_price = None
        item.listed_at = None
    if stale:
        db.session.commit()
    return len(stale)


def list_market_listings(exclude_user_id: int | None = None) -> list[ItemInstance]:
    expire_stale_listings()
    q = ItemInstance.query.filter_by(is_listed=True)
    if exclude_user_id is not None:
        q = q.filter(ItemInstance.user_id != exclude_user_id)
    return q.order_by(ItemInstance.listed_at.asc()).all()


def list_my_listings(user_id: int) -> list[ItemInstance]:
    expire_stale_listings()
    return (
        ItemInstance.query.filter_by(user_id=user_id, is_listed=True)
        .order_by(ItemInstance.listed_at.desc())
        .all()
    )


def buy_listing(item_id: int, buyer_id: int) -> ItemInstance:
    item = ItemInstance.query.filter_by(id=item_id, is_listed=True).first()
    if item is None:
        raise ValueError("Anúncio não encontrado ou já expirado.")
    if item.user_id == buyer_id:
        raise ValueError("Você não pode comprar seu próprio item.")

    buyer_stats = _get_or_create_stats(buyer_id)
    if (buyer_stats.gold or 0) < item.list_price:
        raise ValueError("Ouro insuficiente para comprar este item.")

    seller_stats = _get_or_create_stats(item.user_id)
    price = item.list_price
    buyer_stats.gold -= price
    seller_stats.gold = (seller_stats.gold or 0) + price

    item.user_id = buyer_id
    item.is_equipped = False
    item.is_listed = False
    item.list_price = None
    item.listed_at = None
    db.session.commit()
    return item
