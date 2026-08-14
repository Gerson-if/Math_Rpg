"""
Application factory.

The app is built as a set of feature packages (auth, users, mathematics,
progression, ranking, achievements, chat, api) that each expose a Flask
Blueprint. This keeps the codebase modular from day one and matches the
architecture described in the project spec.
"""
import click
from flask import Flask, render_template

from app.extensions import db, migrate, login_manager, csrf, limiter
from app.logging_config import configure_logging


def create_app(config_object: str = "config.config.DevelopmentConfig") -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)
    configure_logging(app)

    # --- extensions -------------------------------------------------
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

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
    from app.friends.routes import friends_bp
    from app.character.routes import character_bp
    from app.market.routes import market_bp
    from app.api.routes import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(users_bp)
    app.register_blueprint(mathematics_bp)
    app.register_blueprint(progression_bp)
    app.register_blueprint(ranking_bp)
    app.register_blueprint(achievements_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(friends_bp)
    app.register_blueprint(character_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    @app.context_processor
    def _inject_pending_invites_count():
        """Small badge count for the navbar's "Amigos" link — friend
        requests + dungeon invites waiting on the current user. Cheap (two
        indexed COUNT-shaped queries) and only runs when logged in."""
        from flask_login import current_user

        if not current_user.is_authenticated:
            return {}
        from app.services import friends_service, dungeon_service

        count = (
            len(friends_service.list_incoming_requests(current_user.id))
            + len(dungeon_service.list_incoming(current_user.id))
        )
        return {"pending_invites_count": count}

    @app.after_request
    def _apply_security_headers(response):
        # HSTS is left to Caddy (it sets it automatically for HTTPS sites)
        # — setting it here too would be redundant and, if this app is
        # ever run without Caddy in front, actively wrong.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    @app.route("/health")
    def health():
        return {"status": "ok"}

    @app.errorhandler(404)
    def _not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def _server_error(error):
        # Flask already logs unhandled exceptions via app.logger (which
        # configure_logging() points at stdout as structured JSON in
        # production) — this handler only swaps the response body for a
        # branded page that never leaks a traceback to the client.
        return render_template("errors/500.html"), 500

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
