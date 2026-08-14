"""One distinct "guardian" (name + FontAwesome icon + accent color) per
subject, so the battle arena doesn't show the same generic dragon for
every topic. Purely presentational — keyed by Subject.slug with a
fallback for any subject not listed here (e.g. new curriculum added
without updating this file), so nothing ever breaks for lack of an entry.
"""
from typing import TypedDict


class Guardian(TypedDict):
    name: str
    icon: str  # FontAwesome solid class, e.g. "fa-dragon"
    color: str  # Tailwind color token, e.g. "purple-400"


GUARDIANS: dict[str, Guardian] = {
    "fundamentos": {"name": "Golem Ancestral", "icon": "fa-robot", "color": "stone-300"},
    "tabuada": {"name": "Hidra das Tábuas", "icon": "fa-dragon", "color": "purple-400"},
    "operacoes-fundamentais": {"name": "Quimera Aritmética", "icon": "fa-hippo", "color": "emerald-400"},
    "potenciacao": {"name": "Fênix Exponencial", "icon": "fa-fire", "color": "orange-400"},
    "radiciacao": {"name": "Espectro Glacial", "icon": "fa-ghost", "color": "cyan-300"},
    "fracoes": {"name": "Aracnídeo do Labirinto", "icon": "fa-spider", "color": "violet-400"},
    "numeros-decimais": {"name": "Serpente de Cristal", "icon": "fa-worm", "color": "blue-400"},
    "porcentagem": {"name": "Mercador das Sombras", "icon": "fa-mask", "color": "yellow-400"},
    "algebra": {"name": "Guardião do Castelo Final", "icon": "fa-chess-rook", "color": "red-400"},
}

# Every topic in a subject used to fight the exact same named guardian at
# the exact same strength, regardless of whether it was the subject's
# easiest or hardest topic — reaching "the boss" never felt earned since
# it was already the first fight too, and beating it once made every
# later replay of that same topic feel identical. for_topic() now walks
# three tiers on the way up (minion -> elite minion -> the real guardian)
# and, once the guardian itself has already been beaten at least once,
# a fourth: it comes back stronger.
MINION_NAMES: dict[str, str] = {
    "fundamentos": "Fragmento de Pedra",
    "tabuada": "Cria da Hidra",
    "operacoes-fundamentais": "Servo da Forja",
    "potenciacao": "Faísca da Fênix",
    "radiciacao": "Eco do Espelho",
    "fracoes": "Filhote do Labirinto",
    "numeros-decimais": "Fragmento de Cristal",
    "porcentagem": "Batedor das Sombras",
    "algebra": "Sentinela do Castelo",
}
_MINION_FALLBACK = "Servo do Guardião"

ELITE_MINION_NAMES: dict[str, str] = {
    "fundamentos": "Guardião de Pedra",
    "tabuada": "Serpente da Hidra",
    "operacoes-fundamentais": "Mestre-Forjador",
    "potenciacao": "Chama da Fênix",
    "radiciacao": "Reflexo Sombrio",
    "fracoes": "Tecelão do Labirinto",
    "numeros-decimais": "Lâmina de Cristal",
    "porcentagem": "Emissário das Sombras",
    "algebra": "Guarda-Costas do Castelo",
}
_ELITE_FALLBACK = "Servo Veterano"

# Shown instead of the plain guardian name once the player has already
# beaten that guardian at least once before — see practice() in
# app/mathematics/routes.py, which is the one place with DB access to
# check that (this module stays DB-free, same as mathematics_service).
SUPREME_NAMES: dict[str, str] = {
    "fundamentos": "Golem Ancestral Desperto",
    "tabuada": "Hidra das Tábuas Ressuscitada",
    "operacoes-fundamentais": "Quimera Aritmética Renascida",
    "potenciacao": "Fênix Exponencial Imortal",
    "radiciacao": "Espectro Glacial Eterno",
    "fracoes": "Aracnídeo do Labirinto Ressurgido",
    "numeros-decimais": "Serpente de Cristal Renascida",
    "porcentagem": "Mercador das Sombras Ressuscitado",
    "algebra": "Guardião do Castelo Final Imortal",
}
_SUPREME_FALLBACK = "Guardião Ressuscitado"

_FALLBACK: Guardian = {"name": "Guardião do Conhecimento", "icon": "fa-dragon", "color": "purple-400"}


def for_subject(subject_slug: str) -> Guardian:
    return GUARDIANS.get(subject_slug, _FALLBACK)


def supreme_name_for(subject_slug: str) -> str:
    return SUPREME_NAMES.get(subject_slug, _SUPREME_FALLBACK)


def for_topic(topic) -> tuple[Guardian, str]:
    """The enemy shown for one specific topic's battle. Returns
    (display_guardian, tier), tier one of "minion" / "elite" / "boss".
    Only the subject's LAST topic (by Topic.order) is tier "boss" and
    shows the real named guardian — every topic before it is a minion
    (first half) or an elite minion (second half), same icon/color as
    the guardian but a lesser name, so reaching the guardian reads as an
    escalation instead of a repeat of the very first fight."""
    base = for_subject(topic.subject.slug)
    topics_sorted = sorted(topic.subject.topics, key=lambda t: t.order)
    n = len(topics_sorted)
    idx = next((i for i, t in enumerate(topics_sorted) if t.id == topic.id), n - 1)

    if idx >= n - 1:
        return base, "boss"

    half = max(1, -(-n // 2))  # ceil(n / 2): early topics are minions, later ones elite
    if idx < half:
        name = MINION_NAMES.get(topic.subject.slug, _MINION_FALLBACK)
        tier = "minion"
    else:
        name = ELITE_MINION_NAMES.get(topic.subject.slug, _ELITE_FALLBACK)
        tier = "elite"
    return {"name": name, "icon": base["icon"], "color": base["color"]}, tier
