"""Per-fact spaced-repetition memory — "still shaky on 7×8 specifically",
not just "72% mastery on Tabuada do 7" (see MissedFact's own docstring in
app/models/progression.py for why this is a separate table from Mastery).

Only meaningful for question families with a small, discrete, enumerable
fact space — currently just the tabuada family, wired up in
mathematics_service._gen_tabuada/_gen_tabuada_mista via the fingerprint
this module hands back through app/mathematics/routes.py. Every function
here is a no-op (or returns None) when called with a falsy fingerprint,
so topics that don't participate never touch this table at all.
"""
import random
from datetime import datetime

from app.extensions import db
from app.models import MissedFact

# Three corrects in a row on the same fact and it's not "missed" anymore —
# short enough that a fact actually gets resolved within a normal practice
# session instead of lingering at the bottom of the queue forever, long
# enough that one lucky guess right after a miss doesn't clear it.
RESOLVE_STREAK = 3

# How often a genuinely due fact gets served instead of a fresh random
# question, when there's at least one candidate. Deliberately well under
# 1.0 — a practice session that's ALWAYS re-testing yesterday's mistakes
# never gets to build genuinely new fluency, and feels like a punishment
# loop rather than review.
DUE_BIAS_CHANCE = 0.45

# Cap on how many rows we ever pull per (user, topic) — a player with a
# long tail of half-forgotten facts still only gets a bounded query, and
# the heaviest offenders (highest miss_count) are the ones actually in
# the candidate pool anyway.
_MAX_DUE_CANDIDATES = 20


def record_result(user_id: int, topic_id: int, fingerprint: str | None, is_correct: bool) -> None:
    """Updates (or creates/resolves) the MissedFact row for one answered
    question. Does NOT commit — called from app/mathematics/routes.py
    inside the same request as the Attempt/Mastery update, so it rides
    along on progression_service.process_attempt's single commit rather
    than opening a second transaction for the same answer."""
    if not fingerprint:
        return

    row = MissedFact.query.filter_by(
        user_id=user_id, topic_id=topic_id, fingerprint=fingerprint
    ).first()

    if is_correct:
        if row is None:
            return  # never missed this one — nothing to track
        row.correct_streak += 1
        row.last_seen_at = datetime.utcnow()
        if row.correct_streak >= RESOLVE_STREAK:
            db.session.delete(row)
        return

    if row is None:
        row = MissedFact(user_id=user_id, topic_id=topic_id, fingerprint=fingerprint)
        db.session.add(row)
    else:
        row.miss_count += 1
    row.correct_streak = 0
    row.last_seen_at = datetime.utcnow()


def due_fingerprint(user_id: int, topic_id: int) -> str | None:
    """One fingerprint worth re-testing right now, weighted toward facts
    missed more often — or None, either because nothing's due or because
    the dice didn't land on review this time (see DUE_BIAS_CHANCE), in
    which case the caller just generates a normal random question."""
    if random.random() > DUE_BIAS_CHANCE:
        return None

    rows = (
        MissedFact.query.filter_by(user_id=user_id, topic_id=topic_id)
        .order_by(MissedFact.miss_count.desc(), MissedFact.last_seen_at.asc())
        .limit(_MAX_DUE_CANDIDATES)
        .all()
    )
    if not rows:
        return None

    weights = [row.miss_count for row in rows]
    return random.choices(rows, weights=weights, k=1)[0].fingerprint
