"""
Application factory.

The app is built as a set of feature packages (auth, users, mathematics,
progression, ranking, achievements, chat, api) that each expose a Flask
Blueprint. This keeps the codebase modular from day one and matches the
architecture described in the project spec.
"""
import click
from flask import Flask

from app.extensions import db, migrate, login_manager, csrf


def create_app(config_object: str = "config.config.DevelopmentConfig") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    # --- extensions -------------------------------------------------
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = "auth.login"

    # --- models must be imported before migrations can see them -----
    from app import models  # noqa: F401
    from app.auth import loaders  # noqa: F401  (registers login_manager.user_loader)

    # --- blueprints ---------------------------------------------------
    from app.auth.routes import auth_bp
    from app.users.routes import users_bp
    from app.mathematics.routes import mathematics_bp
    from app.progression.routes import progression_bp
    from app.ranking.routes import ranking_bp
    from app.achievements.routes import achievements_bp
    from app.chat.routes import chat_bp
    from app.api.routes import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(mathematics_bp)
    app.register_blueprint(progression_bp)
    app.register_blueprint(ranking_bp)
    app.register_blueprint(achievements_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    @app.route("/health")
    def health():
        return {"status": "ok"}

    @app.cli.command("recompute-leaderboards")
    @click.option(
        "--scope", default="weekly", type=click.Choice(["weekly", "monthly", "global"]),
        help="Which leaderboard snapshot to (re)compute.",
    )
    @click.option("--limit", default=100, type=int, help="How many top players to keep.")
    def recompute_leaderboards(scope: str, limit: int) -> None:
        """Recompute a LeaderboardEntry snapshot for the current period.

        No in-process scheduler is bundled on purpose — with multiple
        Gunicorn workers an in-process timer would fire once per worker.
        Point an external scheduler (cron, systemd timer, Windows Task
        Scheduler, ...) at this command instead. See README for examples.
        """
        from app.services import ranking_service

        count = ranking_service.recompute_leaderboard(scope=scope, limit=limit)
        click.echo(f"Leaderboard '{scope}' recomputado: {count} jogadores.")

    return app
