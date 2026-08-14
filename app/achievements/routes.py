from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from app.extensions import db
from app.models import Achievement, UserAchievement

achievements_bp = Blueprint("achievements", __name__, url_prefix="/achievements")

MAX_FEATURED = 3


@achievements_bp.route("/")
@login_required
def index():
    unlocked = UserAchievement.query.filter_by(user_id=current_user.id).all()
    unlocked_ids = {ua.achievement_id for ua in unlocked}
    featured_ids = {ua.achievement_id for ua in unlocked if ua.is_featured}
    all_achievements = Achievement.query.all()
    return render_template(
        "achievements/index.html",
        achievements=all_achievements,
        unlocked_ids=unlocked_ids,
        featured_ids=featured_ids,
        featured_count=len(featured_ids),
        max_featured=MAX_FEATURED,
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
