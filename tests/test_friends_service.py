import pytest

from app.extensions import db
from app.models import User
from app.services import friends_service


def _make_user(username, email=None):
    user = User(email=email or f"{username}@example.com", username=username)
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.flush()
    return user


def test_send_request_creates_a_pending_friendship(app, db):
    with app.app_context():
        alice = _make_user("alice")
        bob = _make_user("bob")
        db.session.commit()

        friendship = friends_service.send_request(alice.id, "bob")

        assert friendship.requester_id == alice.id
        assert friendship.addressee_id == bob.id
        assert friendship.status == "pending"


def test_send_request_to_unknown_username_raises(app, db):
    with app.app_context():
        alice = _make_user("alice")
        db.session.commit()

        with pytest.raises(friends_service.FriendError):
            friends_service.send_request(alice.id, "ninguem")


def test_send_request_to_self_raises(app, db):
    with app.app_context():
        alice = _make_user("alice")
        db.session.commit()

        with pytest.raises(friends_service.FriendError):
            friends_service.send_request(alice.id, "alice")


def test_send_request_twice_raises(app, db):
    with app.app_context():
        alice = _make_user("alice")
        _make_user("bob")
        db.session.commit()

        friends_service.send_request(alice.id, "bob")
        with pytest.raises(friends_service.FriendError):
            friends_service.send_request(alice.id, "bob")


def test_respond_accept_makes_them_friends_both_ways(app, db):
    with app.app_context():
        alice = _make_user("alice")
        bob = _make_user("bob")
        db.session.commit()

        friendship = friends_service.send_request(alice.id, "bob")
        friends_service.respond(friendship.id, bob.id, accept=True)

        assert friends_service.are_friends(alice.id, bob.id)
        assert [u.username for u in friends_service.list_friends(alice.id)] == ["bob"]
        assert [u.username for u in friends_service.list_friends(bob.id)] == ["alice"]


def test_respond_decline_does_not_make_them_friends(app, db):
    with app.app_context():
        alice = _make_user("alice")
        bob = _make_user("bob")
        db.session.commit()

        friendship = friends_service.send_request(alice.id, "bob")
        friends_service.respond(friendship.id, bob.id, accept=False)

        assert not friends_service.are_friends(alice.id, bob.id)


def test_only_the_addressee_can_respond(app, db):
    with app.app_context():
        alice = _make_user("alice")
        _make_user("bob")
        db.session.commit()

        friendship = friends_service.send_request(alice.id, "bob")
        with pytest.raises(friends_service.FriendError):
            friends_service.respond(friendship.id, alice.id, accept=True)  # requester, not addressee


def test_remove_deletes_an_accepted_friendship(app, db):
    with app.app_context():
        alice = _make_user("alice")
        bob = _make_user("bob")
        db.session.commit()

        friendship = friends_service.send_request(alice.id, "bob")
        friends_service.respond(friendship.id, bob.id, accept=True)
        friends_service.remove(friendship.id, alice.id)

        assert not friends_service.are_friends(alice.id, bob.id)
        assert friends_service.list_friends(alice.id) == []


def test_list_friend_rows_exposes_the_friendship_id(app, db):
    with app.app_context():
        alice = _make_user("alice")
        bob = _make_user("bob")
        db.session.commit()

        friendship = friends_service.send_request(alice.id, "bob")
        friends_service.respond(friendship.id, bob.id, accept=True)

        rows = friends_service.list_friend_rows(alice.id)
        assert rows == [(friendship.id, bob)]
