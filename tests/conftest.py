import random

import pytest

from app import create_app
from app.extensions import db as _db


@pytest.fixture(autouse=True)
def _deterministic_random():
    """Python's `random` module is process-wide, not per-test — without
    this, how many random draws a *previous* test happened to consume
    (question generation, crit rolls, loot rarity, ...) shifts what the
    *next* test draws, so a handful of tests that assert on one random
    outcome (not a distribution over many draws) would intermittently
    fail depending on run order alone. Reseeding before every test makes
    each test's random draws reproducible regardless of what ran before
    it or in what order the suite executes."""
    random.seed(1234)
    yield


@pytest.fixture()
def app():
    app = create_app("config.config.TestingConfig")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db(app):
    return _db
