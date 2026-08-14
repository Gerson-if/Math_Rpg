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

    user = db.relationship("User")
