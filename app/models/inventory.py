from app.extensions import db
from app.models.base import TimestampMixin


class ItemInstance(db.Model, TimestampMixin):
    """A single procedurally-rolled equipment drop owned by a player.
    Denormalized on purpose (name/icon/passive copied at roll time, not a
    foreign key to a catalog) — see app/services/loot_service.py, which
    generates a continuous `passive_value` per roll (base * rarity
    multiplier), so there's no fixed catalog row to point at."""

    __tablename__ = "item_instances"

    SLOTS = ("arma", "anel", "amuleto", "armadura", "capacete", "botas")

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    slot = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    icon_key = db.Column(db.String(40), nullable=False)  # FontAwesome class, e.g. "fa-khanda"
    passive_type = db.Column(db.String(20), nullable=False)
    passive_value = db.Column(db.Float, nullable=False)
    rarity = db.Column(db.String(20), nullable=False)
    is_equipped = db.Column(db.Boolean, default=False, nullable=False)

    # Player-to-player marketplace ("Loja") — see loot_service.list_for_sale
    # etc. A listed item is still owned by the seller (still shows up as
    # theirs) until someone buys it or the listing expires back to them.
    is_listed = db.Column(db.Boolean, default=False, nullable=False)
    list_price = db.Column(db.Integer, nullable=True)
    listed_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")


class ShopOffer(db.Model, TimestampMixin):
    """The kingdom's own rotating stock ("Loja do Reino") — unowned,
    system-generated items purchasable with gold, refreshed periodically
    (see loot_service.get_shop_stock). Denormalized the same way as
    ItemInstance; turns into a real ItemInstance for the buyer once sold,
    and is removed from stock so nobody can buy the same offer twice."""

    __tablename__ = "shop_offers"

    id = db.Column(db.Integer, primary_key=True)
    slot = db.Column(db.String(20), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    icon_key = db.Column(db.String(40), nullable=False)
    passive_type = db.Column(db.String(20), nullable=False)
    passive_value = db.Column(db.Float, nullable=False)
    rarity = db.Column(db.String(20), nullable=False)
    price = db.Column(db.Integer, nullable=False)
