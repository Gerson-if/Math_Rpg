from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Achievement, UserAchievement, PlayerStats
from app.services import progression_service

achievements_bp = Blueprint("achievements", __name__, url_prefix="/achievements")

MAX_FEATURED = 3

# Achievements aren't tagged with a category column — grouping instead
# reads their criteria.type, the same field that already decides how
# progress is measured (see progression_service.progress_for_achievement).
# One label/icon per criteria type keeps the achievements page organized
# without a schema change; a new criteria type not listed here still shows
# up, just under a generic "Outras" group at the end.
CATEGORY_META = {
    "attempts_correct_total": ("Marcos de Acertos", "fa-bullseye"),
    "attempts_total": ("Volume de Prática", "fa-layer-group"),
    "distinct_practice_days": ("Constância", "fa-calendar-check"),
    "best_streak": ("Sequências", "fa-fire"),
    "level_reached": ("Níveis", "fa-arrow-up-right-dots"),
    "rank_reached": ("Ligas", "fa-ranking-star"),
    "attempts_correct_in_subject": ("Domínio por Matéria", "fa-book-open"),
}
CATEGORY_ORDER = list(CATEGORY_META.keys())


@achievements_bp.route("/")
@login_required
def index():
    unlocked = UserAchievement.query.filter_by(user_id=current_user.id).all()
    unlocked_ids = {ua.achievement_id for ua in unlocked}
    featured_ids = {ua.achievement_id for ua in unlocked if ua.is_featured}
    all_achievements = Achievement.query.all()
    stats = PlayerStats.query.filter_by(user_id=current_user.id).first()

    groups_by_type = {}
    for achievement in all_achievements:
        criteria = achievement.criteria or {}
        ctype = criteria.get("type")
        label, icon = CATEGORY_META.get(ctype, ("Outras", "fa-star"))

        progress = None
        if achievement.id not in unlocked_ids and stats is not None:
            raw = progression_service.progress_for_achievement(current_user.id, stats, criteria)
            if raw and raw[1]:
                current, target = raw
                progress = {
                    "current": min(current, target),
                    "target": target,
                    "pct": min(100, round(current / target * 100)),
                }

        # Note: key is "entries", not "items" — a dict literally named
        # "items" collides with dict.items() when accessed as group.items
        # from Jinja (attribute lookup finds the bound method before ever
        # trying __getitem__), silently handing the template a method
        # object instead of the list.
        group = groups_by_type.setdefault(ctype, {"label": label, "icon": icon, "entries": []})
        group["entries"].append((achievement, progress))

    for group in groups_by_type.values():
        group["unlocked_count"] = sum(1 for a, _ in group["entries"] if a.id in unlocked_ids)

    groups = [groups_by_type[t] for t in CATEGORY_ORDER if t in groups_by_type]
    groups += [g for t, g in groups_by_type.items() if t not in CATEGORY_ORDER]

    return render_template(
        "achievements/index.html",
        groups=groups,
        unlocked_ids=unlocked_ids,
        featured_ids=featured_ids,
        featured_count=len(featured_ids),
        max_featured=MAX_FEATURED,
        total_count=len(all_achievements),
        unlocked_count=len(unlocked_ids),
    )


@achievements_bp.route("/destacar/<int:achievement_id>", methods=["POST"])
@login_required
def toggle_featured(achievement_id):
    ua = UserAchievement.query.filter_by(user_id=current_user.id, achievement_id=achievement_id).first()
    if ua is None:
        flash("Você ainda não desbloqueou essa conquista.", "error")
        return redirect(url_for("achievements.index"))

    if ua.is_featured:
        ua.is_featured = False
    else:
        featured_count = UserAchievement.query.filter_by(user_id=current_user.id, is_featured=True).count()
        if featured_count >= MAX_FEATURED:
            flash(f"Você já tem {MAX_FEATURED} conquistas em destaque — remova uma primeiro.", "error")
            return redirect(url_for("achievements.index"))
        ua.is_featured = True
    db.session.commit()
    return redirect(url_for("achievements.index"))
