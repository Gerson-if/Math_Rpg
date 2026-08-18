from app.extensions import db
from app.models.base import TimestampMixin


class Duel(db.Model, TimestampMixin):
    """A real-time 1v1 duel between two accepted friends — see
    app/services/duel_service.py (server-authoritative round resolution,
    same principle as the solo battle's answer_question route) and
    app/duels/socket_events.py (the Socket.IO transport that pushes state
    to both clients instantly instead of HTMX polling).

    current_prompt/current_answer hold the *shared* question both players
    are racing to answer — current_answer is never sent to either client,
    only compared against server-side in submit_answer()."""

    __tablename__ = "duels"

    STATUS_PENDING = "pending"
    STATUS_ACTIVE = "active"
    STATUS_FINISHED = "finished"
    STATUS_DECLINED = "declined"

    id = db.Column(db.Integer, primary_key=True)
    room_code = db.Column(db.String(24), unique=True, nullable=False, index=True)
    challenger_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    opponent_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    topic_id = db.Column(db.Integer, db.ForeignKey("topics.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=STATUS_PENDING)

    challenger_hp = db.Column(db.Integer, nullable=False, default=100)
    opponent_hp = db.Column(db.Integer, nullable=False, default=100)
    winner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    current_prompt = db.Column(db.String(200), nullable=True)
    current_answer = db.Column(db.String(200), nullable=True)
    round_number = db.Column(db.Integer, nullable=False, default=0)

    challenger = db.relationship("User", foreign_keys=[challenger_id])
    opponent = db.relationship("User", foreign_keys=[opponent_id])
    winner = db.relationship("User", foreign_keys=[winner_id])
    topic = db.relationship("Topic")

    def hp_for(self, user_id: int) -> int:
        return self.challenger_hp if user_id == self.challenger_id else self.opponent_hp

    def opponent_of(self, user_id: int) -> "int | None":
        if user_id == self.challenger_id:
            return self.opponent_id
        if user_id == self.opponent_id:
            return self.challenger_id
        return None
