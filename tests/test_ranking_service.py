from app.models import User, PlayerStats, LeaderboardEntry
from app.services import ranking_service


def _make_player(db, email, xp):
    user = User(email=email, username=email.split("@")[0])
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.flush()
    db.session.add(PlayerStats(user_id=user.id, xp=xp))
    db.session.commit()
    return user


def test_recompute_leaderboard_ranks_players_by_xp(app, db):
    with app.app_context():
        _make_player(db, "a@example.com", 100)
        _make_player(db, "b@example.com", 300)
        _make_player(db, "c@example.com", 200)

        count = ranking_service.recompute_leaderboard(scope="weekly")

        assert count == 3
        entries = (
            LeaderboardEntry.query.filter_by(scope="weekly")
            .order_by(LeaderboardEntry.position)
            .all()
        )
        assert [e.score for e in entries] == [300, 200, 100]
        assert [e.position for e in entries] == [1, 2, 3]


def test_recompute_leaderboard_replaces_stale_entries_for_the_same_period(app, db):
    with app.app_context():
        _make_player(db, "a@example.com", 50)
        ranking_service.recompute_leaderboard(scope="weekly")

        _make_player(db, "b@example.com", 999)
        ranking_service.recompute_leaderboard(scope="weekly")

        entries = LeaderboardEntry.query.filter_by(scope="weekly").all()
        assert len(entries) == 2  # not 3 — the first snapshot was replaced, not appended to


def test_recompute_leaderboards_cli_command_runs(app, db):
    with app.app_context():
        _make_player(db, "a@example.com", 10)
        runner = app.test_cli_runner()

        result = runner.invoke(args=["recompute-leaderboards", "--scope", "monthly"])

        assert result.exit_code == 0
        assert "recomputado" in result.output
        assert LeaderboardEntry.query.filter_by(scope="monthly").count() == 1
