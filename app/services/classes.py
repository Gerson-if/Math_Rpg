"""Character classes: chosen freely the first time, then re-chosen (same
class or a different one) only when a new ability tier unlocks by level —
"escolher classe, e quando chegar a um determinado nível, pode mudar de
classe e ganha uma nova habilidade". Like loot_service's equipment buffs,
a class's bonus only ever affects the *cosmetic* battle presentation
(crit chance, combo, fury, etc. — see loot_service.compute_buffs, which
merges this in) — never real XP or mastery.
"""
from typing import TypedDict

from app.services.loot_service import PASSIVE_BASE


class CharacterClass(TypedDict):
    name: str
    icon: str  # FontAwesome solid class
    color: str  # Tailwind color token
    buff_type: str  # key into loot_service.PASSIVE_BASE / Buffs


CLASSES: dict[str, CharacterClass] = {
    "guerreiro": {"name": "Guerreiro", "icon": "fa-khanda", "color": "red-400", "buff_type": "dano"},
    "mago": {"name": "Mago", "icon": "fa-hat-wizard", "color": "purple-400", "buff_type": "critico"},
    "arqueiro": {"name": "Arqueiro", "icon": "fa-bullseye", "color": "green-400", "buff_type": "combo"},
    "clerigo": {"name": "Clérigo", "icon": "fa-cross", "color": "yellow-300", "buff_type": "vida"},
    "ladino": {"name": "Ladino", "icon": "fa-user-ninja", "color": "stone-300", "buff_type": "vampirismo"},
}

# Ability tiers, unlocked by level — index matches ABILITY_TIERS /
# CLASS_ABILITIES entries. Tier 0 (level 1) is the free starting pick
# everyone can make immediately; tiers 1/2 line up with the existing
# "Aventureiro Experiente" (nível 10) / "Herói do Reino" (nível 25)
# achievements from scripts/seed.py, so the milestones already feel
# established in-game.
ABILITY_TIERS = [
    {"level": 1, "label": "Iniciante", "mult": 1.0},
    {"level": 10, "label": "Adepto", "mult": 2.0},
    {"level": 25, "label": "Mestre", "mult": 3.5},
]

CLASS_ABILITIES: dict[str, list[str]] = {
    "guerreiro": ["Golpe Poderoso", "Fúria de Batalha", "Ira Implacável"],
    "mago": ["Centelha Arcana", "Rajada de Gelo", "Meteoro Arcano"],
    "arqueiro": ["Tiro Certeiro", "Chuva de Flechas", "Olho de Águia"],
    "clerigo": ["Bênção Menor", "Cura Radiante", "Luz Divina"],
    "ladino": ["Golpe Furtivo", "Passos Silenciosos", "Assassinato"],
}

# One line of flavor per class, tying it into "As Crônicas de Arith" (see
# app/services/lore.py) — how this class's aprendiz would carry the same
# quest to find the princesa Sela differently. Purely narrative, shown on
# the class picker and the profile page.
CLASS_LORE: dict[str, str] = {
    "guerreiro": "Você avança pela força bruta — cada golpe certeiro é mais uma prova de que a coragem ainda vale algo em Arith.",
    "mago": "Você enxerga os padrões escondidos nos números, os mesmos que aprisionam Sela — e sabe que a resposta certa, no instante certo, pode desfazer qualquer feitiço.",
    "arqueiro": "Sua precisão nunca falha duas vezes seguidas — cada acerto encadeado no anterior, como os passos de quem já decidiu não recuar.",
    "clerigo": "Você carrega a fé do reino como um escudo — onde outros veem apenas números, você vê pessoas esperando para serem salvas.",
    "ladino": "Você aprendeu a tirar proveito de cada erro do inimigo — inclusive os do próprio Mercador das Sombras.",
}


def current_tier(level_number: int) -> int:
    """Highest ability tier index this level qualifies for."""
    tier = 0
    for i, t in enumerate(ABILITY_TIERS):
        if level_number >= t["level"]:
            tier = i
    return tier


def can_choose_class(level_number: int, class_tier_claimed: int) -> bool:
    """True if the player has never picked a class yet, or a new tier has
    unlocked since their last pick."""
    if class_tier_claimed < 0:
        return True
    return current_tier(level_number) > class_tier_claimed


def ability_for(class_key: str, tier: int) -> str | None:
    names = CLASS_ABILITIES.get(class_key)
    if not names or tier >= len(names):
        return None
    return names[tier]


def class_buff(class_key: str | None, tier_claimed: int) -> dict[str, float]:
    """The flat bonus a claimed class+tier adds to one buff category —
    same units/scale as loot_service.PASSIVE_BASE so it stacks naturally
    with equipment. Nothing claimed yet (no class chosen) contributes 0."""
    empty = {"danoPct": 0.0, "critBonus": 0.0, "furiaBonus": 0.0, "comboBonus": 0.0, "vidaBonus": 0.0, "vampirismoPct": 0.0}
    if not class_key or class_key not in CLASSES or tier_claimed < 0:
        return empty

    key_by_buff_type = {
        "dano": "danoPct", "critico": "critBonus", "furia": "furiaBonus",
        "combo": "comboBonus", "vida": "vidaBonus", "vampirismo": "vampirismoPct",
    }
    buff_type = CLASSES[class_key]["buff_type"]
    tier_index = min(tier_claimed, len(ABILITY_TIERS) - 1)
    mult = ABILITY_TIERS[tier_index]["mult"]
    empty[key_by_buff_type[buff_type]] = PASSIVE_BASE[buff_type] * mult
    return empty
