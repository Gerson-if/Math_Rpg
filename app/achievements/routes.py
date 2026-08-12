from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.models import Achievement, UserAchievement

achievements_bp = Blueprint("achievements", __name__, url_prefix="/achievements")


@achievements_bp.route("/")
@login_required
def index():
    unlocked = UserAchievement.query.filter_by(user_id=current_user.id).all()
    unlocked_ids = {ua.achievement_id for ua in unlocked}
    all_achievements = Achievement.query.all()
    return render_template(
        "achievements/index.html",
        achievements=all_achievements,
        unlocked_ids=unlocked_ids,
    )
