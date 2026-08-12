"""Fase 8: Flask-Limiter is disabled in the shared TestingConfig (tests
hit routes far more than a real user would), so this file builds its own
app instance with rate limiting force-enabled to prove the limits are
actually wired up, not just present in code.

Note: Limiter.enabled is cached as an instance attribute the moment
init_app() runs (it reads config.setdefault(...) once), and `limiter` is
a module-level singleton shared by every create_app() call in the
process. Flipping app.config["RATELIMIT_ENABLED"] *after* create_app()
has already returned is too late — the override has to be in the config
class *before* create_app() calls limiter.init_app(app)."""
from config.config import TestingConfig
from app import create_app
from app.extensions import db as _db


class _RateLimitedTestingConfig(TestingConfig):
    RATELIMIT_ENABLED = True


def _limited_app():
    app = create_app(_RateLimitedTestingConfig)
    with app.app_context():
        _db.create_all()
    return app


def test_login_is_rate_limited_after_repeated_attempts():
    app = _limited_app()
    with app.app_context():
        client = app.test_client()
        statuses = [
            client.post("/auth/login", data={"email": "x@example.com", "password": "wrong"}).status_code
            for _ in range(15)
        ]
        assert 429 in statuses, f"expected a 429 among {statuses}"
        _db.session.remove()
        _db.drop_all()


def test_register_is_rate_limited_after_repeated_attempts():
    app = _limited_app()
    with app.app_context():
        client = app.test_client()
        statuses = []
        for i in range(15):
            resp = client.post("/auth/register", data={
                "username": f"user{i}", "email": f"user{i}@example.com",
                "password": "senhaforte123", "confirm_password": "senhaforte123",
            })
            statuses.append(resp.status_code)
        assert 429 in statuses, f"expected a 429 among {statuses}"
        _db.session.remove()
        _db.drop_all()
