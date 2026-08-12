"""
Gunicorn config for production. Run with:

    gunicorn -c gunicorn.conf.py run:app

Everything here is overridable via environment variables so the same
config file works across different hosts/plans without editing code.
"""
import multiprocessing
import os

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")

# Sync workers are the right default here: the app does normal
# request/response DB work, no long-lived streaming or websockets.
# Formula is the standard Gunicorn recommendation (2 * cores + 1),
# capped so a small box doesn't spawn more workers than it can run well.
workers = int(os.environ.get("GUNICORN_WORKERS", min(multiprocessing.cpu_count() * 2 + 1, 5)))
worker_class = "sync"
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
