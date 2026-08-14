from unittest.mock import patch

import pytest

from app.services import question_token


def _make_token_at(app, seconds_ago):
    """Builds a token whose signed timestamp looks `seconds_ago` seconds
    in the past — itsdangerous timestamps with time.time() internally, so
    faking that clock is the only reliable way to age a token in a test."""
    with app.app_context():
        real_time = __import__("time").time
        with patch("itsdangerous.timed.time.time", return_value=real_time() - seconds_ago):
            return question_token.make_token("adicao", 1, "7")


def test_a_token_within_the_new_generous_window_is_still_accepted(app):
    # Old default was 300s (5 min) — this would have failed under that,
    # confirming the window was actually widened, not just bumped in a
    # comment.
    token = _make_token_at(app, seconds_ago=20 * 60)
    with app.app_context():
        payload = question_token.read_token(token)
    assert payload["answer"] == "7"


def test_a_token_past_the_new_window_still_expires(app):
    token = _make_token_at(app, seconds_ago=40 * 60)
    with app.app_context():
        with pytest.raises(question_token.TokenError):
            question_token.read_token(token)


def test_a_tampered_token_is_rejected(app):
    with app.app_context():
        token = question_token.make_token("adicao", 1, "7")
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    with app.app_context():
        with pytest.raises(question_token.TokenError):
            question_token.read_token(tampered)
