from dataclasses import dataclass
from datetime import datetime, timedelta

from app.extensions import db
from app.models import ChatMessage, ChatModeration, ChatReport, Notification, PlayerStats, User

MAX_LENGTH = 500
COOLDOWN_SECONDS = 3
DUPLICATE_WINDOW_SECONDS = 60
FLAG_REPEATED_CHAR_RUN = 5

DEFAULT_ROOM = "global"

# Escalation ladder for *confirmed* violations (offensive language caught
# by the proactive scan on send, or a report that _analyze_violation
# confirms) — index 0 is the consequence for the 1st violation, index 1
# the 2nd, and so on; the last entry repeats for every violation past the
# ladder's length. None = a warning only, a timedelta = a temporary chat
# mute, "ban" = the account itself is deactivated (blocks login — see
# auth.routes.login and app/__init__.py's _enforce_account_ban). Never
# resets on its own, so a repeat offender keeps climbing instead of
# getting an unlimited string of free warnings.
ESCALATION_LADDER = [
    None,
    timedelta(minutes=15),
    timedelta(hours=2),
    timedelta(hours=24),
    "ban",
]

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


@dataclass
class ModerationWarning:
    """Handed back to the sender only (never broadcast) when their own
    message trips the automatic scan. `action` is "warning" for a first
    offense or a spam-only heuristic hit (never punished on its own — see
    _looks_like_spam's docstring), or "muted"/"banned" once offensive
    language pushes them further up ESCALATION_LADDER."""

    action: str  # "warning" | "muted" | "banned"
    reason: str
    muted_until: datetime | None = None


def send_message(user_id: int, content: str, room: str = DEFAULT_ROOM) -> ChatMessage:
    """Returns the persisted ChatMessage, same as before — a moderation
    warning triggered by *this* message (if any) is attached as
    `.moderation_warning` (a plain instance attribute, not a mapped
    column: never persisted, meant only for the caller of this one
    request to show the sender a private heads-up) rather than changing
    the return type, so existing call sites that only care about the
    message itself don't need to change."""
    content = content.strip()
    if not content:
        raise ChatError("Mensagem vazia.")
    if len(content) > MAX_LENGTH:
        raise ChatError(f"Mensagem muito longa (máx. {MAX_LENGTH} caracteres).")

    moderation = ChatModeration.query.filter_by(user_id=user_id).first()
    if moderation and moderation.muted_until and moderation.muted_until > datetime.utcnow():
        remaining = moderation.muted_until - datetime.utcnow()
        raise ChatError(f"Você está silenciado no chat por mais {_format_remaining(remaining)}.")

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

    # Proactive scan — every message is checked, not just ones a human
    # bothers to report (see module docstring-equivalent comment on
    # ESCALATION_LADDER above). Offensive language is a real, escalating
    # violation; the spam heuristic alone stays a private heads-up and
    # never counts toward a mute/ban — typing in caps once is usually just
    # excitement, not the kind of repeat bad behavior this ladder targets.
    term_hit = _contains_violation_terms(content)
    is_spam = _looks_like_spam(content)

    message = ChatMessage(
        user_id=user_id,
        room=room,
        content=content,
        is_flagged=bool(term_hit) or is_spam,
    )
    db.session.add(message)

    warning = None
    if term_hit:
        warning = _register_violation(user_id, "A mensagem contém linguagem ofensiva.")
    elif is_spam:
        warning = ModerationWarning(
            action="warning",
            reason="Sua mensagem foi identificada como possível spam (caixa alta ou repetição excessiva de caracteres) — evite esse tipo de formatação.",
        )

    db.session.commit()
    message.moderation_warning = warning
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

    # A report is a human vouching that something's wrong — stronger
    # signal than the automatic send-time scan alone, so (unlike
    # send_message above) a confirmed report escalates the ladder even
    # for a spam-pattern hit, not just offensive language. But offensive
    # language already escalated once at send time (see send_message) —
    # re-deriving that exact condition here (rather than re-running it
    # unconditionally) avoids double-counting the same message as two
    # separate violations just because it was both auto-flagged and later
    # reported.
    if is_violation and not _contains_violation_terms(message.content):
        _register_violation(message.user_id, reason)

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


def _contains_violation_terms(content: str) -> bool:
    normalized = content.lower()
    return any(term in normalized for term in VIOLATION_TERMS)


def _analyze_violation(content: str) -> tuple[bool, str]:
    """Rule-based check for whether a reported message actually violates
    the chat's content policy — deterministic and local, same spirit as
    _looks_like_spam. Returns (is_violation, human-readable reason)."""
    if _contains_violation_terms(content):
        return True, "A mensagem contém linguagem ofensiva."
    if _looks_like_spam(content):
        return True, "A mensagem foi identificada como spam (caixa alta ou repetição excessiva de caracteres)."
    return False, "Nenhuma violação das regras do chat foi encontrada nesta mensagem."


def _format_remaining(delta: timedelta) -> str:
    total_minutes = max(1, int(delta.total_seconds() // 60))
    if total_minutes < 60:
        return f"{total_minutes}min"
    hours, minutes = divmod(total_minutes, 60)
    if hours < 24:
        return f"{hours}h{minutes:02d}min" if minutes else f"{hours}h"
    days, hours = divmod(hours, 24)
    return f"{days}d{hours}h" if hours else f"{days}d"


def _register_violation(user_id: int, reason: str) -> ModerationWarning:
    """Applies the next rung of ESCALATION_LADDER for this user and
    records why — called for every confirmed violation, whether caught by
    the proactive scan in send_message or confirmed via a report. Always
    notifies the offending player (a warning explaining what happened and
    what's next escalates the deterrent even on a first offense, when no
    restriction is actually applied yet)."""
    moderation = ChatModeration.query.filter_by(user_id=user_id).first()
    if moderation is None:
        moderation = ChatModeration(user_id=user_id, violation_count=0)
        db.session.add(moderation)

    moderation.violation_count += 1
    moderation.last_violation_at = datetime.utcnow()
    moderation.last_reason = reason

    tier = ESCALATION_LADDER[min(moderation.violation_count - 1, len(ESCALATION_LADDER) - 1)]

    if tier is None:
        action = "warning"
        muted_until = None
    elif tier == "ban":
        action = "banned"
        muted_until = None
        moderation.muted_until = None
        user = User.query.get(user_id)
        if user is not None:
            user.is_active = False
    else:
        action = "muted"
        muted_until = datetime.utcnow() + tier
        moderation.muted_until = muted_until

    db.session.add(Notification(
        user_id=user_id,
        type="chat_violation",
        payload={
            "action": action,
            "reason": reason,
            "violation_count": moderation.violation_count,
            "muted_label": _format_remaining(tier) if isinstance(tier, timedelta) else None,
        },
    ))

    return ModerationWarning(action=action, reason=reason, muted_until=muted_until)
