"""Concept-check questions — "o que esse termo significa", not "calcule
isto". The rest of the battle already drills computation; these exist
because a player can get every numeric question right while still not
knowing what a "denominador" or a "expoente" actually is, and that
vocabulary gap is exactly what real math class calls it out for.

Keyed by math sub-area (see app.services.math_areas), not by topic — the
vocabulary for "o que é numerador" belongs to Frações as a skill, not to
one specific topic inside it. Kept as a plain, hand-curated Python module
like guardians.py/lore.py — this is curriculum content, not something a
player or admin edits at runtime.

Each answer is one canonical term (not a list of accepted synonyms) so
these questions can flow through the exact same signed-token
answer-checking path as every numeric question (see
app/services/question_token.py) without touching that comparison logic —
same reason accent-folding was added to mathematics_service.normalize_answer,
so "area" still matches "Área" without the player needing the accent.
"""
import random
from typing import TypedDict


class ConceptQuestion(TypedDict):
    prompt: str
    answer: str


CONCEPT_QUESTIONS: dict[str, list[ConceptQuestion]] = {
    "senso-numerico": [
        {"prompt": "Qual é o menor número natural que existe?", "answer": "0"},
        {"prompt": "Quantos algarismos existem no sistema de numeração decimal (de 0 a 9)?", "answer": "10"},
    ],
    "comparacao": [
        {"prompt": "Qual símbolo matemático significa \"maior que\"?", "answer": ">"},
        {"prompt": "Qual símbolo matemático significa \"menor que\"?", "answer": "<"},
        {"prompt": "Qual símbolo indica que dois valores são iguais?", "answer": "="},
    ],
    "calculo-mental": [
        {"prompt": "Como se chama o resultado de uma multiplicação?", "answer": "Produto"},
        {"prompt": "Qual número, ao multiplicar qualquer outro, não muda o resultado (elemento neutro da multiplicação)?", "answer": "1"},
    ],
    "operacoes-aritmeticas": [
        {"prompt": "Como se chama o resultado de uma adição?", "answer": "Soma"},
        {"prompt": "Como se chama o resultado de uma subtração?", "answer": "Diferença"},
        {"prompt": "Como se chama o resultado de uma divisão?", "answer": "Quociente"},
        {"prompt": "Na divisão, como se chama o valor que sobra quando ela não é exata?", "answer": "Resto"},
        {"prompt": "Na subtração 9 - 4 = 5, como se chama o número 9 (o primeiro)?", "answer": "Minuendo"},
    ],
    "potenciacao": [
        {"prompt": "Na potência 2³, como se chama o número 2 (o de baixo)?", "answer": "Base"},
        {"prompt": "Na potência 2³, como se chama o número 3 (o de cima)?", "answer": "Expoente"},
        {"prompt": "Qualquer número (diferente de zero) elevado a zero é igual a quê?", "answer": "1"},
    ],
    "radiciacao": [
        {"prompt": "Como se chama o símbolo √, usado para indicar uma raiz?", "answer": "Radical"},
        {"prompt": "Dentro do símbolo de raiz, como se chama o número do qual se extrai a raiz?", "answer": "Radicando"},
    ],
    "fracoes": [
        {"prompt": "Numa fração, como se chama o número de cima?", "answer": "Numerador"},
        {"prompt": "Numa fração, como se chama o número de baixo?", "answer": "Denominador"},
        {"prompt": "Uma fração em que o numerador é maior que o denominador é chamada de fração...? (uma palavra)", "answer": "Imprópria"},
    ],
    "numeros-decimais": [
        {"prompt": "No Brasil, qual sinal separa a parte inteira da parte decimal de um número?", "answer": "Vírgula"},
        {"prompt": "No número 3,25, quantas casas decimais existem depois da vírgula?", "answer": "2"},
    ],
    "porcentagem": [
        {"prompt": "Qual símbolo representa \"por cento\"?", "answer": "%"},
        {"prompt": "Quantos por cento representam a metade de um valor?", "answer": "50"},
    ],
    "pensamento-algebrico": [
        {"prompt": "Em álgebra, como chamamos uma letra que representa um valor desconhecido, como o x?", "answer": "Incógnita"},
        {"prompt": "Como se chama uma igualdade matemática com uma incógnita, como 2x + 3 = 7?", "answer": "Equação"},
    ],
    "geometria-basica": [
        {"prompt": "Como se chama a soma de todos os lados de uma figura plana?", "answer": "Perímetro"},
        {"prompt": "Como se chama a medida da superfície interna de uma figura plana?", "answer": "Área"},
        {"prompt": "Quantos lados tem um triângulo?", "answer": "3"},
        {"prompt": "Quantos lados tem um quadrado?", "answer": "4"},
    ],
}


def random_concept_question(area_slug: str | None) -> ConceptQuestion | None:
    """None if area_slug is unrecognized or has no concept content yet —
    callers fall back to a normal numeric question rather than crashing."""
    if not area_slug:
        return None
    pool = CONCEPT_QUESTIONS.get(area_slug)
    return random.choice(pool) if pool else None


def pool_for_areas(area_slugs: list[str]) -> list[ConceptQuestion]:
    """Union of every area's concept pool, in AREAS order and de-duplicated
    by prompt — a Subject on the adventure map can span more than one math
    area (see math_areas' own docstring, e.g. Fundamentos = senso-numerico
    + comparação), so its dedicated concept exercise pulls from all of
    them rather than picking just one arbitrarily."""
    seen_prompts: set[str] = set()
    pool: list[ConceptQuestion] = []
    for area_slug in area_slugs:
        for question in CONCEPT_QUESTIONS.get(area_slug, []):
            if question["prompt"] not in seen_prompts:
                seen_prompts.add(question["prompt"])
                pool.append(question)
    return pool


def random_concept_question_for_areas(
    area_slugs: list[str], avoid_prompts: "set[str] | None" = None
) -> ConceptQuestion | None:
    """avoid_prompts (recently-served prompts — see
    app/mathematics/routes.py's session-backed tracking) is filtered out
    of the pool *before* picking, not retried after — these pools are
    small and fixed (a handful of questions per area), so a filter
    guarantees no repeat until the whole pool has actually been seen,
    instead of a retry loop that could still land on the same one a few
    times before giving up. Falls back to the full pool if filtering
    would leave nothing to ask (small pool, most of it recently shown) —
    a rare repeat beats returning None and ending the exercise early."""
    pool = pool_for_areas(area_slugs)
    if not pool:
        return None
    if avoid_prompts:
        filtered = [q for q in pool if q["prompt"] not in avoid_prompts]
        if filtered:
            pool = filtered
    return random.choice(pool)
