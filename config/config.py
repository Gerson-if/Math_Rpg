import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Load .env in local/dev environments (no-op if python-dotenv isn't there
# or if there's no .env file, e.g. in production where env vars are
# injected by the platform).
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


class BaseConfig:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-key-change-me")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    WTF_CSRF_ENABLED = True

    # Session/remember-me cookies. SECURE is deliberately left off here —
    # it makes the browser refuse to send the cookie over plain HTTP,
    # which is exactly how local dev runs. ProductionConfig turns it on,
    # since Caddy terminates HTTPS in front of the app there.
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"

    # Difficulty engine defaults — used by the mathematics module,
    # kept here so tuning doesn't require touching business logic.
    DIFFICULTY_LEVELS = 5
    MASTERY_REVIEW_THRESHOLD = 0.75  # below this, a topic is queued for review

    # Rate limiting (Flask-Limiter). In-memory storage only enforces
    # correctly within a single process — set RATELIMIT_STORAGE_URI to a
    # Redis URI (e.g. redis://localhost:6379) for multi-worker Gunicorn.
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_DEFAULT = "200 per hour"  # RATELIMIT_DEFAULT is a single delimited string, not a list
    RATELIMIT_HEADERS_ENABLED = True

    # Real-time duels (Flask-SocketIO). "threading" needs no monkey-patching
    # and works fine for dev and a single Gunicorn worker; production with
    # more than one worker needs "eventlet" (see gunicorn.conf.py's eventlet
    # worker class, which monkey-patches automatically on boot) *and* a
    # shared message queue so events reach clients connected to a different
    # worker — same "in-memory by default, Redis for multi-worker" pattern
    # as RATELIMIT_STORAGE_URI above.
    SOCKETIO_ASYNC_MODE = os.environ.get("SOCKETIO_ASYNC_MODE", "threading")
    SOCKETIO_MESSAGE_QUEUE = os.environ.get("SOCKETIO_MESSAGE_QUEUE")  # e.g. redis://localhost:6379


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'dev.db'}"
    )


class TestingConfig(BaseConfig):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    RATELIMIT_ENABLED = False  # tests hit routes far more than a real user would


class ProductionConfig(BaseConfig):
    DEBUG = False
    # Expected to be a postgres:// / postgresql:// URL provided via env var.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")

    # Only sent over HTTPS — safe to require here because Caddy is the
    # one terminating TLS in front of the app in production (see Caddyfile).
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True

    def __init__(self):
        if not self.SQLALCHEMY_DATABASE_URI:
            raise RuntimeError("DATABASE_URL must be set in production")


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
