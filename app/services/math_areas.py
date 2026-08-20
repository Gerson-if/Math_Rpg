"""Maps every topic in the curriculum to the real math sub-area it
actually teaches — not the app's own Subject grouping (which is closer to
"chapter") but the underlying skill (comparação, cálculo mental,
pensamento algébrico, ...), the terms a math teacher would actually use.

This is what app.services.diagnostics_service reads to tell a player
*which skill* to train, not just "which topic has low mastery" — two
different topics inside the same Subject can teach genuinely different
skills (Fundamentos' "contagem" and "comparação" topics are not the same
kind of thinking), and the reverse is also true (the whole Tabuada subject
is really just one skill — cálculo mental — repeated across factors).

Kept as a plain Python module, same as guardians.py/lore.py/mentor_tips.py
— this is curriculum metadata, not something a player or admin ever edits
at runtime, so it doesn't need a DB table like Achievement/Rank do.
"""
from typing import TypedDict


class MathArea(TypedDict):
    name: str
    short_name: str  # tight label for the radar chart's axis tips
    icon: str  # FontAwesome solid class
    color: str  # Tailwind color token, e.g. "purple-400"
    description: str  # what this skill actually is, one sentence


# Insertion order here IS the canonical pedagogical order (roughly what
# scripts/seed.py's Subject.order already encodes, split where one
# Subject actually covers two different skills — see the module
# docstring). diagnostics_service uses this order for the radar chart's
# axes and AREA_PREREQUISITES below, instead of the diagnostic report's
# own weakest-first sort, so the chart's shape stays stable between
# visits regardless of which areas happen to be weakest today.
AREAS: dict[str, MathArea] = {
    "senso-numerico": {
        "name": "Senso Numérico e Contagem",
        "short_name": "Contagem",
        "icon": "fa-hashtag",
        "color": "stone-300",
        "description": "Reconhecer, contar e nomear quantidades.",
    },
    "comparacao": {
        "name": "Comparação e Ordenação",
        "short_name": "Comparação",
        "icon": "fa-scale-balanced",
        "color": "slate-300",
        "description": "Comparar números e quantidades — maior, menor, igual.",
    },
    "calculo-mental": {
        "name": "Cálculo Mental e Tabuada",
        "short_name": "Tabuada",
        "icon": "fa-brain",
        "color": "purple-400",
        "description": "Multiplicação memorizada e agilidade de cálculo mental.",
    },
    "operacoes-aritmeticas": {
        "name": "Operações Aritméticas Fundamentais",
        "short_name": "Operações",
        "icon": "fa-plus-minus",
        "color": "emerald-400",
        "description": "Adição, subtração, multiplicação e divisão.",
    },
    "potenciacao": {
        "name": "Potenciação",
        "short_name": "Potências",
        "icon": "fa-superscript",
        "color": "orange-400",
        "description": "Potências e suas propriedades.",
    },
    "radiciacao": {
        "name": "Radiciação",
        "short_name": "Raízes",
        "icon": "fa-square-root-variable",
        "color": "cyan-300",
        "description": "Raízes quadradas e cúbicas.",
    },
    "fracoes": {
        "name": "Frações e Números Racionais",
        "short_name": "Frações",
        "icon": "fa-divide",
        "color": "violet-400",
        "description": "Partes de um todo e operações com frações.",
    },
    "numeros-decimais": {
        "name": "Números Decimais",
        "short_name": "Decimais",
        "icon": "fa-ellipsis",
        "color": "blue-400",
        "description": "Leitura e operações com números decimais.",
    },
    "porcentagem": {
        "name": "Porcentagem e Proporcionalidade",
        "short_name": "Porcent.",
        "icon": "fa-percent",
        "color": "yellow-400",
        "description": "Porcentagens e raciocínio proporcional.",
    },
    "pensamento-algebrico": {
        "name": "Pensamento Algébrico",
        "short_name": "Álgebra",
        "icon": "fa-equals",
        "color": "red-400",
        "description": "Equações e resolução de problemas com incógnitas.",
    },
    "geometria-basica": {
        "name": "Geometria: Perímetro e Área",
        "short_name": "Geometria",
        "icon": "fa-draw-polygon",
        "color": "indigo-400",
        "description": "Medir contornos e superfícies de figuras planas.",
    },
}

# Which areas should ideally be solid *before* this one — advisory only,
# same philosophy as progression_service.unmet_prerequisites (nothing is
# ever hard-locked; this only powers a "reforce isto primeiro" hint on the
# Diagnóstico de Domínio page). Roughly follows AREAS' own insertion
# order above, hand-curated rather than derived from it so a reordering
# there never silently changes the dependency graph.
AREA_PREREQUISITES: dict[str, list[str]] = {
    "senso-numerico": [],
    "comparacao": ["senso-numerico"],
    "calculo-mental": ["senso-numerico", "comparacao"],
    "operacoes-aritmeticas": ["calculo-mental"],
    "potenciacao": ["operacoes-aritmeticas"],
    "radiciacao": ["potenciacao"],
    "fracoes": ["operacoes-aritmeticas"],
    "numeros-decimais": ["fracoes"],
    "porcentagem": ["fracoes", "numeros-decimais"],
    "pensamento-algebrico": ["operacoes-aritmeticas", "porcentagem"],
    "geometria-basica": ["operacoes-aritmeticas"],
}

# topic slug -> area slug. Every *active* topic seeded by scripts/seed.py
# must have an entry (see test_math_areas.py) — a topic silently missing
# from this map would just vanish from the diagnostic instead of erroring
# loudly, which is worse than a hard test failure.
TOPIC_AREAS: dict[str, str] = {
    "numeros-e-contagem": "senso-numerico",
    "comparacao-de-quantidades": "comparacao",
    "tabuada-do-1": "calculo-mental",
    "tabuada-do-2": "calculo-mental",
    "tabuada-do-3": "calculo-mental",
    "tabuada-do-4": "calculo-mental",
    "tabuada-do-5": "calculo-mental",
    "tabuada-do-6": "calculo-mental",
    "tabuada-do-7": "calculo-mental",
    "tabuada-do-8": "calculo-mental",
    "tabuada-do-9": "calculo-mental",
    "tabuada-do-10": "calculo-mental",
    "tabuada-mista": "calculo-mental",
    "adicao": "operacoes-aritmeticas",
    "subtracao": "operacoes-aritmeticas",
    "multiplicacao": "operacoes-aritmeticas",
    "divisao": "operacoes-aritmeticas",
    "potencias-basicas": "potenciacao",
    "propriedades-da-potenciacao": "potenciacao",
    "raiz-quadrada": "radiciacao",
    "raiz-cubica": "radiciacao",
    "fracoes-basicas": "fracoes",
    "operacoes-com-fracoes": "fracoes",
    "leitura-de-decimais": "numeros-decimais",
    "operacoes-com-decimais": "numeros-decimais",
    "porcentagem-basica": "porcentagem",
    "calculo-de-porcentagem": "porcentagem",
    "equacoes-1-grau": "pensamento-algebrico",
    "equacoes-1-grau-avancado": "pensamento-algebrico",
    "equacoes-2-grau-incompletas": "pensamento-algebrico",
    "equacoes-2-grau-fatoravel": "pensamento-algebrico",
    "perimetro-de-figuras": "geometria-basica",
    "area-de-figuras": "geometria-basica",
}


def area_slug_for_topic(topic) -> str | None:
    """None for a topic slug not in the map (e.g. curriculum content added
    without updating this file) — callers skip it rather than crash, but
    test_math_areas.py asserts this never happens for real seeded data."""
    return TOPIC_AREAS.get(topic.slug)


def area_for_topic(topic) -> MathArea | None:
    slug = area_slug_for_topic(topic)
    return AREAS.get(slug) if slug else None
