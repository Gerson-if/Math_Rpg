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
import random
import re
from typing import TypedDict

TABUADA_RE = re.compile(r"^tabuada-do-(\d{1,2})$")


class Question(TypedDict):
    prompt: str
    answer: str
    meta: dict


# number ranges per difficulty (1..5) for the four basic operations
_ADD_SUB_RANGES = {1: (1, 10), 2: (1, 50), 3: (1, 200), 4: (1, 1000), 5: (1, 10000)}
_MUL_DIV_RANGES = {1: (1, 10), 2: (1, 20), 3: (1, 50), 4: (1, 100), 5: (1, 500)}


def generate_question(topic_slug: str, difficulty: int) -> Question:
    difficulty = max(1, min(5, difficulty))

    tabuada_match = TABUADA_RE.match(topic_slug)
    if tabuada_match:
        return _gen_tabuada(int(tabuada_match.group(1)), difficulty)

    generators = {
        "adicao": _gen_addition,
        "subtracao": _gen_subtraction,
        "multiplicacao": _gen_multiplication,
        "divisao": _gen_division,
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
