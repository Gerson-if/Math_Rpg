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

    # Difficulty engine defaults — used by the mathematics module,
    # kept here so tuning doesn't require touching business logic.
    DIFFICULTY_LEVELS = 5
    MASTERY_REVIEW_THRESHOLD = 0.75  # below this, a topic is queued for review


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'instance' / 'dev.db'}"
    )


class TestingConfig(BaseConfig):
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


class ProductionConfig(BaseConfig):
    DEBUG = False
    # Expected to be a postgres:// / postgresql:// URL provided via env var.
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")

    def __init__(self):
        if not self.SQLALCHEMY_DATABASE_URI:
            raise RuntimeError("DATABASE_URL must be set in production")


config_by_name = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}
