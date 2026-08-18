from dataclasses import dataclass
from datetime import datetime

from app.extensions import db
from app.models import ChatMessage, ChatReport, Notification, PlayerStats

MAX_LENGTH = 500
COOLDOWN_SECONDS = 3
DUPLICATE_WINDOW_SECONDS = 60
FLAG_REPEATED_CHAR_RUN = 5

DEFAULT_ROOM = "global"

# Rule-based, deterministic, local — same "no black box" spirit as the
# rest of the app's generators (no external moderation API). Deliberately
# not exhaustive; catches clear-cut cases while staying easy to extend.
# Lowercase, no accents needed since _analyze_violation normalizes first.
VIOLATION_TERMS = {
    "arrombado", "babaca", "bosta", "burro", "canalha", "cretino",
    "desgracado", "estupido", "fdp", "filho da puta", "idiota", "imbecil",
    "lixo", "merda", "otario", "porra", "puta", "retardado", "vagabundo",
    "vadia", "viado",
}


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


def unread_count(user_id: int, room: str = DEFAULT_ROOM, cap: int = 99) -> int:
    """How many messages from *other* players landed since this user last
    opened the chat — the navbar badge's count. Capped so a player who
    never once opened chat doesn't see a scary triple-digit number; the
    badge itself renders "9+" past a much lower visual cap anyway."""
    stats = PlayerStats.query.filter_by(user_id=user_id).first()
    last_seen = stats.last_seen_chat_at if stats else None
    q = ChatMessage.query.filter(ChatMessage.room == room, ChatMessage.user_id != user_id)
    if last_seen is not None:
        q = q.filter(ChatMessage.created_at > last_seen)
    return q.limit(cap).count()


def mark_seen(user_id: int, room: str = DEFAULT_ROOM) -> None:
    """Called when the user opens the chat page — resets their unread
    badge back to zero going forward."""
    stats = PlayerStats.query.filter_by(user_id=user_id).first()
    if stats is None:
        stats = PlayerStats(user_id=user_id)
        db.session.add(stats)
    stats.last_seen_chat_at = datetime.utcnow()
    db.session.commit()


@dataclass
class ReportResult:
    is_violation: bool
    reason: str


def report_message(message_id: int, reporter_id: int) -> ReportResult:
    """A denúncia now gets analyzed on the spot instead of just flipping a
    flag and waiting for a human — see _analyze_violation. The verdict is
    recorded (ChatReport, one row per reporter+message so re-clicking
    "denunciar" doesn't spam duplicate notifications) and handed back to
    both sides: the caller gets the ReportResult for immediate inline
    feedback, and a Notification is written for each of the reporter and
    the reported player so the outcome is visible later too, wherever
    they happen to see it first."""
    message = ChatMessage.query.filter_by(id=message_id).first()
    if message is None:
        raise ChatError("Mensagem não encontrada.")
    if message.user_id == reporter_id:
        raise ChatError("Você não pode denunciar sua própria mensagem.")
    if ChatReport.query.filter_by(message_id=message_id, reporter_id=reporter_id).first() is not None:
        raise ChatError("Você já denunciou esta mensagem.")

    is_violation, reason = _analyze_violation(message.content)
    message.is_flagged = message.is_flagged or is_violation

    db.session.add(ChatReport(
        message_id=message.id,
        reporter_id=reporter_id,
        reported_user_id=message.user_id,
        content_snapshot=message.content,
        is_violation=is_violation,
        reason=reason,
    ))

    snippet = message.content if len(message.content) <= 80 else message.content[:77] + "..."
    db.session.add(Notification(
        user_id=reporter_id,
        type="report_result",
        payload={"is_violation": is_violation, "reason": reason, "snippet": snippet},
    ))
    db.session.add(Notification(
        user_id=message.user_id,
        type="report_against_you",
        payload={"is_violation": is_violation, "reason": reason, "snippet": snippet},
    ))

    db.session.commit()
    return ReportResult(is_violation=is_violation, reason=reason)


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


def _analyze_violation(content: str) -> tuple[bool, str]:
    """Rule-based check for whether a reported message actually violates
    the chat's content policy — deterministic and local, same spirit as
    _looks_like_spam. Returns (is_violation, human-readable reason)."""
    normalized = content.lower()
    hit = next((term for term in VIOLATION_TERMS if term in normalized), None)
    if hit is not None:
        return True, "A mensagem contém linguagem ofensiva."
    if _looks_like_spam(content):
        return True, "A mensagem foi identificada como spam (caixa alta ou repetição excessiva de caracteres)."
    return False, "Nenhuma violação das regras do chat foi encontrada nesta mensagem."
