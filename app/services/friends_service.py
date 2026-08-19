"""Friends: send/accept/decline a request, list an accepted friend list.
Kept deliberately simple — one `Friendship` row per requested pair, status
moves pending -> accepted/declined. No notifications table dependency here
(unlike achievements) since the friends page itself is the inbox; nothing
else needs to know a request exists.
"""
from app.extensions import db
from app.models import Friendship, User


class FriendError(Exception):
    """Raised for user-facing failures (not found, self-request, duplicate)
    so the route can flash a clear message instead of guessing from None."""


def send_request(requester_id: int, addressee_username: str) -> Friendship:
    addressee = User.query.filter_by(username=addressee_username.strip()).first()
    if addressee is None:
        raise FriendError(f'Nenhum aventureiro chamado "{addressee_username}" foi encontrado.')
    if addressee.id == requester_id:
        raise FriendError("Você não pode enviar um convite de amizade para si mesmo.")

    existing = _find_pair(requester_id, addressee.id)
    if existing is not None:
        if existing.status == Friendship.STATUS_ACCEPTED:
            raise FriendError(f"Você já é amigo de {addressee.username}.")
        if existing.status == Friendship.STATUS_PENDING:
            raise FriendError("Já existe um convite pendente entre vocês.")
        # Previously declined — let them try again with a fresh row.
        existing.status = Friendship.STATUS_PENDING
        existing.requester_id, existing.addressee_id = requester_id, addressee.id
        db.session.commit()
        return existing

    friendship = Friendship(requester_id=requester_id, addressee_id=addressee.id)
    db.session.add(friendship)
    db.session.commit()
    return friendship


def respond(friendship_id: int, addressee_id: int, accept: bool) -> Friendship:
    friendship = Friendship.query.filter_by(
        id=friendship_id, addressee_id=addressee_id, status=Friendship.STATUS_PENDING,
    ).first()
    if friendship is None:
        raise FriendError("Convite não encontrado (ou já respondido).")
    friendship.status = Friendship.STATUS_ACCEPTED if accept else Friendship.STATUS_DECLINED
    db.session.commit()
    return friendship


def remove(friendship_id: int, user_id: int) -> None:
    friendship = Friendship.query.filter(
        Friendship.id == friendship_id,
        Friendship.status == Friendship.STATUS_ACCEPTED,
        db.or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id),
    ).first()
    if friendship is None:
        raise FriendError("Amizade não encontrada.")
    db.session.delete(friendship)
    db.session.commit()


def list_friends(user_id: int) -> list[User]:
    return [user for _friendship_id, user in list_friend_rows(user_id)]


def list_friend_rows(user_id: int) -> list[tuple[int, User]]:
    """Same as list_friends, but keeps the Friendship.id alongside each
    User so templates can build an "unfriend" action without a second
    lookup — list_friends() alone can't do that since accepted rows are
    directional and the "other" user differs per row."""
    rows = Friendship.query.filter(
        Friendship.status == Friendship.STATUS_ACCEPTED,
        db.or_(Friendship.requester_id == user_id, Friendship.addressee_id == user_id),
    ).all()
    return [
        (row.id, row.addressee if row.requester_id == user_id else row.requester)
        for row in rows
    ]


def list_incoming_requests(user_id: int) -> list[Friendship]:
    return Friendship.query.filter_by(
        addressee_id=user_id, status=Friendship.STATUS_PENDING,
    ).all()


def list_outgoing_requests(user_id: int) -> list[Friendship]:
    return Friendship.query.filter_by(
        requester_id=user_id, status=Friendship.STATUS_PENDING,
    ).all()


def are_friends(user_id_a: int, user_id_b: int) -> bool:
    pair = _find_pair(user_id_a, user_id_b)
    return pair is not None and pair.status == Friendship.STATUS_ACCEPTED


def relationship_status(viewer_id: int, other_id: int) -> str:
    """"friends" | "pending_outgoing" | "pending_incoming" | "none" — used
    by the public profile page to decide what friend-request control (if
    any) to show. "none" also covers a previously declined request, since
    send_request already lets a fresh request overwrite one."""
    pair = _find_pair(viewer_id, other_id)
    if pair is None or pair.status == Friendship.STATUS_DECLINED:
        return "none"
    if pair.status == Friendship.STATUS_ACCEPTED:
        return "friends"
    return "pending_outgoing" if pair.requester_id == viewer_id else "pending_incoming"


def _find_pair(user_id_a: int, user_id_b: int) -> Friendship | None:
    return Friendship.query.filter(
        db.or_(
            db.and_(Friendship.requester_id == user_id_a, Friendship.addressee_id == user_id_b),
            db.and_(Friendship.requester_id == user_id_b, Friendship.addressee_id == user_id_a),
        )
    ).first()
