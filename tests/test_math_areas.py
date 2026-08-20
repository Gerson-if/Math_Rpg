"""math_areas.TOPIC_AREAS is a hand-maintained map — these tests guard
against it silently drifting out of sync with the real curriculum (a
topic added to scripts/seed.py without a matching area entry would
otherwise just vanish from the diagnostic report instead of erroring)."""
from scripts.seed import CURRICULUM
from app.services import math_areas


def _all_curriculum_topic_slugs():
    slugs = []
    for entry in CURRICULUM:
        slugs.extend(entry[2])
    return slugs


def test_every_curriculum_topic_has_a_math_area():
    missing = [slug for slug in _all_curriculum_topic_slugs() if slug not in math_areas.TOPIC_AREAS]
    assert missing == [], f"topics missing from math_areas.TOPIC_AREAS: {missing}"


def test_every_mapped_area_slug_exists_in_areas_catalog():
    unknown = [area for area in math_areas.TOPIC_AREAS.values() if area not in math_areas.AREAS]
    assert unknown == [], f"TOPIC_AREAS references undefined area slugs: {unknown}"


def test_topic_areas_has_no_stale_entries_for_topics_no_longer_in_the_curriculum():
    curriculum_slugs = set(_all_curriculum_topic_slugs())
    stale = [slug for slug in math_areas.TOPIC_AREAS if slug not in curriculum_slugs]
    assert stale == [], f"math_areas.TOPIC_AREAS has entries for topics not in CURRICULUM: {stale}"


def test_area_prerequisites_only_reference_real_area_slugs():
    for area_slug, prereqs in math_areas.AREA_PREREQUISITES.items():
        assert area_slug in math_areas.AREAS, f"AREA_PREREQUISITES has an unknown area key: {area_slug}"
        for prereq_slug in prereqs:
            assert prereq_slug in math_areas.AREAS, f"{area_slug} lists unknown prerequisite: {prereq_slug}"


def test_area_prerequisites_has_no_self_reference():
    for area_slug, prereqs in math_areas.AREA_PREREQUISITES.items():
        assert area_slug not in prereqs


def test_area_for_topic_returns_none_for_an_unmapped_slug():
    class _FakeTopic:
        slug = "not-a-real-topic"

    assert math_areas.area_slug_for_topic(_FakeTopic()) is None
    assert math_areas.area_for_topic(_FakeTopic()) is None


class _FakeTopicWithSlug:
    def __init__(self, slug):
        self.slug = slug


class _FakeSubject:
    def __init__(self, topic_slugs):
        self.topics = [_FakeTopicWithSlug(s) for s in topic_slugs]


def test_area_slugs_for_subject_dedupes_and_keeps_canonical_order():
    # Fundamentos-style subject: two topics, two different areas.
    subject = _FakeSubject(["numeros-e-contagem", "comparacao-de-quantidades"])
    assert math_areas.area_slugs_for_subject(subject) == ["senso-numerico", "comparacao"]


def test_area_slugs_for_subject_returns_one_slug_when_all_topics_share_an_area():
    subject = _FakeSubject(["adicao", "subtracao", "multiplicacao", "divisao"])
    assert math_areas.area_slugs_for_subject(subject) == ["operacoes-aritmeticas"]


def test_area_slugs_for_subject_ignores_unmapped_topics_instead_of_crashing():
    subject = _FakeSubject(["nao-existe"])
    assert math_areas.area_slugs_for_subject(subject) == []
