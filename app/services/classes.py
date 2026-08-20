"""Character classes: chosen freely the first time, then *evolving on
their own* within the same family as the player levels up — no more
manually re-visiting the class picker at every tier (see
progression_service._update_class_tier, which advances
Profile.class_tier_claimed automatically the moment a new tier is
reached). Switching to a *different* family entirely is a separate,
deliberate action (see SWITCH_CLASS_GOLD_COST) that costs gold, since
that's an identity change, not growth — "escolher classe, e conforme sobe
de nível, evolui dentro da mesma; mudar de classe custa ouro". Like
loot_service's equipment buffs, a class's bonus only ever affects the
*cosmetic* battle presentation (crit chance, combo, fury, etc. — see
loot_service.compute_buffs, which merges this in) — never real XP or
mastery.
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

# The class's own displayed identity per tier — same index as
# ABILITY_TIERS/CLASS_ABILITIES. Tier 0 is just the base CLASSES entry;
# tiers 1/2 are a genuinely different name+icon, not just a stronger
# version of the same portrait, so reaching level 10/25 actually reads as
# "becoming" something new rather than a numeric upgrade. Color and
# buff_type never change across tiers — evolving doesn't change *what*
# the class is good at, only how far along that path you've come.
EVOLVED_NAMES: dict[str, list[str]] = {
    "guerreiro": ["Guerreiro", "Cavaleiro", "Campeão Real"],
    "mago": ["Mago", "Arcanista", "Arquimago"],
    "arqueiro": ["Arqueiro", "Batedor", "Mestre Arqueiro"],
    "clerigo": ["Clérigo", "Paladino", "Bispo Sagrado"],
    "ladino": ["Ladino", "Assassino", "Mestre das Sombras"],
}
EVOLVED_ICONS: dict[str, list[str]] = {
    "guerreiro": ["fa-khanda", "fa-shield-halved", "fa-crown"],
    "mago": ["fa-hat-wizard", "fa-wand-sparkles", "fa-hurricane"],
    "arqueiro": ["fa-bullseye", "fa-crosshairs", "fa-bolt"],
    "clerigo": ["fa-cross", "fa-hands-praying", "fa-sun"],
    "ladino": ["fa-user-ninja", "fa-user-secret", "fa-mask"],
}

# Switching to a *different* class family costs gold (see loot_service.sell
# for where gold actually comes from) — evolving forward within the same
# family, by contrast, is free and automatic. Flat rather than scaled by
# tier: the cost is for the identity change itself, not a refund of
# "progress lost" (there isn't any — see choose_class() preserving the
# equivalent tier in the new family).
SWITCH_CLASS_GOLD_COST = 150

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


def can_choose_class(class_key: str | None) -> bool:
    """True only for a player who has never picked a class yet — the free,
    no-strings first pick. Once a class is chosen it evolves on its own as
    the player levels (see progression_service._update_class_tier); the
    only way to end up with a *different* family after that is the paid
    "Trocar de classe" flow (see switch_class_cost below and
    users.choose_class), not this free first-pick path."""
    return not class_key


def switch_class_cost(current_class_key: str | None) -> int:
    """Gold cost to change family — 0 for the free first pick (nothing to
    switch *from* yet), SWITCH_CLASS_GOLD_COST otherwise. A tiny wrapper so
    callers never have to duplicate the "is this actually a switch"
    check."""
    return 0 if not current_class_key else SWITCH_CLASS_GOLD_COST


def ability_for(class_key: str, tier: int) -> str | None:
    names = CLASS_ABILITIES.get(class_key)
    if not names or tier >= len(names):
        return None
    return names[tier]


def display_for(class_key: str | None, tier: int) -> CharacterClass | None:
    """The evolved name/icon for this class at this tier, falling back to
    the base CLASSES entry for an unknown class or an out-of-range tier
    (e.g. new curriculum added ahead of updating EVOLVED_NAMES) rather
    than breaking. None only if class_key itself isn't a real class."""
    base = CLASSES.get(class_key) if class_key else None
    if base is None:
        return None
    names = EVOLVED_NAMES.get(class_key)
    icons = EVOLVED_ICONS.get(class_key)
    if not names or not icons or tier < 0 or tier >= len(names):
        return base
    return {"name": names[tier], "icon": icons[tier], "color": base["color"], "buff_type": base["buff_type"]}


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
