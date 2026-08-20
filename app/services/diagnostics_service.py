"""Turns raw per-topic Mastery rows into a per-*skill* report — "onde
exatamente o jogador deve treinar mais" — using the math sub-area taxonomy
in app.services.math_areas instead of the app's own Subject/Topic
grouping. A player can be strong at Frações as a Subject overall while
still being weak specifically at Comparação (a Fundamentos topic covering
a completely different skill), and this is what surfaces that.
"""
from app.models import Mastery, Topic
from app.services import math_areas


def area_report(user_id: int) -> list[dict]:
    """One row per math sub-area actually covered by the curriculum,
    sorted weakest-first. A topic never attempted counts as 0 mastery in
    its area's average — an untouched skill is exactly the kind of blind
    spot this report exists to surface, not something to hide until the
    player happens to try it."""
    topics = Topic.query.filter_by(is_active=True).all()
    masteries = {
        m.topic_id: m
        for m in Mastery.query.filter_by(user_id=user_id).all()
    }

    buckets: dict[str, dict] = {}
    for topic in topics:
        area_slug = math_areas.area_slug_for_topic(topic)
        if area_slug is None:
            continue
        bucket = buckets.setdefault(area_slug, {"topics": [], "mastery_sum": 0.0, "attempted": 0})
        mastery = masteries.get(topic.id)
        score = mastery.mastery_score if mastery else 0.0
        bucket["topics"].append((topic, score))
        bucket["mastery_sum"] += score
        if mastery is not None:
            bucket["attempted"] += 1

    report = []
    for area_slug, bucket in buckets.items():
        meta = math_areas.AREAS[area_slug]
        topic_count = len(bucket["topics"])
        avg = bucket["mastery_sum"] / topic_count if topic_count else 0.0
        weakest_topic, _ = min(bucket["topics"], key=lambda pair: pair[1])
        report.append({
            "slug": area_slug,
            "name": meta["name"],
            "icon": meta["icon"],
            "color": meta["color"],
            "description": meta["description"],
            "mastery_pct": round(avg * 100),
            "topics_practiced": bucket["attempted"],
            "topics_total": topic_count,
            "weakest_topic": weakest_topic,
        })

    report.sort(key=lambda row: row["mastery_pct"])
    return report
