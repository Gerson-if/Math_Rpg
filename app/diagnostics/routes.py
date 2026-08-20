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
    weakest = report[0] if report else None
    radar_svg = diagnostics_service.radar_chart_svg({row["slug"]: row for row in report})
    return render_template(
        "diagnostics/index.html",
        report=report,
        weakest=weakest,
        radar_svg=radar_svg,
    )
