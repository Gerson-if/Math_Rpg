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


def read_token(token: str, max_age: int = 300, return_timestamp: bool = False):
    """max_age is in seconds — 5 minutes is generous for answering one
    question but still bounds how long a token (and thus an inflated
    response_time) can be replayed."""
    try:
        return _serializer().loads(token, max_age=max_age, return_timestamp=return_timestamp)
    except (BadSignature, SignatureExpired) as exc:
        raise TokenError(str(exc)) from exc
