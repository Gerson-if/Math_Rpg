"""
Progression blueprint. XP/level/mastery *calculation* lives in
app/services/progression_service.py and runs right after each Attempt is
saved (see app/mathematics/routes.py) — this blueprint just surfaces the
results, starting with the review queue described in section 4 of the
spec ("Você domina muito bem X, mas apresentou uma queda recente em Y").
"""
from datetime import datetime

from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.models import Mastery

progression_bp = Blueprint("progression", __name__, url_prefix="/progressao")


@progression_bp.route("/revisao")
@login_required
def review_queue():
    items = (
        Mastery.query.filter_by(user_id=current_user.id, needs_review=True)
        .order_by(Mastery.mastery_score.asc())
        .all()
    )
    now = datetime.utcnow()
    # How long it's actually been since practice, alongside the mastery
    # gap — a topic that's both weak AND stale reads as more urgent than
    # one that's merely weak, even though both already passed the same
    # needs_review threshold.
    days_since = {
        m.id: (now - m.last_practiced_at).days if m.last_practiced_at else None
        for m in items
    }
    return render_template("progression/review.html", items=items, days_since=days_since)
