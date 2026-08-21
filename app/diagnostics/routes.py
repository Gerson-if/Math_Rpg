"""Diagnóstico de Domínio — a per-skill report (see
app.services.diagnostics_service/math_areas) telling the player which
math sub-area to actually train next, instead of only ever surfacing
"which topic" via the adventure map's own per-topic mastery numbers."""
from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.services import diagnostics_service

diagnostics_bp = Blueprint("diagnostics", __name__, url_prefix="/diagnostico")


@diagnostics_bp.route("/")
@login_required
def index():
    report = diagnostics_service.area_report(current_user.id)
    weakest = diagnostics_service.weakest_with_data(report)
    # A weakest pick with zero real attempts only ever happens when
    # NOTHING in the whole report has been practiced yet (see
    # weakest_with_data's fallback) — at that point it's not a diagnosed
    # gap, it's just "you haven't started". The template shows a
    # different, encouraging callout for that case instead of an alarming
    # "sua maior lacuna" pointed at an area picked essentially at random.
    has_any_data = any(row["attempts_total"] > 0 for row in report)
    radar_svg = diagnostics_service.radar_chart_svg({row["slug"]: row for row in report})
    return render_template(
        "diagnostics/index.html",
        report=report,
        weakest=weakest if has_any_data else None,
        has_any_data=has_any_data,
        radar_svg=radar_svg,
    )
