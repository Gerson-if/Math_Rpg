from datetime import datetime

from app.extensions import db
from app.models import ChatMessage

MAX_LENGTH = 500
COOLDOWN_SECONDS = 3
DUPLICATE_WINDOW_SECONDS = 60
FLAG_REPEATED_CHAR_RUN = 5

DEFAULT_ROOM = "global"


class ChatError(Exception):
    """Raised when a message is rejected — empty, too long, or spammy."""


def get_recent_messages(room: str = DEFAULT_ROOM, limit: int = 50) -> list[ChatMessage]:
    messages = (
        ChatMessage.query.filter_by(room=room)
        .order_by(ChatMessage.created_at.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(messages))


def send_message(user_id: int, content: str, room: str = DEFAULT_ROOM) -> ChatMessage:
    content = content.strip()
    if not content:
        raise ChatError("Mensagem vazia.")
    if len(content) > MAX_LENGTH:
        raise ChatError(f"Mensagem muito longa (máx. {MAX_LENGTH} caracteres).")

    last = (
        ChatMessage.query.filter_by(user_id=user_id, room=room)
        .order_by(ChatMessage.created_at.desc())
        .first()
    )
    if last is not None:
        elapsed = (datetime.utcnow() - last.created_at).total_seconds()
        if elapsed < COOLDOWN_SECONDS:
            raise ChatError("Aguarde um instante antes de enviar outra mensagem.")
        if elapsed < DUPLICATE_WINDOW_SECONDS and last.content == content:
            raise ChatError("Você já enviou essa mensagem.")

    message = ChatMessage(
        user_id=user_id,
        room=room,
        content=content,
        is_flagged=_looks_like_spam(content),
    )
    db.session.add(message)
    db.session.commit()
    return message


def _looks_like_spam(content: str) -> bool:
    """Soft heuristic — flags for moderation review, never blocks sending."""
    if len(content) >= 8 and content.isupper():
        return True

    run = 1
    for prev, curr in zip(content, content[1:]):
        if curr == prev and not curr.isspace():
            run += 1
            if run >= FLAG_REPEATED_CHAR_RUN:
                return True
        else:
            run = 1
    return False
