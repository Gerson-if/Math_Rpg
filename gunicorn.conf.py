"""
Gunicorn config for production. Run with:

    gunicorn -c gunicorn.conf.py run:app

Everything here is overridable via environment variables so the same
config file works across different hosts/plans without editing code.
"""
import multiprocessing
import os

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")

# Real-time duels (Flask-SocketIO) need an async-capable worker — sync
# workers block on every request/connection, which is fatal for a
# WebSocket that's supposed to stay open. eventlet monkey-patches the
# process at boot automatically (Gunicorn's own EventletWorker does this
# before the app is even imported), so nothing else in this app needs to
# call eventlet.monkey_patch() itself.
#
# IMPORTANT: a WebSocket connection is pinned to whichever worker process
# accepted it. With more than one worker, two duelists connected to
# *different* workers can't see each other's moves unless Socket.IO is
# given a shared message queue to relay events between workers — set
# SOCKETIO_MESSAGE_QUEUE (a Redis URL) for that. Without it, keep exactly
# one worker; a single eventlet worker still handles plenty of concurrent
# connections via greenlets; it's not the same limitation a single *sync*
# worker would have.
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "eventlet")
_default_workers = 1 if worker_class == "eventlet" and not os.environ.get("SOCKETIO_MESSAGE_QUEUE") else min(multiprocessing.cpu_count() * 2 + 1, 5)
workers = int(os.environ.get("GUNICORN_WORKERS", _default_workers))
threads = int(os.environ.get("GUNICORN_THREADS", 1))

timeout = int(os.environ.get("GUNICORN_TIMEOUT", 30))
graceful_timeout = 30
keepalive = 5

# Recycle workers periodically to bound the impact of any slow memory
# leak — jitter avoids every worker restarting at the same instant.
max_requests = 1000
max_requests_jitter = 100

accesslog = "-"   # stdout — the app also logs its own structured JSON per
errorlog = "-"    # request (app/logging_config.py); this covers Gunicorn's
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")  # own worker/startup/crash events.

# Rate limiting only enforces correctly across all these workers if
# RATELIMIT_STORAGE_URI points at a shared backend (Redis) instead of the
# in-memory default — see config/config.py and the README.
