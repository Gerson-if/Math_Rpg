"""Turns raw per-topic Mastery rows into a per-*skill* report — "onde
exatamente o jogador deve treinar mais" — using the math sub-area taxonomy
in app.services.math_areas instead of the app's own Subject/Topic
grouping. A player can be strong at Frações as a Subject overall while
still being weak specifically at Comparação (a Fundamentos topic covering
a completely different skill), and this is what surfaces that.
"""
import math as _math

from app.models import Mastery, Topic
from app.services import math_areas
from app.services.progression_service import PREREQUISITE_MASTERY_THRESHOLD

# A prerequisite area counts as a real gap worth flagging only below this
# — same threshold next_topic_for already uses to decide "mastered enough
# to move on", so "reforce isto primeiro" means the same thing here as it
# does everywhere else in the app.
_PREREQ_GAP_THRESHOLD_PCT = round(PREREQUISITE_MASTERY_THRESHOLD * 100)


def area_report(user_id: int) -> list[dict]:
    """One row per math sub-area actually covered by the curriculum,
    sorted weakest-first. A topic never attempted counts as 0 mastery in
    its area's average — an untouched skill is exactly the kind of blind
    spot this report exists to surface, not something to hide until the
    player happens to try it. Each row also carries `prereq_gaps`: the
    areas math_areas.AREA_PREREQUISITES says should come first, filtered
    to just the ones still below _PREREQ_GAP_THRESHOLD_PCT — "what you
    need to know before advancing here", not just "what's weak"."""
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
            "short_name": meta["short_name"],
            "icon": meta["icon"],
            "color": meta["color"],
            "description": meta["description"],
            "mastery_pct": round(avg * 100),
            "topics_practiced": bucket["attempted"],
            "topics_total": topic_count,
            "weakest_topic": weakest_topic,
        })

    rows_by_slug = {row["slug"]: row for row in report}
    for row in report:
        gaps = []
        for prereq_slug in math_areas.AREA_PREREQUISITES.get(row["slug"], []):
            prereq_row = rows_by_slug.get(prereq_slug)
            if prereq_row and prereq_row["mastery_pct"] < _PREREQ_GAP_THRESHOLD_PCT:
                gaps.append({
                    "slug": prereq_slug,
                    "name": prereq_row["name"],
                    "mastery_pct": prereq_row["mastery_pct"],
                })
        row["prereq_gaps"] = gaps

    report.sort(key=lambda row: row["mastery_pct"])
    return report


# ---------------------------------------------------------------------------
# Radar/spider chart — a single glance at "is this shape lopsided" says
# more than scanning 11 separate percentages does. Rendered as plain
# inline SVG (server-side trig, no charting library), consistent with the
# rest of the app never pulling in a third-party JS dependency.
# ---------------------------------------------------------------------------

_RADAR_SIZE = 520
_RADAR_CENTER = _RADAR_SIZE / 2
_RADAR_RADIUS = 165.0
_RADAR_RINGS = (0.25, 0.5, 0.75, 1.0)


def _radar_point(index: int, count: int, fraction: float) -> tuple[float, float]:
    angle = -_math.pi / 2 + index * (2 * _math.pi / count)  # start straight up, go clockwise
    r = _RADAR_RADIUS * fraction
    return _RADAR_CENTER + r * _math.cos(angle), _RADAR_CENTER + r * _math.sin(angle)


def radar_chart_svg(rows_by_slug: dict[str, dict]) -> str:
    """rows_by_slug: {area_slug: row} — typically {row["slug"]: row for row
    in area_report(user_id)}, kept as a separate pure function so the
    chart geometry is testable without touching the database. Areas
    always plot in math_areas.AREAS' own (pedagogical) order, not the
    weakest-first order the report list itself uses, so the chart's shape
    stays stable between visits regardless of which areas are weakest
    today."""
    slugs = list(math_areas.AREAS.keys())
    count = len(slugs)
    if count < 3:
        return ""

    rings = []
    for ring in _RADAR_RINGS:
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in (_radar_point(i, count, ring) for i in range(count)))
        rings.append(f'<polygon points="{pts}" fill="none" stroke="rgba(212,175,55,0.18)" stroke-width="1"/>')

    axes = []
    labels = []
    for i, slug in enumerate(slugs):
        x, y = _radar_point(i, count, 1.0)
        axes.append(
            f'<line x1="{_RADAR_CENTER}" y1="{_RADAR_CENTER}" x2="{x:.1f}" y2="{y:.1f}" '
            f'stroke="rgba(212,175,55,0.18)" stroke-width="1"/>'
        )

        label_x, label_y = _radar_point(i, count, 1.16)
        angle_deg = (i * 360 / count) % 360
        if angle_deg < 10 or angle_deg > 350:
            anchor = "middle"
        elif angle_deg < 170:
            anchor = "start"
        elif angle_deg < 190:
            anchor = "middle"
        else:
            anchor = "end"
        labels.append(
            f'<text x="{label_x:.1f}" y="{label_y:.1f}" text-anchor="{anchor}" '
            f'dominant-baseline="middle" font-size="12" fill="#d6c9a3" font-family="sans-serif">'
            f'{math_areas.AREAS[slug]["short_name"]}</text>'
        )

    data_points = []
    for i, slug in enumerate(slugs):
        pct = rows_by_slug.get(slug, {}).get("mastery_pct", 0)
        # 0.02 floor so a genuinely 0% axis still shows a visible vertex
        # at the center instead of collapsing the polygon into a hole.
        fraction = max(0.02, min(1.0, pct / 100))
        data_points.append(_radar_point(i, count, fraction))
    data_pts_str = " ".join(f"{x:.1f},{y:.1f}" for x, y in data_points)
    dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="#d4af37"/>' for x, y in data_points)

    return (
        f'<svg viewBox="0 0 {_RADAR_SIZE} {_RADAR_SIZE}" class="w-full h-auto" role="img" '
        f'style="overflow: visible;" '
        f'aria-label="Gráfico de domínio por área da matemática">'
        + "".join(rings)
        + "".join(axes)
        + f'<polygon points="{data_pts_str}" fill="rgba(212,175,55,0.28)" stroke="#d4af37" stroke-width="2"/>'
        + dots
        + "".join(labels)
        + "</svg>"
    )
