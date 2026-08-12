"""
Application factory.

The app is built as a set of feature packages (auth, users, mathematics,
progression, ranking, achievements, chat, api) that each expose a Flask
Blueprint. This keeps the codebase modular from day one and matches the
architecture described in the project spec.
"""
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

    return app
