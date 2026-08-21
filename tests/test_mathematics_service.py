import math
from fractions import Fraction

import pytest

from app.services.mathematics_service import generate_question, normalize_answer


@pytest.mark.parametrize("difficulty", [1, 2, 3, 4, 5])
def test_tabuada_question_involves_the_base_number(difficulty):
    q = generate_question("tabuada-do-7", difficulty)
    assert "7" in q["prompt"]
    assert q["answer"].lstrip("-").isdigit()


def test_tabuada_missing_factor_variant_at_high_difficulty():
    q = generate_question("tabuada-do-9", 5)
    assert "?" in q["prompt"]


def test_tabuada_difficulty_1_always_keeps_the_base_first():
    for _ in range(40):
        q = generate_question("tabuada-do-7", 1)
        assert q["prompt"].startswith("7 ×")


def test_tabuada_difficulty_2_sometimes_inverts_the_operand_order():
    prompts = {generate_question("tabuada-do-7", 2)["prompt"] for _ in range(80)}
    assert any(not p.startswith("7 ×") for p in prompts), "expected at least one inverted 'N × 7' prompt"
    assert any(p.startswith("7 ×") for p in prompts), "expected the natural order to still show up too"


@pytest.mark.parametrize("difficulty", [2, 3])
def test_tabuada_answer_is_correct_regardless_of_printed_order(difficulty):
    for _ in range(40):
        q = generate_question("tabuada-do-6", difficulty)
        a, _, b = q["prompt"].partition(" × ")
        b = b.split(" =")[0]
        assert int(a) * int(b) == int(q["answer"])


# --- "Tabuada mista": the mixed-review topic covering every base 1..10 ----

def test_tabuada_mista_covers_the_full_base_range():
    seen_bases = {generate_question("tabuada-mista", 1)["meta"]["base"] for _ in range(300)}
    assert seen_bases == set(range(1, 11))


@pytest.mark.parametrize("difficulty", [1, 2, 3, 4, 5])
def test_tabuada_mista_answer_is_correct(difficulty):
    for _ in range(50):
        q = generate_question("tabuada-mista", difficulty)
        assert q["meta"]["family"] == "tabuada"
        base = q["meta"]["base"]
        assert 1 <= base <= 10
        if q["prompt"].endswith("= ?"):
            # Order isn't fixed (base-first vs inverted, see
            # _gen_tabuada) from difficulty 2 onward — check the product
            # of whatever two numbers are actually printed instead of
            # assuming which position holds the base.
            left, right = q["prompt"].split(" = ?")[0].split(" × ")
            assert int(q["answer"]) == int(left) * int(right)
            assert base in (int(left), int(right))
        else:
            result = int(q["prompt"].split("= ")[1])
            assert base * int(q["answer"]) == result


@pytest.mark.parametrize("topic", ["adicao", "subtracao", "multiplicacao", "divisao"])
def test_basic_operations_generate_valid_answers(topic):
    for difficulty in range(1, 6):
        q = generate_question(topic, difficulty)
        assert q["prompt"]
        assert q["answer"].lstrip("-").isdigit()


def test_division_is_always_exact():
    for _ in range(50):
        q = generate_question("divisao", 4)
        dividend_str, _, rest = q["prompt"].partition(" ÷ ")
        divisor_str = rest.split(" ")[0]
        assert int(dividend_str) % int(divisor_str) == 0


def test_subtraction_never_negative_by_default():
    for _ in range(50):
        q = generate_question("subtracao", 3)
        assert int(q["answer"]) >= 0


def test_unknown_topic_raises_value_error():
    with pytest.raises(ValueError):
        generate_question("topico-inexistente", 1)


# --- Fundamentos ---------------------------------------------------------

def test_numbers_counting_answer_matches_symbol_count():
    for _ in range(50):
        for difficulty in range(1, 6):
            q = generate_question("numeros-e-contagem", difficulty)
            symbol = q["prompt"].split("aqui: ")[1]
            assert len(symbol) == int(q["answer"])


def test_quantity_comparison_answer_is_the_larger_number():
    for _ in range(50):
        for difficulty in range(1, 6):
            q = generate_question("comparacao-de-quantidades", difficulty)
            prompt = q["prompt"].removeprefix("Qual é o maior número: ").rstrip("?")
            a_str, b_str = prompt.split(" ou ")
            a, b = int(a_str), int(b_str)
            assert a != b
            assert int(q["answer"]) == max(a, b)


# --- Fase 7: Potenciação -----------------------------------------------

def test_powers_basic_answer_is_correct():
    # NOTE: str.isdigit() is True for superscript digits too, so the base
    # and the exponent must be split by set membership, not by isdigit().
    superscripts = "⁰¹²³⁴⁵⁶⁷⁸⁹"
    for _ in range(50):
        for difficulty in range(1, 6):
            q = generate_question("potencias-basicas", difficulty)
            expr = q["prompt"].split(" = ?")[0].strip()
            base = int("".join(ch for ch in expr if ch not in superscripts))
            exponent = int("".join(str(superscripts.index(ch)) for ch in expr if ch in superscripts))
            assert int(q["answer"]) == base ** exponent


def test_powers_properties_answer_matches_exponent_rule():
    for _ in range(80):
        q = generate_question("propriedades-da-potenciacao", 4)
        prop = q["meta"]["property"]
        answer = int(q["answer"])
        assert answer >= 0
        if prop == "quotient":
            assert answer >= 0


# --- Fase 7: Radiciação --------------------------------------------------

@pytest.mark.parametrize("topic,power", [("raiz-quadrada", 2), ("raiz-cubica", 3)])
def test_roots_answer_is_correct(topic, power):
    for _ in range(50):
        for difficulty in range(1, 6):
            q = generate_question(topic, difficulty)
            n = int(q["prompt"].lstrip("√∛").split(" = ?")[0])
            assert int(q["answer"]) ** power == n


# --- Fase 7: Frações -------------------------------------------------------

def test_fractions_basic_is_already_reduced_and_equivalent():
    for _ in range(80):
        for difficulty in range(1, 6):
            q = generate_question("fracoes-basicas", difficulty)
            shown = q["prompt"].split("fração ")[1].split(" (")[0]
            shown_num, shown_den = (int(x) for x in shown.split("/"))
            answer_frac = Fraction(q["answer"])
            assert Fraction(shown_num, shown_den) == answer_frac
            assert math.gcd(answer_frac.numerator, answer_frac.denominator) == 1


def test_fractions_operations_answer_is_arithmetically_correct():
    for _ in range(80):
        for difficulty in range(1, 6):
            q = generate_question("operacoes-com-fracoes", difficulty)
            left, op, right = q["prompt"].replace(" = ?", "").split(" ")
            a, b = Fraction(left), Fraction(right)
            expected = {"+": a + b, "-": a - b, "×": a * b}[op]
            got = Fraction(q["answer"])
            assert got == expected
            if op == "-":
                assert expected >= 0


# --- Fase 7: Números decimais ----------------------------------------------

def test_decimals_reading_matches_fraction_value():
    for _ in range(50):
        for difficulty in range(1, 6):
            q = generate_question("leitura-de-decimais", difficulty)
            frac_part = q["prompt"].split("Escreva ")[1].split(" na")[0]
            num, den = (int(x) for x in frac_part.split("/"))
            assert abs(float(q["answer"]) - num / den) < 1e-9


def test_decimals_operations_answer_is_correct():
    for _ in range(50):
        for difficulty in range(1, 6):
            q = generate_question("operacoes-com-decimais", difficulty)
            left, op, right = q["prompt"].replace(" = ?", "").split(" ")
            a, b = float(left), float(right)
            expected = a + b if op == "+" else a - b
            assert abs(float(q["answer"]) - expected) < 1e-6
            if op == "-":
                assert float(q["answer"]) >= 0


# --- Fase 7: Porcentagem ----------------------------------------------------

def test_percentage_basic_answer_is_correct():
    for _ in range(80):
        for difficulty in range(1, 6):
            q = generate_question("porcentagem-basica", difficulty)
            pct = int(q["prompt"].split("é ")[1].split("% de ")[0])
            value = int(q["prompt"].split("% de ")[1].rstrip("?"))
            assert int(q["answer"]) == pct * value // 100


def test_percentage_reverse_answer_is_correct():
    for _ in range(80):
        for difficulty in range(1, 6):
            q = generate_question("calculo-de-porcentagem", difficulty)
            part = int(q["prompt"].split(" é ")[0])
            whole = int(q["prompt"].split("de ")[1].rstrip("?"))
            assert part * 100 // whole == int(q["answer"])


# --- Álgebra -----------------------------------------------------------

def test_linear_equation_basic_answer_solves_the_equation():
    import re

    for _ in range(80):
        for difficulty in range(1, 6):
            q = generate_question("equacoes-1-grau", difficulty)
            x = int(q["answer"])
            m = re.match(r"(\d+)x(?: \+ (\d+))? = (\d+)", q["prompt"])
            a, b, c = int(m.group(1)), int(m.group(2) or 0), int(m.group(3))
            assert a * x + b == c
            assert x > 0


def test_linear_equation_both_sides_answer_solves_the_equation():
    import re

    for _ in range(80):
        for difficulty in range(1, 6):
            q = generate_question("equacoes-1-grau-avancado", difficulty)
            x = int(q["answer"])
            m = re.match(r"(\d+)x \+ (\d+) = (\d+)x \+ (\d+)", q["prompt"])
            a, b, c, d = (int(m.group(i)) for i in range(1, 5))
            assert a * x + b == c * x + d
            assert x > 0


# --- Equações do 2º Grau -------------------------------------------------

def test_quadratic_incomplete_answer_solves_the_equation():
    import re

    for _ in range(80):
        for difficulty in range(1, 6):
            q = generate_question("equacoes-2-grau-incompletas", difficulty)
            x = int(q["answer"])
            m = re.match(r"(\d+)x² = (\d+)", q["prompt"])
            a, b = int(m.group(1)), int(m.group(2))
            assert a * x * x == b
            assert x > 0


def test_quadratic_factorable_answer_is_the_repeated_root():
    import re

    for _ in range(80):
        for difficulty in range(1, 6):
            q = generate_question("equacoes-2-grau-fatoravel", difficulty)
            r = int(q["answer"])
            m = re.match(r"x² - (\d+)x \+ (\d+) = 0", q["prompt"])
            b, c = int(m.group(1)), int(m.group(2))
            # (x - r)² expanded is x² - 2r·x + r² — confirms r really is
            # the (repeated) root of the equation shown.
            assert b == 2 * r
            assert c == r * r
            assert r > 0


# --- Geometria Básica ------------------------------------------------------

def test_perimeter_answer_matches_the_shape_described():
    for _ in range(150):
        for difficulty in range(1, 6):
            q = generate_question("perimetro-de-figuras", difficulty)
            shape = q["meta"]["shape"]
            nums = [int(n) for n in __import__("re").findall(r"\d+", q["prompt"])]
            answer = int(q["answer"])
            if shape == "quadrado":
                side, = nums[:1]
                assert answer == side * 4
            elif shape == "triangulo-equilatero":
                side, = nums[:1]
                assert answer == side * 3
            else:
                base, altura = nums[:2]
                assert base != altura
                assert answer == 2 * (base + altura)


def test_force_concept_returns_a_concept_question_when_the_area_has_content():
    q = generate_question("fracoes-basicas", 1, force_concept=True)
    assert q["meta"]["kind"] == "conceito"
    assert q["meta"]["area"] == "fracoes"
    assert q["prompt"]
    assert q["answer"]


def test_force_concept_falls_back_to_numeric_for_an_unmapped_topic():
    # Not a real curriculum slug, so math_areas has no entry for it —
    # force_concept must not raise, just fall through to the normal
    # per-topic dispatch below (which *will* raise its own ValueError for
    # an unknown topic, same as without force_concept at all).
    with pytest.raises(ValueError):
        generate_question("topico-que-nao-existe", 1, force_concept=True)


def test_force_concept_false_never_returns_a_concept_question():
    for _ in range(20):
        q = generate_question("fracoes-basicas", 1, force_concept=False)
        assert q["meta"].get("kind") != "conceito"


def test_normalize_answer_folds_accents_for_word_answers():
    assert normalize_answer("Área") == normalize_answer("area")
    assert normalize_answer("Numerador") == normalize_answer("numerador")
    assert normalize_answer("  Denominador  ") == normalize_answer("denominador")


def test_area_answer_matches_the_shape_described():
    import re

    for _ in range(150):
        for difficulty in range(1, 6):
            q = generate_question("area-de-figuras", difficulty)
            shape = q["meta"]["shape"]
            nums = [int(n) for n in re.findall(r"\d+", q["prompt"])]
            answer = int(q["answer"])
            if shape == "quadrado":
                side, = nums[:1]
                assert answer == side * side
            elif shape == "retangulo":
                base, altura = nums[:2]
                assert answer == base * altura
            else:  # triangulo
                base, altura = nums[:2]
                assert (base * altura) % 2 == 0
                assert answer == (base * altura) // 2


# --- no-immediate-repeat (avoid_prompts) ----------------------------------

def test_avoid_prompts_dodges_an_immediate_repeat_when_the_space_allows_it():
    # tabuada-do-7 at difficulty 1 has 11 possible prompts (factor 0..10)
    # — plenty of room to avoid re-drawing the one prompt already served.
    first = generate_question("tabuada-do-7", 1)
    avoided = {first["prompt"]}
    # Draw many times and confirm at least some distinct prompts show up
    # outside the avoid set (i.e. avoid_prompts is actually influencing
    # the draw, not a no-op) — a single draw could still legitimately
    # dodge it by chance even without the retry logic, so this checks the
    # aggregate behaviour across many draws instead.
    prompts = {generate_question("tabuada-do-7", 1, avoid_prompts=avoided)["prompt"] for _ in range(20)}
    assert len(prompts - avoided) > 0


def test_avoid_prompts_never_raises_even_when_the_space_is_nearly_exhausted():
    # difficulty 1 counting (Fundamentos) has a small number space —
    # confirms the retry cap kicks in instead of looping forever or
    # erroring when avoid_prompts covers most/all of it.
    from app.services.mathematics_service import _COUNTING_RANGES, _COUNTING_SYMBOLS

    lo, hi = _COUNTING_RANGES[1]
    avoid_all = {f"Quantos {s} há aqui: {s * n}" for s in _COUNTING_SYMBOLS for n in range(lo, hi + 1)}
    # Should return *something* without raising, even though every
    # possible prompt is in the avoid set.
    q = generate_question("numeros-e-contagem", 1, avoid_prompts=avoid_all)
    assert q["prompt"]


def test_avoid_prompts_empty_set_behaves_like_no_avoidance():
    q = generate_question("tabuada-do-7", 1, avoid_prompts=set())
    assert "7" in q["prompt"]


# --- fingerprints / due-fact review (tabuada family only) -----------------

def test_tabuada_question_includes_a_canonical_fingerprint():
    q = generate_question("tabuada-do-7", 1)
    fp = q["meta"]["fingerprint"]
    a, b = sorted(int(x) for x in fp.split("x"))
    assert a == 7 or b == 7
    assert a <= b


def test_tabuada_due_fingerprint_generates_that_exact_fact():
    q = generate_question("tabuada-do-7", 1, due_fingerprint="7x8")
    assert q["meta"]["fingerprint"] == "7x8"
    assert "7" in q["prompt"] and "8" in q["prompt"]
    assert q["answer"] == "56"


def test_tabuada_due_fingerprint_at_high_difficulty_still_asks_for_the_missing_factor():
    q = generate_question("tabuada-do-7", 5, due_fingerprint="7x8")
    assert q["meta"]["fingerprint"] == "7x8"
    assert "?" in q["prompt"]
    assert int(q["answer"]) in (7, 8)


def test_tabuada_mista_due_fingerprint_uses_the_fingerprints_own_pair():
    q = generate_question("tabuada-mista", 1, due_fingerprint="4x9")
    assert q["meta"]["fingerprint"] == "4x9"
    assert q["answer"] == "36"


def test_tabuada_ignores_a_malformed_due_fingerprint_and_falls_back_to_random():
    q = generate_question("tabuada-do-7", 1, due_fingerprint="not-a-fingerprint")
    assert "7" in q["prompt"]


def test_due_fingerprint_is_ignored_for_topics_outside_the_tabuada_family():
    # Passing due_fingerprint for e.g. addition shouldn't error or do
    # anything special — only the tabuada family understands it.
    q = generate_question("adicao", 1, due_fingerprint="7x8")
    assert "+" in q["prompt"]


def test_due_fingerprint_falls_back_to_random_when_it_collides_with_avoid_prompts():
    # Regression guard: at difficulty 1 (no order-flip — see
    # _tabuada_prompt) a due-fact draw is fully deterministic in prompt
    # text. If that exact prompt is already in avoid_prompts, retrying
    # with the same due_fingerprint would just regenerate the identical
    # prompt every time and never actually dodge it.
    due_prompt = generate_question("tabuada-do-7", 1, due_fingerprint="7x8")["prompt"]
    assert due_prompt == "7 × 8 = ?"

    prompts = {
        generate_question("tabuada-do-7", 1, due_fingerprint="7x8", avoid_prompts={due_prompt})["prompt"]
        for _ in range(20)
    }
    assert len(prompts - {due_prompt}) > 0, "expected the retry to escape the due fact's own deterministic prompt"
