from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.extensions import db
from app.models import PlayerStats, User, Rank
from app.services import classes as classes_service

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

    # The full ladder, low to high, so players can see the ceiling — not
    # just their current badge in isolation. See app/services/loot_service
    # docstring philosophy: progression should always be legible.
    all_ranks = Rank.query.order_by(Rank.order.asc()).all()
    my_stats = PlayerStats.query.filter_by(user_id=current_user.id).first()

    # Evolved display (name/icon), not the bare base class — a Cavaleiro
    # should show as "Cavaleiro" here too, not fall back to "Guerreiro"
    # just because the ranking page has its own lookup.
    class_display_by_user_id = {}
    for stats, user in top_players:
        profile = user.profile
        if profile and profile.character_class:
            class_display_by_user_id[user.id] = classes_service.display_for(
                profile.character_class, profile.class_tier_claimed
            )

    return render_template(
        "ranking/index.html",
        top_players=top_players,
        all_ranks=all_ranks,
        my_stats=my_stats,
        class_display_by_user_id=class_display_by_user_id,
    )
