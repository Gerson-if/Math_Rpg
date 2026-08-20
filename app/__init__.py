"""
Application factory.

The app is built as a set of feature packages (auth, users, mathematics,
progression, ranking, achievements, chat, api) that each expose a Flask
Blueprint. This keeps the codebase modular from day one and matches the
architecture described in the project spec.
"""
import click
from flask import Flask, redirect, render_template, url_for
from flask_login import current_user

from app.extensions import db, migrate, login_manager, csrf, limiter, socketio
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
    # cors_allowed_origins deliberately left at its default (same-origin
    # only) — this app is never embedded/consumed cross-origin, and the
    # duel handlers authenticate purely off the Flask-Login session
    # cookie, so accepting a handshake from another origin would be a
    # real hole, not just noise.
    socketio.init_app(
        app,
        async_mode=app.config.get("SOCKETIO_ASYNC_MODE", "threading"),
        message_queue=app.config.get("SOCKETIO_MESSAGE_QUEUE"),
    )

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
    from app.duels.routes import duels_bp
    from app.diagnostics.routes import diagnostics_bp
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
    app.register_blueprint(duels_bp)
    app.register_blueprint(diagnostics_bp)
    app.register_blueprint(api_bp, url_prefix="/api")

    # Socket.IO event handlers register themselves on the shared `socketio`
    # instance via decorators — importing the module is what wires them up.
    from app.duels import socket_events  # noqa: F401

    @app.context_processor
    def _inject_pending_invites_count():
        """Small badge count for the navbar's "Amigos" link — friend
        requests + dungeon invites + duel challenges waiting on the
        current user. Cheap (indexed COUNT-shaped queries) and only runs
        when logged in."""
        from flask_login import current_user

        if not current_user.is_authenticated:
            return {}
        from app.services import friends_service, dungeon_service, duel_service

        count = (
            len(friends_service.list_incoming_requests(current_user.id))
            + len(dungeon_service.list_incoming(current_user.id))
            + len(duel_service.list_pending_challenges(current_user.id))
        )
        return {"pending_invites_count": count}

    @app.context_processor
    def _inject_chat_unread_count():
        """Small badge count for the navbar's "Chat" link — same pattern as
        the friends/invites badge above, just for unseen global chat
        messages (see chat_service.unread_count)."""
        from flask_login import current_user

        if not current_user.is_authenticated:
            return {}
        from app.services import chat_service

        return {"chat_unread_count": chat_service.unread_count(current_user.id)}

    @app.context_processor
    def _inject_notifications_unread_count():
        """Small badge count for the navbar's notification bell — unread
        Notification rows (achievement unlocks, chat-report verdicts, ...).
        Same pattern as the two badges above."""
        from flask_login import current_user

        if not current_user.is_authenticated:
            return {}
        from app.models import Notification

        count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return {"notifications_unread_count": count}

    @app.before_request
    def _enforce_account_ban():
        # Escalating chat violations can deactivate an account outright
        # (see chat_service.ESCALATION_LADDER) — that blocks *new* logins
        # for free (flask_login.login_user refuses an inactive user), but
        # someone already mid-session keeps their cookie until it expires
        # unless something actively checks is_active on each request. This
        # is that check: catches it within one request instead of leaving
        # a banned player playing until their session naturally lapses.
        if current_user.is_authenticated and not current_user.is_active:
            from flask import flash
            from flask_login import logout_user

            logout_user()
            flash("Sua conta foi suspensa por violações repetidas das regras do chat.", "error")

    @app.after_request
    def _apply_security_headers(response):
        # HSTS is left to Caddy (it sets it automatically for HTTPS sites)
        # — setting it here too would be redundant and, if this app is
        # ever run without Caddy in front, actively wrong.
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    @app.route("/")
    def index():
        # No content lives at "/" itself — it's just the front door.
        # Without this route, hitting the bare domain 404s instead of
        # landing on login (logged out) or the dashboard (logged in).
        if current_user.is_authenticated:
            return redirect(url_for("users.dashboard"))
        return redirect(url_for("auth.login"))

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
