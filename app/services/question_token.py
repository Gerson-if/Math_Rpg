"""
Keeps the correct answer to a generated question out of the database and
out of the client's view, without needing a session or a Question row for
every practice attempt.

The answer + topic + difficulty are signed (itsdangerous) and embedded as a
hidden field in the question form. The signature also carries a timestamp,
which doubles as the "question shown at" time used to compute response_time
when the answer comes back — no server-side state to clean up.
"""
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask import current_app

_SALT = "math-question"


class TokenError(Exception):
    """Raised for a missing, tampered, or expired question token."""


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=_SALT)


def make_token(topic_slug: str, difficulty: int, answer: str) -> str:
    return _serializer().dumps({"topic": topic_slug, "difficulty": difficulty, "answer": answer})


def read_token(token: str, max_age: int = 1800, return_timestamp: bool = False):
    """max_age is in seconds. Doesn't need to tightly bound response_time
    forgery on its own — app/mathematics/routes.py separately clamps
    elapsed_ms to 10 minutes regardless of this value — so it can afford
    to be generous: 30 minutes covers a player who steps away mid-battle
    (reads a chronicle, gets distracted) without silently stranding them
    on an expired question that no longer accepts answers."""
    try:
        return _serializer().loads(token, max_age=max_age, return_timestamp=return_timestamp)
    except (BadSignature, SignatureExpired) as exc:
        raise TokenError(str(exc)) from exc
