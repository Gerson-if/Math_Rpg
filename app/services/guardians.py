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

# Every topic in a subject used to fight the exact same named guardian,
# regardless of whether it was the subject's easiest or hardest topic —
# reaching "the boss" never felt earned since it was already the first
# fight too. Earlier topics now fight a lesser minion (same icon/color,
# lesser name) and only the subject's LAST topic — its real final exam —
# faces the actual guardian. See for_topic().
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

_FALLBACK: Guardian = {"name": "Guardião do Conhecimento", "icon": "fa-dragon", "color": "purple-400"}


def for_subject(subject_slug: str) -> Guardian:
    return GUARDIANS.get(subject_slug, _FALLBACK)


def for_topic(topic) -> tuple[Guardian, bool]:
    """The enemy shown for one specific topic's battle. Returns
    (display_guardian, is_final_boss) — is_final_boss is True only for
    the subject's last topic (by Topic.order), which fights the real
    named guardian; every earlier topic fights a same-icon/color minion
    instead, so the guardian fight reads as an escalation, not a repeat."""
    base = for_subject(topic.subject.slug)
    topic_orders = [t.order for t in topic.subject.topics]
    is_final = bool(topic_orders) and topic.order == max(topic_orders)
    if is_final:
        return base, True
    minion: Guardian = {
        "name": MINION_NAMES.get(topic.subject.slug, _MINION_FALLBACK),
        "icon": base["icon"],
        "color": base["color"],
    }
    return minion, False
