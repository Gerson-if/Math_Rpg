import math
from fractions import Fraction

import pytest

from app.services.mathematics_service import generate_question


@pytest.mark.parametrize("difficulty", [1, 2, 3, 4, 5])
def test_tabuada_question_involves_the_base_number(difficulty):
    q = generate_question("tabuada-do-7", difficulty)
    assert "7" in q["prompt"]
    assert q["answer"].lstrip("-").isdigit()


def test_tabuada_missing_factor_variant_at_high_difficulty():
    q = generate_question("tabuada-do-9", 5)
    assert "?" in q["prompt"]


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
