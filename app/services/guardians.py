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
}

_FALLBACK: Guardian = {"name": "Guardião do Conhecimento", "icon": "fa-dragon", "color": "purple-400"}


def for_subject(subject_slug: str) -> Guardian:
    return GUARDIANS.get(subject_slug, _FALLBACK)
