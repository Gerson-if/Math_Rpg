"""
Structured logging for production (Fase 8).

Dev/tests keep a human-readable line format — nobody wants to read JSON in
a terminal while iterating. Anywhere else (DEBUG=False, i.e. behind
Gunicorn) logs are one JSON object per line on stdout, which is what every
cloud log aggregator (Docker, systemd/journald, Render, Fly, etc.) expects
without extra configuration — no log files to rotate or ship by hand.
"""
import json
import logging
import sys
from datetime import datetime, timezone

from flask import Flask, request
from flask_login import current_user


class JsonFormatter(logging.Formatter):
    _EXTRA_FIELDS = ("method", "path", "status", "remote_addr", "user_id")

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in self._EXTRA_FIELDS:
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(app: Flask) -> None:
    handler = logging.StreamHandler(sys.stdout)
    if app.debug or app.testing:
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    else:
        handler.setFormatter(JsonFormatter())

    app.logger.handlers = [handler]
    app.logger.setLevel(logging.INFO)
    app.logger.propagate = False

    @app.after_request
    def _log_request(response):
        user_id = current_user.id if current_user.is_authenticated else None
        app.logger.info(
            "request",
            extra={
                "method": request.method,
                "path": request.path,
                "status": response.status_code,
                "remote_addr": request.remote_addr,
                "user_id": user_id,
            },
        )
        return response
