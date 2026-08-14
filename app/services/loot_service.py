"""Loot & equipment — ported from the reference battle template, kept
DB-backed (unlike the reference's in-memory arrays) so the "chest" survives
a page reload. Buffs from equipped items only ever affect the *cosmetic*
combat presentation (combo/crit-flourish/fury pacing on the client, plus
the server-side crit-chance roll below) — never real XP/mastery. See the
plan/README for why: an educational app shouldn't reward gear-grinding
with faster real progression.
"""
import random
from datetime import datetime, timedelta
from typing import TypedDict

from app.extensions import db
from app.models import Attempt, ItemInstance

RARITIES = [
    {"id": "comum", "label": "Comum", "color": "#cbd5e1", "mult": 1.0, "weight": 50},
    {"id": "magico", "label": "Mágico", "color": "#60a5fa", "mult": 1.8, "weight": 30},
    {"id": "raro", "label": "Raro", "color": "#c084fc", "mult": 2.6, "weight": 15},
    {"id": "lendario", "label": "Lendário", "color": "#fbbf24", "mult": 4.0, "weight": 5},
]
_RARITY_BY_ID = {r["id"]: r for r in RARITIES}

# base passive value per point of rarity multiplier — mirrors PASSIVOS in
# the reference template. Keys match ItemInstance.passive_type.
PASSIVE_BASE = {
    "dano": 0.04,
    "critico": 0.03,
    "furia": 3.0,
    "combo": 0.015,
    "vida": 8.0,
    "vampirismo": 0.05,
}

ITEM_TEMPLATES = [
    {"slot": "arma", "name": "Lâmina Encantada", "icon_key": "fa-khanda", "passive_type": "dano"},
    {"slot": "arma", "name": "Cajado Arcano", "icon_key": "fa-wand-magic-sparkles", "passive_type": "critico"},
    {"slot": "anel", "name": "Anel do Encadeamento", "icon_key": "fa-ring", "passive_type": "combo"},
    {"slot": "anel", "name": "Anel da Fúria", "icon_key": "fa-ring", "passive_type": "furia"},
    {"slot": "amuleto", "name": "Amuleto da Vitalidade", "icon_key": "fa-gem", "passive_type": "vida"},
    {"slot": "amuleto", "name": "Relicário Vampírico", "icon_key": "fa-droplet", "passive_type": "vampirismo"},
    {"slot": "armadura", "name": "Couraça de Ferro", "icon_key": "fa-shield", "passive_type": "vida"},
    {"slot": "armadura", "name": "Manto das Sombras", "icon_key": "fa-mask", "passive_type": "critico"},
    {"slot": "capacete", "name": "Elmo do Guardião", "icon_key": "fa-hat-wizard", "passive_type": "vida"},
    {"slot": "capacete", "name": "Coroa Arcana", "icon_key": "fa-crown", "passive_type": "furia"},
    {"slot": "botas", "name": "Botas Élficas", "icon_key": "fa-shoe-prints", "passive_type": "combo"},
    {"slot": "botas", "name": "Grevas Flamejantes", "icon_key": "fa-shoe-prints", "passive_type": "dano"},
]

# How much bonus crit chance the "critico" passive grants per point of raw
# passive_value (its value is already `PASSIVE_BASE["critico"] * rarity.mult`,
# i.e. already a probability-scale number — used directly, no extra scaling).
BASE_CRIT_CHANCE = 0.15
LOOT_CHANCE_ON_CRIT = 0.22
BOSS_KILL_RECENCY_MINUTES = 5


class Buffs(TypedDict):
    danoPct: float
    critBonus: float
    furiaBonus: float
    comboBonus: float
    vidaBonus: float
    vampirismoPct: float


def roll_rarity() -> dict:
    total = sum(r["weight"] for r in RARITIES)
    roll = random.uniform(0, total)
    for r in RARITIES:
        if roll < r["weight"]:
            return r
        roll -= r["weight"]
    return RARITIES[0]


def generate_item(user_id: int) -> ItemInstance:
    """Rolls a random item and persists it (unequipped) for the user."""
    template = random.choice(ITEM_TEMPLATES)
    rarity = roll_rarity()
    value = PASSIVE_BASE[template["passive_type"]] * rarity["mult"]
    item = ItemInstance(
        user_id=user_id,
        slot=template["slot"],
        name=template["name"],
        icon_key=template["icon_key"],
        passive_type=template["passive_type"],
        passive_value=value,
        rarity=rarity["id"],
        is_equipped=False,
    )
    db.session.add(item)
    db.session.commit()
    return item


def equip(item_id: int, user_id: int) -> ItemInstance:
    item = ItemInstance.query.filter_by(id=item_id, user_id=user_id).first()
    if item is None:
        raise ValueError("Item não encontrado.")
    # Unequip whatever else is in that slot first (one item per slot).
    ItemInstance.query.filter_by(
        user_id=user_id, slot=item.slot, is_equipped=True
    ).update({"is_equipped": False})
    item.is_equipped = True
    db.session.commit()
    return item


def unequip(user_id: int, slot: str) -> None:
    ItemInstance.query.filter_by(
        user_id=user_id, slot=slot, is_equipped=True
    ).update({"is_equipped": False})
    db.session.commit()


def list_unequipped(user_id: int, rarity: str | None = None) -> list[ItemInstance]:
    q = ItemInstance.query.filter_by(user_id=user_id, is_equipped=False)
    if rarity:
        q = q.filter_by(rarity=rarity)
    return q.order_by(ItemInstance.created_at.desc()).all()


def list_equipped(user_id: int) -> dict[str, ItemInstance | None]:
    rows = ItemInstance.query.filter_by(user_id=user_id, is_equipped=True).all()
    by_slot = {row.slot: row for row in rows}
    return {slot: by_slot.get(slot) for slot in ItemInstance.SLOTS}


def compute_buffs(user_id: int) -> Buffs:
    buffs: Buffs = {
        "danoPct": 0.0, "critBonus": 0.0, "furiaBonus": 0.0,
        "comboBonus": 0.0, "vidaBonus": 0.0, "vampirismoPct": 0.0,
    }
    key_by_passive = {
        "dano": "danoPct", "critico": "critBonus", "furia": "furiaBonus",
        "combo": "comboBonus", "vida": "vidaBonus", "vampirismo": "vampirismoPct",
    }
    for item in list_equipped(user_id).values():
        if item is None:
            continue
        buffs[key_by_passive[item.passive_type]] += item.passive_value
    return buffs


def roll_crit(user_id: int) -> bool:
    buffs = compute_buffs(user_id)
    return random.random() < (BASE_CRIT_CHANCE + buffs["critBonus"])


def claim_boss_kill_loot(user_id: int, topic_id: int) -> ItemInstance:
    """Guaranteed item for cosmetically defeating the boss. Doesn't try to
    validate the exact client-side combo/damage math (fragile, and would
    drift out of sync every time combat numbers are tuned) — proportional
    integrity check instead: a real correct Attempt for this topic in the
    last few minutes. Rate limiting on the route is the other half of
    keeping this from being spammed."""
    recent_correct = (
        Attempt.query.filter(
            Attempt.user_id == user_id,
            Attempt.topic_id == topic_id,
            Attempt.is_correct.is_(True),
            Attempt.created_at >= datetime.utcnow() - timedelta(minutes=BOSS_KILL_RECENCY_MINUTES),
        )
        .first()
    )
    if recent_correct is None:
        raise ValueError("Nenhuma resposta correta recente encontrada para este tópico.")
    return generate_item(user_id)
