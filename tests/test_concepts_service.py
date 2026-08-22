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


def test_pool_for_areas_unions_multiple_areas_without_duplicates():
    pool = concepts_service.pool_for_areas(["senso-numerico", "comparacao"])
    expected_prompts = {q["prompt"] for q in concepts_service.CONCEPT_QUESTIONS["senso-numerico"]}
    expected_prompts |= {q["prompt"] for q in concepts_service.CONCEPT_QUESTIONS["comparacao"]}
    assert {q["prompt"] for q in pool} == expected_prompts
    assert len(pool) == len(expected_prompts)


def test_pool_for_areas_ignores_unknown_area_slugs():
    pool = concepts_service.pool_for_areas(["nao-existe"])
    assert pool == []


def test_random_concept_question_for_areas_returns_none_for_an_empty_list():
    assert concepts_service.random_concept_question_for_areas([]) is None


def test_random_concept_question_for_areas_draws_from_the_combined_pool():
    for _ in range(30):
        q = concepts_service.random_concept_question_for_areas(["fracoes"])
        assert q in concepts_service.CONCEPT_QUESTIONS["fracoes"]


# --- multiple-choice options -----------------------------------------------

def test_every_concept_question_has_exactly_three_distractors():
    for area_slug, questions in concepts_service.CONCEPT_QUESTIONS.items():
        for q in questions:
            assert len(q["distractors"]) == 3, f"{area_slug}: {q['prompt']!r} doesn't have 3 distractors"


def test_no_concept_question_has_a_distractor_matching_its_own_answer():
    for area_slug, questions in concepts_service.CONCEPT_QUESTIONS.items():
        for q in questions:
            assert q["answer"] not in q["distractors"], f"{area_slug}: {q['prompt']!r} has the answer as a distractor"


def test_build_options_returns_four_unique_options_including_the_answer():
    question = concepts_service.CONCEPT_QUESTIONS["fracoes"][0]
    for _ in range(20):
        options = concepts_service.build_options(question)
        assert len(options) == 4
        assert len(set(options)) == 4
        assert question["answer"] in options
        assert set(options) == {question["answer"], *question["distractors"]}


def test_build_options_shuffles_the_correct_answers_position():
    question = concepts_service.CONCEPT_QUESTIONS["fracoes"][0]
    positions = {concepts_service.build_options(question).index(question["answer"]) for _ in range(60)}
    # With 60 draws across 4 slots, landing in every slot at least once is
    # a near-certainty if shuffle is actually happening (not just always
    # returning the same fixed order).
    assert len(positions) > 1
