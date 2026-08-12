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
