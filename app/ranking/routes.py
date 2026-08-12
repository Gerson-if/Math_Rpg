from flask import Blueprint, render_template
from flask_login import login_required

from app.extensions import db
from app.models import PlayerStats, User

ranking_bp = Blueprint("ranking", __name__, url_prefix="/ranking")


@ranking_bp.route("/")
@login_required
def index():
    # Live query rather than the LeaderboardEntry snapshot table — cheap
    # enough for a global "top players by XP" board. Weekly/monthly boards
    # would read from LeaderboardEntry once a scheduled recompute exists
    # (see app/services/ranking_service.py).
    top_players = (
        db.session.query(PlayerStats, User)
        .join(User, User.id == PlayerStats.user_id)
        .order_by(PlayerStats.xp.desc())
        .limit(20)
        .all()
    )
    return render_template("ranking/index.html", top_players=top_players)
