from app.services import concepts_service, math_areas


def test_every_math_area_has_at_least_one_concept_question():
    missing = [slug for slug in math_areas.AREAS if slug not in concepts_service.CONCEPT_QUESTIONS]
    assert missing == [], f"areas with no concept content yet: {missing}"


def test_concept_questions_only_reference_real_area_slugs():
    unknown = [slug for slug in concepts_service.CONCEPT_QUESTIONS if slug not in math_areas.AREAS]
    assert unknown == [], f"CONCEPT_QUESTIONS has entries for unknown area slugs: {unknown}"


def test_every_concept_question_has_a_nonempty_prompt_and_answer():
    for area_slug, questions in concepts_service.CONCEPT_QUESTIONS.items():
        for q in questions:
            assert q["prompt"].strip(), f"{area_slug} has a blank prompt"
            assert q["answer"].strip(), f"{area_slug} has a blank answer"


def test_random_concept_question_returns_one_from_the_right_area():
    for _ in range(30):
        q = concepts_service.random_concept_question("fracoes")
        assert q in concepts_service.CONCEPT_QUESTIONS["fracoes"]


def test_random_concept_question_returns_none_for_an_unknown_or_missing_area():
    assert concepts_service.random_concept_question("nao-existe") is None
    assert concepts_service.random_concept_question(None) is None
