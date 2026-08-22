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

Presented as multiple choice (A/B/C/D), not free text — a vocabulary
question has exactly one right *word*, and asking a player to type it
correctly (accents, spelling, "Numerador" vs "numerador") tests spelling
as much as it tests the concept, and can't be validated against anything
but that one exact string. Each question's `distractors` are hand-picked
wrong-but-plausible terms from the same neighborhood of vocabulary (e.g.
"Denominador"/"Quociente"/"Divisor" as wrong answers for "Numerador") —
never generated or randomized — so a wrong guess is still informative
instead of obviously silly.

The correct answer is still checked server-side against the signed
question_token (see app/mathematics/routes.py's concepts_answer), exactly
the same way a numeric answer is — a rendered option button just submits
its own label as the "answer" form field, so this reuses that same
comparison path unchanged. The multiple-choice UI doesn't change the
trust model at all; it just makes it impossible for a legitimate player
to submit something that was never actually one of the options (blank,
a typo, stray whitespace) — a client tampering with the raw POST is
caught the exact same way a bogus numeric answer already was, since the
token is what's authoritative, never the submitted text alone.
"""
import random
from typing import TypedDict


class ConceptQuestion(TypedDict):
    prompt: str
    answer: str
    distractors: list[str]


CONCEPT_QUESTIONS: dict[str, list[ConceptQuestion]] = {
    "senso-numerico": [
        {"prompt": "Qual é o menor número natural que existe?", "answer": "0", "distractors": ["1", "-1", "10"]},
        {"prompt": "Quantos algarismos existem no sistema de numeração decimal (de 0 a 9)?", "answer": "10", "distractors": ["9", "12", "100"]},
    ],
    "comparacao": [
        {"prompt": "Qual símbolo matemático significa \"maior que\"?", "answer": ">", "distractors": ["<", "=", "≠"]},
        {"prompt": "Qual símbolo matemático significa \"menor que\"?", "answer": "<", "distractors": [">", "=", "≠"]},
        {"prompt": "Qual símbolo indica que dois valores são iguais?", "answer": "=", "distractors": [">", "<", "≈"]},
    ],
    "calculo-mental": [
        {"prompt": "Como se chama o resultado de uma multiplicação?", "answer": "Produto", "distractors": ["Soma", "Quociente", "Fator"]},
        {"prompt": "Qual número, ao multiplicar qualquer outro, não muda o resultado (elemento neutro da multiplicação)?", "answer": "1", "distractors": ["0", "-1", "10"]},
    ],
    "operacoes-aritmeticas": [
        {"prompt": "Como se chama o resultado de uma adição?", "answer": "Soma", "distractors": ["Produto", "Diferença", "Quociente"]},
        {"prompt": "Como se chama o resultado de uma subtração?", "answer": "Diferença", "distractors": ["Soma", "Produto", "Resto"]},
        {"prompt": "Como se chama o resultado de uma divisão?", "answer": "Quociente", "distractors": ["Produto", "Resto", "Soma"]},
        {"prompt": "Na divisão, como se chama o valor que sobra quando ela não é exata?", "answer": "Resto", "distractors": ["Quociente", "Diferença", "Divisor"]},
        {"prompt": "Na subtração 9 - 4 = 5, como se chama o número 9 (o primeiro)?", "answer": "Minuendo", "distractors": ["Subtraendo", "Diferença", "Resto"]},
    ],
    "potenciacao": [
        {"prompt": "Na potência 2³, como se chama o número 2 (o de baixo)?", "answer": "Base", "distractors": ["Expoente", "Potência", "Radical"]},
        {"prompt": "Na potência 2³, como se chama o número 3 (o de cima)?", "answer": "Expoente", "distractors": ["Base", "Potência", "Coeficiente"]},
        {"prompt": "Qualquer número (diferente de zero) elevado a zero é igual a quê?", "answer": "1", "distractors": ["0", "-1", "10"]},
    ],
    "radiciacao": [
        {"prompt": "Como se chama o símbolo √, usado para indicar uma raiz?", "answer": "Radical", "distractors": ["Radicando", "Índice", "Potência"]},
        {"prompt": "Dentro do símbolo de raiz, como se chama o número do qual se extrai a raiz?", "answer": "Radicando", "distractors": ["Radical", "Índice", "Quociente"]},
    ],
    "fracoes": [
        {"prompt": "Numa fração, como se chama o número de cima?", "answer": "Numerador", "distractors": ["Denominador", "Quociente", "Divisor"]},
        {"prompt": "Numa fração, como se chama o número de baixo?", "answer": "Denominador", "distractors": ["Numerador", "Dividendo", "Resto"]},
        {"prompt": "Uma fração em que o numerador é maior que o denominador é chamada de fração...? (uma palavra)", "answer": "Imprópria", "distractors": ["Própria", "Mista", "Equivalente"]},
    ],
    "numeros-decimais": [
        {"prompt": "No Brasil, qual sinal separa a parte inteira da parte decimal de um número?", "answer": "Vírgula", "distractors": ["Ponto", "Barra", "Dois-pontos"]},
        {"prompt": "No número 3,25, quantas casas decimais existem depois da vírgula?", "answer": "2", "distractors": ["1", "3", "4"]},
    ],
    "porcentagem": [
        {"prompt": "Qual símbolo representa \"por cento\"?", "answer": "%", "distractors": ["‰", "#", "&"]},
        {"prompt": "Quantos por cento representam a metade de um valor?", "answer": "50", "distractors": ["25", "100", "10"]},
    ],
    "pensamento-algebrico": [
        {"prompt": "Em álgebra, como chamamos uma letra que representa um valor desconhecido, como o x?", "answer": "Incógnita", "distractors": ["Coeficiente", "Constante", "Termo"]},
        {"prompt": "Como se chama uma igualdade matemática com uma incógnita, como 2x + 3 = 7?", "answer": "Equação", "distractors": ["Expressão", "Inequação", "Função"]},
    ],
    "geometria-basica": [
        {"prompt": "Como se chama a soma de todos os lados de uma figura plana?", "answer": "Perímetro", "distractors": ["Área", "Volume", "Diâmetro"]},
        {"prompt": "Como se chama a medida da superfície interna de uma figura plana?", "answer": "Área", "distractors": ["Perímetro", "Volume", "Circunferência"]},
        {"prompt": "Quantos lados tem um triângulo?", "answer": "3", "distractors": ["4", "5", "6"]},
        {"prompt": "Quantos lados tem um quadrado?", "answer": "4", "distractors": ["3", "5", "6"]},
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


def build_options(question: ConceptQuestion) -> list[str]:
    """The answer + its hand-picked distractors, shuffled — a fresh
    shuffle every call, so the correct option isn't always in the same
    visual slot (that alone would let a player pattern-match the UI
    instead of actually recalling the term). Nothing about the shuffle
    needs to be remembered server-side: each rendered option button
    submits its own label directly as the answer, checked against the
    signed token exactly like a typed answer always was (see this
    module's own docstring)."""
    options = [question["answer"], *question["distractors"]]
    random.shuffle(options)
    return options
