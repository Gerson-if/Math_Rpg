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


def test_area_for_topic_returns_none_for_an_unmapped_slug():
    class _FakeTopic:
        slug = "not-a-real-topic"

    assert math_areas.area_slug_for_topic(_FakeTopic()) is None
    assert math_areas.area_for_topic(_FakeTopic()) is None
