"""
Mathematics engine: turns (topic, difficulty) into a question.

Design notes
------------
- One small generator function per topic family, registered by slug/pattern
  so adding a new topic (frações, potenciação, ...) later means adding one
  function here, not touching routes or models.
- Difficulty is read from `Topic.base_difficulty` for now — it's static.
  Per section 9 of the spec, *adapting* difficulty to performance is an
  explicitly future capability; this module already accepts a difficulty
  argument so that logic can be layered on top later without changing the
  generator signatures.
- Generators never touch the database. Correction happens by comparing the
  submitted answer to the value returned here (see app/services/
  question_token.py for how the answer is kept secret from the client
  without persisting a Question row for every generated exercise).
"""
import math
import random
import re
from fractions import Fraction
from typing import TypedDict

TABUADA_RE = re.compile(r"^tabuada-do-(\d{1,2})$")


class Question(TypedDict):
    prompt: str
    answer: str
    meta: dict


# number ranges per difficulty (1..5) for the four basic operations
_ADD_SUB_RANGES = {1: (1, 10), 2: (1, 50), 3: (1, 200), 4: (1, 1000), 5: (1, 10000)}
_MUL_DIV_RANGES = {1: (1, 10), 2: (1, 20), 3: (1, 50), 4: (1, 100), 5: (1, 500)}

# Fundamentos: counting objects / comparing two quantities. Kept numeric-only
# (no >, <, = symbols to type) so the existing inputmode="numeric" answer
# field works without changes.
_COUNTING_RANGES = {1: (1, 5), 2: (1, 10), 3: (1, 15), 4: (1, 20), 5: (1, 30)}
_COMPARISON_RANGES = {1: (1, 10), 2: (1, 20), 3: (1, 50), 4: (1, 100), 5: (1, 500)}
_COUNTING_SYMBOLS = ["⭐", "🍎", "🐱", "⚽", "🌸", "🚗", "🐟", "🎈"]


def normalize_answer(value: str) -> str:
    """Numeric-aware comparison: '007' == '7', '0,3' == '0.3' (pt-BR decimal
    comma) == '0.30', and whole-valued floats collapse to plain ints ('3.0'
    == '3') so decimal-operation answers that land on a whole number still
    match. Falls back to a trimmed/lowered/space-stripped string compare for
    non-numeric answers (e.g. fractions like '5/6'). Shared by the solo
    practice loop (app/mathematics/routes.py) and real-time duels
    (app/services/duel_service.py) so both grade answers the same way."""
    value = (value or "").strip().replace(",", ".")
    try:
        return str(int(value))
    except (TypeError, ValueError):
        pass
    try:
        as_float = float(value)
        return str(int(as_float)) if as_float.is_integer() else repr(as_float)
    except (TypeError, ValueError):
        return value.lower().replace(" ", "")


def generate_question(topic_slug: str, difficulty: int) -> Question:
    difficulty = max(1, min(5, difficulty))

    tabuada_match = TABUADA_RE.match(topic_slug)
    if tabuada_match:
        return _gen_tabuada(int(tabuada_match.group(1)), difficulty)

    generators = {
        "numeros-e-contagem": _gen_numbers_counting,
        "comparacao-de-quantidades": _gen_quantity_comparison,
        "tabuada-mista": _gen_tabuada_mista,
        "adicao": _gen_addition,
        "subtracao": _gen_subtraction,
        "multiplicacao": _gen_multiplication,
        "divisao": _gen_division,
        "potencias-basicas": _gen_powers_basic,
        "propriedades-da-potenciacao": _gen_powers_properties,
        "raiz-quadrada": _gen_square_root,
        "raiz-cubica": _gen_cube_root,
        "fracoes-basicas": _gen_fractions_basic,
        "operacoes-com-fracoes": _gen_fractions_operations,
        "leitura-de-decimais": _gen_decimals_reading,
        "operacoes-com-decimais": _gen_decimals_operations,
        "porcentagem-basica": _gen_percentage_basic,
        "calculo-de-porcentagem": _gen_percentage_reverse,
        "equacoes-1-grau": _gen_linear_equation_basic,
        "equacoes-1-grau-avancado": _gen_linear_equation_both_sides,
    }
    generator = generators.get(topic_slug)
    if generator is None:
        raise ValueError(f"Sem gerador de questões para o tópico '{topic_slug}'")
    return generator(difficulty)


def _gen_tabuada(base: int, difficulty: int) -> Question:
    factor = random.randint(0, 10)
    if difficulty <= 3:
        # Straightforward: base × factor = ?
        prompt = f"{base} × {factor} = ?"
        answer = base * factor
    else:
        # Higher difficulty: the missing-factor variant forces recall
        # instead of left-to-right computation.
        result = base * factor
        prompt = f"{base} × ? = {result}"
        answer = factor
    return {"prompt": prompt, "answer": str(answer), "meta": {"family": "tabuada", "base": base}}


def _gen_tabuada_mista(difficulty: int) -> Question:
    """"Domínio completo": draws the base from the whole 1..10 range instead
    of a single fixed table, for the mixed-review topic that sits after all
    ten individual tabuada-do-N topics. Reuses _gen_tabuada so both the
    straightforward and missing-factor variants (and their difficulty
    scaling) stay in one place."""
    base = random.randint(1, 10)
    return _gen_tabuada(base, difficulty)


# ---------------------------------------------------------------------------
# Fundamentos
# ---------------------------------------------------------------------------


def _gen_numbers_counting(difficulty: int) -> Question:
    lo, hi = _COUNTING_RANGES[difficulty]
    count = random.randint(lo, hi)
    symbol = random.choice(_COUNTING_SYMBOLS)
    return {
        "prompt": f"Quantos {symbol} há aqui: {symbol * count}",
        "answer": str(count),
        "meta": {"family": "fundamentos", "kind": "contagem"},
    }


def _gen_quantity_comparison(difficulty: int) -> Question:
    lo, hi = _COMPARISON_RANGES[difficulty]
    a = random.randint(lo, hi)
    b = random.randint(lo, hi)
    while b == a:
        b = random.randint(lo, hi)
    return {
        "prompt": f"Qual é o maior número: {a} ou {b}?",
        "answer": str(max(a, b)),
        "meta": {"family": "fundamentos", "kind": "comparacao"},
    }


def _gen_addition(difficulty: int) -> Question:
    lo, hi = _ADD_SUB_RANGES[difficulty]
    a, b = random.randint(lo, hi), random.randint(lo, hi)
    return {"prompt": f"{a} + {b} = ?", "answer": str(a + b), "meta": {"family": "adicao"}}


def _gen_subtraction(difficulty: int) -> Question:
    lo, hi = _ADD_SUB_RANGES[difficulty]
    a = random.randint(lo, hi)
    b = random.randint(lo, a)  # keep results non-negative for the base topic
    return {"prompt": f"{a} - {b} = ?", "answer": str(a - b), "meta": {"family": "subtracao"}}


def _gen_multiplication(difficulty: int) -> Question:
    lo, hi = _MUL_DIV_RANGES[difficulty]
    a, b = random.randint(lo, hi), random.randint(lo, hi)
    return {"prompt": f"{a} × {b} = ?", "answer": str(a * b), "meta": {"family": "multiplicacao"}}


def _gen_division(difficulty: int) -> Question:
    lo, hi = _MUL_DIV_RANGES[difficulty]
    divisor = random.randint(max(1, lo), hi)
    quotient = random.randint(max(1, lo), hi)
    dividend = divisor * quotient  # guarantees an exact, integer result
    return {
        "prompt": f"{dividend} ÷ {divisor} = ?",
        "answer": str(quotient),
        "meta": {"family": "divisao"},
    }


_SUPERSCRIPT = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def _superscript(n: int) -> str:
    return str(n).translate(_SUPERSCRIPT)


# ---------------------------------------------------------------------------
# Potenciação
# ---------------------------------------------------------------------------

# (base_lo, base_hi, exp_lo, exp_hi) per difficulty
_POWER_RANGES = {
    1: (2, 5, 2, 2),
    2: (2, 6, 2, 3),
    3: (2, 8, 2, 3),
    4: (2, 10, 2, 4),
    5: (2, 12, 2, 4),
}


def _gen_powers_basic(difficulty: int) -> Question:
    base_lo, base_hi, exp_lo, exp_hi = _POWER_RANGES[difficulty]
    base = random.randint(base_lo, base_hi)
    exponent = random.randint(exp_lo, exp_hi)
    result = base ** exponent
    return {
        "prompt": f"{base}{_superscript(exponent)} = ?",
        "answer": str(result),
        "meta": {"family": "potenciacao", "kind": "basicas"},
    }


def _gen_powers_properties(difficulty: int) -> Question:
    base = random.randint(2, 5 + difficulty)
    max_exp = 2 + difficulty
    kind = random.choice(["product", "quotient", "power"])

    if kind == "product":
        m, n = random.randint(1, max_exp), random.randint(1, max_exp)
        prompt = f"{base}{_superscript(m)} × {base}{_superscript(n)} = {base}^?"
        answer = m + n
    elif kind == "quotient":
        m = random.randint(1, max_exp)
        n = random.randint(1, m)  # keep the resulting exponent non-negative
        prompt = f"{base}{_superscript(m)} ÷ {base}{_superscript(n)} = {base}^?"
        answer = m - n
    else:
        m, n = random.randint(1, max_exp), random.randint(1, max_exp)
        prompt = f"({base}{_superscript(m)}){_superscript(n)} = {base}^?"
        answer = m * n

    return {
        "prompt": prompt,
        "answer": str(answer),
        "meta": {"family": "potenciacao", "kind": "propriedades", "property": kind},
    }


# ---------------------------------------------------------------------------
# Radiciação
# ---------------------------------------------------------------------------

_SQUARE_ROOT_RANGES = {1: (1, 5), 2: (2, 8), 3: (2, 12), 4: (2, 15), 5: (2, 20)}
_CUBE_ROOT_RANGES = {1: (1, 3), 2: (1, 4), 3: (2, 5), 4: (2, 6), 5: (2, 8)}


def _gen_square_root(difficulty: int) -> Question:
    lo, hi = _SQUARE_ROOT_RANGES[difficulty]
    root = random.randint(lo, hi)
    return {
        "prompt": f"√{root * root} = ?",
        "answer": str(root),
        "meta": {"family": "radiciacao", "kind": "quadrada"},
    }


def _gen_cube_root(difficulty: int) -> Question:
    lo, hi = _CUBE_ROOT_RANGES[difficulty]
    root = random.randint(lo, hi)
    return {
        "prompt": f"∛{root ** 3} = ?",
        "answer": str(root),
        "meta": {"family": "radiciacao", "kind": "cubica"},
    }


# ---------------------------------------------------------------------------
# Frações
# ---------------------------------------------------------------------------

_FRACTION_DEN_RANGES = {1: (2, 6), 2: (2, 8), 3: (2, 10), 4: (2, 12), 5: (2, 15)}


def _format_fraction(frac: Fraction) -> str:
    if frac.denominator == 1:
        return str(frac.numerator)
    return f"{frac.numerator}/{frac.denominator}"


def _gen_fractions_basic(difficulty: int) -> Question:
    lo, hi = _FRACTION_DEN_RANGES[difficulty]
    den = random.randint(lo, hi)
    num = random.randint(1, den - 1)
    reduced = Fraction(num, den)  # Fraction always stores in lowest terms

    # Scale both parts up so there's always real simplification work to do.
    scale = random.randint(2, 5)
    shown_num, shown_den = reduced.numerator * scale, reduced.denominator * scale

    return {
        "prompt": f"Simplifique a fração {shown_num}/{shown_den} (forma irredutível):",
        "answer": _format_fraction(reduced),
        "meta": {"family": "fracoes", "kind": "basicas"},
    }


def _gen_fractions_operations(difficulty: int) -> Question:
    lo, hi = _FRACTION_DEN_RANGES[difficulty]
    d1, d2 = random.randint(lo, hi), random.randint(lo, hi)
    f1 = Fraction(random.randint(1, d1), d1)
    f2 = Fraction(random.randint(1, d2), d2)
    op = random.choice(["+", "-", "×"])

    if op == "+":
        result = f1 + f2
    elif op == "-":
        if f1 < f2:
            f1, f2 = f2, f1  # keep the result non-negative for this topic
        result = f1 - f2
    else:
        result = f1 * f2

    return {
        "prompt": f"{_format_fraction(f1)} {op} {_format_fraction(f2)} = ?",
        "answer": _format_fraction(result),
        "meta": {"family": "fracoes", "kind": "operacoes", "op": op},
    }


# ---------------------------------------------------------------------------
# Números decimais
# ---------------------------------------------------------------------------

_DECIMAL_PLACES_BY_DIFFICULTY = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3}
_DECIMAL_READING_DEN_BY_DIFFICULTY = {1: 10, 2: 10, 3: 100, 4: 100, 5: 1000}
_DECIMAL_OPERATION_HI_BY_DIFFICULTY = {1: 100, 2: 300, 3: 500, 4: 2000, 5: 5000}


def _gen_decimals_reading(difficulty: int) -> Question:
    den = _DECIMAL_READING_DEN_BY_DIFFICULTY[difficulty]
    places = _DECIMAL_PLACES_BY_DIFFICULTY[difficulty]
    num = random.randint(1, den - 1)
    return {
        "prompt": f"Escreva {num}/{den} na forma decimal:",
        "answer": f"{num / den:.{places}f}",
        "meta": {"family": "numeros-decimais", "kind": "leitura"},
    }


def _gen_decimals_operations(difficulty: int) -> Question:
    places = _DECIMAL_PLACES_BY_DIFFICULTY[difficulty]
    scale = 10 ** places
    hi = _DECIMAL_OPERATION_HI_BY_DIFFICULTY[difficulty]

    # Work in integer "scaled" units (e.g. cents) so addition/subtraction
    # stays exact, then format to decimal a single time at the end.
    a_units = random.randint(1, hi)
    b_units = random.randint(1, hi)
    op = random.choice(["+", "-"])
    if op == "-" and a_units < b_units:
        a_units, b_units = b_units, a_units
    result_units = a_units + b_units if op == "+" else a_units - b_units

    return {
        "prompt": f"{a_units / scale:.{places}f} {op} {b_units / scale:.{places}f} = ?",
        "answer": f"{result_units / scale:.{places}f}",
        "meta": {"family": "numeros-decimais", "kind": "operacoes"},
    }


# ---------------------------------------------------------------------------
# Porcentagem
# ---------------------------------------------------------------------------

_NICE_PERCENTAGES_BY_DIFFICULTY = {
    1: [10, 20, 25, 50],
    2: [10, 20, 25, 50, 75],
    3: [5, 10, 15, 20, 25, 50, 75],
    4: [5, 10, 12, 15, 20, 25, 40, 60, 75],
    5: [5, 8, 12, 15, 18, 24, 35, 45, 65, 85],
}


def _gen_percentage_basic(difficulty: int) -> Question:
    pct = random.choice(_NICE_PERCENTAGES_BY_DIFFICULTY[difficulty])
    step = 100 // math.gcd(pct, 100)  # smallest value for which pct% is a whole number
    value = step * random.randint(1, 6 + difficulty * 3)
    result = pct * value // 100
    return {
        "prompt": f"Quanto é {pct}% de {value}?",
        "answer": str(result),
        "meta": {"family": "porcentagem", "kind": "basica"},
    }


def _gen_percentage_reverse(difficulty: int) -> Question:
    pct = random.choice(_NICE_PERCENTAGES_BY_DIFFICULTY[difficulty])
    step = 100 // math.gcd(pct, 100)
    whole = step * random.randint(1, 6 + difficulty * 3)
    part = pct * whole // 100
    return {
        "prompt": f"{part} é quantos por cento de {whole}?",
        "answer": str(pct),
        "meta": {"family": "porcentagem", "kind": "calculo"},
    }


# ---------------------------------------------------------------------------
# Álgebra — the newest, most advanced subject (see app/services/lore.py's
# "O Grande Castelo das Incógnitas"). Recommended, never required, only
# once a player is comfortable with the earlier curriculum — see
# scripts/seed.py's entry_prereqs for how that recommendation is wired up.
# ---------------------------------------------------------------------------

# (coefficient range, solution range) per difficulty
_LINEAR_EQ_RANGES = {
    1: (2, 5, 1, 10),
    2: (2, 6, 1, 15),
    3: (2, 8, 1, 20),
    4: (2, 10, 1, 30),
    5: (2, 12, 1, 40),
}


def _gen_linear_equation_basic(difficulty: int) -> Question:
    """ax + b = c → x = ?, always a positive integer solution."""
    a_lo, a_hi, x_lo, x_hi = _LINEAR_EQ_RANGES[difficulty]
    a = random.randint(a_lo, a_hi)
    x = random.randint(x_lo, x_hi)
    b = random.randint(0, x_hi)
    c = a * x + b
    prompt = f"{a}x + {b} = {c} → x = ?" if b else f"{a}x = {c} → x = ?"
    return {"prompt": prompt, "answer": str(x), "meta": {"family": "algebra", "kind": "linear-basica"}}


def _gen_linear_equation_both_sides(difficulty: int) -> Question:
    """ax + b = cx + d → x = ?, with the unknown on both sides — a step up
    from the basic form since it takes an extra rearranging move first."""
    a_lo, a_hi, x_lo, x_hi = _LINEAR_EQ_RANGES[difficulty]
    x = random.randint(x_lo, min(x_hi, 20))
    a = random.randint(3, a_hi)
    c = random.randint(1, a - 1)  # keep a > c so (a - c) stays positive
    b = random.randint(0, 20)
    d = (a - c) * x + b
    return {
        "prompt": f"{a}x + {b} = {c}x + {d} → x = ?",
        "answer": str(x),
        "meta": {"family": "algebra", "kind": "linear-dois-lados"},
    }
