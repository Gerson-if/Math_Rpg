"""
Single place to instantiate Flask extensions so every package can import
them without creating circular imports.
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
# Storage backend is set from config (RATELIMIT_STORAGE_URI) at init_app
# time — defaults to in-memory, which only enforces correctly with a
# single worker process. Point it at Redis for multi-worker production.
limiter = Limiter(key_func=get_remote_address)
