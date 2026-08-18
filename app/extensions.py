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
from flask_socketio import SocketIO

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
csrf = CSRFProtect()
# Storage backend is set from config (RATELIMIT_STORAGE_URI) at init_app
# time — defaults to in-memory, which only enforces correctly with a
# single worker process. Point it at Redis for multi-worker production.
limiter = Limiter(key_func=get_remote_address)
# Real-time transport for duels (see app/duels/) — the only part of this
# app that needs one; everything else stays plain request/response. Async
# mode and message_queue are set from config at init_app time: "threading"
# and no queue by default (single-process, works out of the box for dev
# and a single-worker deploy), "eventlet" + a Redis SOCKETIO_MESSAGE_QUEUE
# URL for a real multi-worker production run — same "in-memory by default,
# point it at Redis for multi-worker" pattern as the rate limiter above.
socketio = SocketIO()
