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
from app.models import Attempt, ItemInstance, PlayerStats

RARITIES = [
    {"id": "comum", "label": "Comum", "color": "#cbd5e1", "mult": 1.0, "weight": 50},
    {"id": "magico", "label": "Mágico", "color": "#60a5fa", "mult": 1.8, "weight": 30},
    {"id": "raro", "label": "Raro", "color": "#c084fc", "mult": 2.6, "weight": 15},
    {"id": "lendario", "label": "Lendário", "color": "#fbbf24", "mult": 4.0, "weight": 5},
]
RARITY_BY_ID = {r["id"]: r for r in RARITIES}

# A rare item some jogador ainda no nível 1 shouldn't be able to slap on —
# gates equipping (not owning/rolling) by player level, aligned to the same
# rank thresholds already shown on the ranking ladder (Bronze/Prata/Ouro)
# so the number means something the player already recognizes. Keeps
# powerful gear tied to real progress instead of pure drop luck.
MIN_LEVEL_BY_RARITY = {"comum": 1, "magico": 5, "raro": 10, "lendario": 20}

# Selling converts an item you don't want into a small amount of gold,
# permanent like discarding — see app/services/market_service.py for where
# that gold gets spent (the kingdom's own rotating shop, and other
# players' marketplace listings).
GOLD_BY_RARITY = {"comum": 5, "magico": 15, "raro": 40, "lendario": 100}

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


def _pick_template_for(user_id: int) -> dict:
    """Weighted template pick, nudged toward the player's own class buff
    type (classes_service.CLASSES[...]["buff_type"]) so drops feel like
    *your* class's gear more often — not a hard restriction, an item of
    any type is still freely equippable/tradeable by anyone, this just
    changes the odds. Deferred imports: classes.py itself imports
    PASSIVE_BASE from this module, so importing it back at module load
    time would be circular — safe here since generate_item is only ever
    called well after both modules have finished loading."""
    from app.models import Profile
    from app.services import classes as classes_service

    profile = Profile.query.filter_by(user_id=user_id).first()
    class_key = profile.character_class if profile else None
    buff_type = classes_service.CLASSES.get(class_key, {}).get("buff_type") if class_key else None
    if not buff_type:
        return random.choice(ITEM_TEMPLATES)

    weights = [3.0 if t["passive_type"] == buff_type else 1.0 for t in ITEM_TEMPLATES]
    return random.choices(ITEM_TEMPLATES, weights=weights, k=1)[0]


def generate_item(user_id: int) -> ItemInstance:
    """Rolls a random item (weighted toward the player's class — see
    _pick_template_for) and persists it (unequipped) for the user."""
    template = _pick_template_for(user_id)
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


def player_level(user_id: int) -> int:
    stats = PlayerStats.query.filter_by(user_id=user_id).first()
    if stats and stats.level:
        return stats.level.number
    return 1


def equip(item_id: int, user_id: int) -> ItemInstance:
    item = ItemInstance.query.filter_by(id=item_id, user_id=user_id).first()
    if item is None:
        raise ValueError("Item não encontrado.")

    min_level = MIN_LEVEL_BY_RARITY.get(item.rarity, 1)
    if player_level(user_id) < min_level:
        rarity_label = RARITY_BY_ID.get(item.rarity, {}).get("label", item.rarity)
        raise ValueError(
            f"Equipamento {rarity_label} exige nível {min_level} — continue praticando para desbloqueá-lo."
        )

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


def discard(item_id: int, user_id: int) -> None:
    """Deletes an unequipped item for good — no undo, matching the "jogar
    fora" framing. Equipped items must be unequipped first (see unequip())
    so a discard can never silently drop an active buff mid-battle-prep."""
    item = ItemInstance.query.filter_by(id=item_id, user_id=user_id).first()
    if item is None:
        raise ValueError("Item não encontrado.")
    if item.is_equipped:
        raise ValueError("Desequipe o item antes de descartá-lo.")
    db.session.delete(item)
    db.session.commit()


def sell(item_id: int, user_id: int) -> int:
    """Deletes an unequipped item and credits gold scaled by rarity.
    Returns the amount of gold gained."""
    item = ItemInstance.query.filter_by(id=item_id, user_id=user_id).first()
    if item is None:
        raise ValueError("Item não encontrado.")
    if item.is_equipped:
        raise ValueError("Desequipe o item antes de vendê-lo.")

    amount = GOLD_BY_RARITY.get(item.rarity, 0)
    stats = PlayerStats.query.filter_by(user_id=user_id).first()
    if stats is None:
        stats = PlayerStats(user_id=user_id)
        db.session.add(stats)
    stats.gold = (stats.gold or 0) + amount

    db.session.delete(item)
    db.session.commit()
    return amount


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
    """All buffs (equipment + class) affecting this user's cosmetic combat
    presentation. Merges app.services.classes.class_buff in alongside
    equipment so both stack the same way through one dict."""
    from app.models import Profile
    from app.services import classes as classes_service

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

    profile = Profile.query.filter_by(user_id=user_id).first()
    if profile is not None:
        class_bonus = classes_service.class_buff(profile.character_class, profile.class_tier_claimed)
        for key, value in class_bonus.items():
            buffs[key] += value
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
