import os

from app import create_app
from app.extensions import socketio
from config.config import config_by_name

env = os.environ.get("FLASK_ENV", "development")
config_class = config_by_name.get(env, config_by_name["development"])
app = create_app(f"config.config.{config_class.__name__}")

if __name__ == "__main__":
    # socketio.run() wraps Werkzeug's dev server with WebSocket support —
    # plain app.run() would leave /socket.io/ requests (real-time duels)
    # unhandled. Production doesn't take this branch at all: Gunicorn's
    # eventlet worker (see gunicorn.conf.py) serves `app` directly the
    # same way it always has, no socketio.run() involved.
    socketio.run(app, debug=app.config.get("DEBUG", False), allow_unsafe_werkzeug=True)
