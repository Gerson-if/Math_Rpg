import json
import logging

from config.config import TestingConfig
from app import create_app
from app.extensions import db as _db
from app.logging_config import JsonFormatter


def test_json_formatter_produces_valid_json_with_expected_fields():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="app", level=logging.INFO, pathname=__file__, lineno=1,
        msg="request", args=(), exc_info=None,
    )
    record.method = "GET"
    record.path = "/dashboard"
    record.status = 200
    record.remote_addr = "127.0.0.1"
    record.user_id = 42

    parsed = json.loads(formatter.format(record))

    assert parsed["message"] == "request"
    assert parsed["level"] == "INFO"
    assert parsed["method"] == "GET"
    assert parsed["status"] == 200
    assert parsed["user_id"] == 42
    assert "timestamp" in parsed


def test_json_formatter_includes_traceback_on_exceptions():
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = logging.LogRecord(
            name="app", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="unhandled exception", args=(), exc_info=sys.exc_info(),
        )
    parsed = json.loads(formatter.format(record))
    assert "ValueError: boom" in parsed["exception"]


def test_404_renders_the_branded_error_page(client, db):
    resp = client.get("/esta-rota-nao-existe")
    assert resp.status_code == 404
    assert "Página não encontrada" in resp.data.decode()


def test_security_headers_are_present_on_every_response(client, db):
    resp = client.get("/health")
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "DENY"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


class _ExceptionPropagationTestingConfig(TestingConfig):
    # Flask re-raises exceptions straight to the test client when TESTING
    # is combined with the default PROPAGATE_EXCEPTIONS behavior — turn
    # that off so the 500 handler actually runs, same as it would for a
    # real user hitting a real bug in production.
    PROPAGATE_EXCEPTIONS = False


def test_500_renders_the_branded_error_page_without_a_traceback():
    app = create_app(_ExceptionPropagationTestingConfig)

    @app.route("/_boom")
    def _boom():
        raise RuntimeError("deliberate failure for the test")

    with app.app_context():
        _db.create_all()
        client = app.test_client()
        resp = client.get("/_boom")

        assert resp.status_code == 500
        body = resp.data.decode()
        assert "Algo deu errado" in body
        assert "RuntimeError" not in body
        assert "Traceback" not in body

        _db.session.remove()
        _db.drop_all()
