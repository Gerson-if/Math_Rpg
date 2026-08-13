from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.models import User, Subject, Topic
from app.services import dungeon_service


def _make_user(username):
    user = User(email=f"{username}@example.com", username=username)
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.flush()
    return user


def _make_topic(slug="adicao", subject=None):
    if subject is None:
        subject = Subject(slug="operacoes-fundamentais", name="Operações Fundamentais", order=0)
        db.session.add(subject)
        db.session.flush()
    topic = Topic(slug=slug, name="Adição", subject_id=subject.id, order=0, base_difficulty=1)
    db.session.add(topic)
    db.session.flush()
    return topic


def test_send_invite_creates_a_pending_row(app, db):
    with app.app_context():
        alice = _make_user("alice")
        bob = _make_user("bob")
        topic = _make_topic()
        db.session.commit()

        invite = dungeon_service.send_invite(alice.id, bob.id, topic.id)
        assert invite.status == "pending"
        assert invite.expires_at is None


def test_no_active_ally_before_the_invite_is_accepted(app, db):
    with app.app_context():
        alice = _make_user("alice")
        bob = _make_user("bob")
        topic = _make_topic()
        db.session.commit()

        dungeon_service.send_invite(alice.id, bob.id, topic.id)
        assert dungeon_service.active_ally(alice.id, topic.id) is None
        assert dungeon_service.active_ally(bob.id, topic.id) is None


def test_accepting_makes_both_sides_see_each_other_as_the_active_ally(app, db):
    with app.app_context():
        alice = _make_user("alice")
        bob = _make_user("bob")
        topic = _make_topic()
        db.session.commit()

        invite = dungeon_service.send_invite(alice.id, bob.id, topic.id)
        dungeon_service.respond(invite.id, bob.id, accept=True)

        assert dungeon_service.active_ally(alice.id, topic.id).username == "bob"
        assert dungeon_service.active_ally(bob.id, topic.id).username == "alice"


def test_declining_never_produces_an_active_ally(app, db):
    with app.app_context():
        alice = _make_user("alice")
        bob = _make_user("bob")
        topic = _make_topic()
        db.session.commit()

        invite = dungeon_service.send_invite(alice.id, bob.id, topic.id)
        dungeon_service.respond(invite.id, bob.id, accept=False)

        assert dungeon_service.active_ally(alice.id, topic.id) is None


def test_only_the_invited_user_can_respond(app, db):
    with app.app_context():
        alice = _make_user("alice")
        bob = _make_user("bob")
        topic = _make_topic()
        db.session.commit()

        invite = dungeon_service.send_invite(alice.id, bob.id, topic.id)
        with pytest.raises(dungeon_service.DungeonError):
            dungeon_service.respond(invite.id, alice.id, accept=True)  # sender, not invitee


def test_expired_invite_is_not_an_active_ally(app, db):
    with app.app_context():
        alice = _make_user("alice")
        bob = _make_user("bob")
        topic = _make_topic()
        db.session.commit()

        invite = dungeon_service.send_invite(alice.id, bob.id, topic.id)
        dungeon_service.respond(invite.id, bob.id, accept=True)
        invite.expires_at = datetime.utcnow() - timedelta(minutes=1)
        db.session.commit()

        assert dungeon_service.active_ally(alice.id, topic.id) is None


def test_active_ally_is_scoped_to_the_invited_topic(app, db):
    with app.app_context():
        alice = _make_user("alice")
        bob = _make_user("bob")
        subject = Subject(slug="operacoes-fundamentais", name="Operações Fundamentais", order=0)
        db.session.add(subject)
        db.session.flush()
        topic = _make_topic("adicao", subject=subject)
        other_topic = _make_topic("subtracao", subject=subject)
        db.session.commit()

        invite = dungeon_service.send_invite(alice.id, bob.id, topic.id)
        dungeon_service.respond(invite.id, bob.id, accept=True)

        assert dungeon_service.active_ally(alice.id, topic.id) is not None
        assert dungeon_service.active_ally(alice.id, other_topic.id) is None
