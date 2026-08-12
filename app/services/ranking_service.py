"""
Ranking service.

The global leaderboard is cheap enough to query live (it's just PlayerStats
sorted by xp), so the route below does that directly. `LeaderboardEntry`
exists for scopes that genuinely need a frozen snapshot — weekly/monthly
boards, where "the ranking as of last Sunday" has to stay stable even as
XP keeps changing. `recompute_leaderboard` is what a scheduled job (cron,
Celery beat, etc.) would call periodically once one exists; it's exposed
here so it can be run manually (or from a script) in the meantime.
"""
from datetime import datetime

from app.extensions import db
from app.models import PlayerStats, LeaderboardEntry


def _current_period_key(scope: str) -> str:
    now = datetime.utcnow()
    if scope == "weekly":
        year, week, _ = now.isocalendar()
        return f"{year}-W{week:02d}"
    if scope == "monthly":
        return now.strftime("%Y-%m")
    return "all-time"


def recompute_leaderboard(scope: str = "global", limit: int = 100) -> int:
    period_key = _current_period_key(scope)
    LeaderboardEntry.query.filter_by(scope=scope, period_key=period_key).delete()

    top_stats = (
        PlayerStats.query.order_by(PlayerStats.xp.desc()).limit(limit).all()
    )
    for position, stats in enumerate(top_stats, start=1):
        db.session.add(LeaderboardEntry(
            scope=scope,
            period_key=period_key,
            user_id=stats.user_id,
            score=stats.xp,
            position=position,
        ))
    db.session.commit()
    return len(top_stats)
