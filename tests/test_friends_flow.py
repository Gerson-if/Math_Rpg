import re

from flask import g

from app.models import User, Subject, Topic, PlayerStats
from app.services import question_token


def _reset_login_cache():
    """conftest.py's `app` fixture keeps a single app context alive for
    the whole test (so tests can query the DB without an explicit `with
    app.app_context()`), and Flask-Login caches the resolved user on
    `g._login_user` *per app context*, not per request. Real request
    handling never hits this since each HTTP request gets its own fresh
    app context — but here, two test clients "logged in" as different
    users within one test share that one ambient app context, so without
    clearing this cache the second client would see the first client's
    user. Call this right before any request made by a client other than
    the one that made the previous request."""
    g.pop("_login_user", None)


def _create_and_login(client, db, username, email=None):
    user = User(email=email or f"{username}@example.com", username=username)
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    _reset_login_cache()
    client.post("/auth/login", data={"email": user.email, "password": "senhaforte123"})
    return user


def _create_topic(db, slug="adicao"):
    subject = Subject(slug="operacoes-fundamentais", name="Operações Fundamentais", order=0)
    db.session.add(subject)
    db.session.flush()
    topic = Topic(slug=slug, name="Adição", subject_id=subject.id, order=0, base_difficulty=1)
    db.session.add(topic)
    db.session.commit()
    return topic


def _extract_token(html: str) -> str:
    match = re.search(r'name="token" value="([^"]+)"', html)
    assert match, "token field not found in question fragment"
    return match.group(1)


def test_friend_request_accept_and_list_through_the_real_flow(client, db, app):
    alice = _create_and_login(client, db, "alice")
    bob_client = app.test_client()
    bob = _create_and_login(bob_client, db, "bob")

    _reset_login_cache()
    resp = client.post("/amigos/solicitar", data={"username": "bob"}, follow_redirects=True)
    assert resp.status_code == 200
    assert "bob" in resp.data.decode()

    # bob sees the incoming request and accepts it
    _reset_login_cache()
    resp2 = bob_client.get("/amigos/")
    assert "alice" in resp2.data.decode()

    from app.models import Friendship
    friendship = Friendship.query.filter_by(requester_id=alice.id, addressee_id=bob.id).first()
    _reset_login_cache()
    resp3 = bob_client.post(f"/amigos/{friendship.id}/aceitar", follow_redirects=True)
    assert resp3.status_code == 200

    _reset_login_cache()
    resp4 = client.get("/amigos/")
    assert "bob" in resp4.data.decode()


def test_dungeon_invite_accept_redirects_to_the_topic_and_grants_a_coop_bonus(client, db, app):
    alice = _create_and_login(client, db, "alice")
    bob_client = app.test_client()
    bob = _create_and_login(bob_client, db, "bob")
    topic = _create_topic(db)

    from app.services import friends_service, dungeon_service
    friendship = friends_service.send_request(alice.id, "bob")
    friends_service.respond(friendship.id, bob.id, accept=True)

    _reset_login_cache()
    resp = client.post(
        "/amigos/masmorra/convidar",
        data={"friend_id": bob.id, "topic_id": topic.id},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    invite = dungeon_service.list_incoming(bob.id)[0]

    _reset_login_cache()
    resp2 = bob_client.post(f"/amigos/masmorra/{invite.id}/aceitar")
    assert resp2.status_code == 302
    assert f"/math/praticar/{topic.slug}" in resp2.headers["Location"]

    # Both allies are now practicing the same topic inside the invite
    # window — a correct answer from either one should include the bonus.
    _reset_login_cache()
    resp3 = client.get(f"/math/praticar/{topic.slug}/questao")
    token = _extract_token(resp3.data.decode())
    payload = question_token.read_token(token)

    _reset_login_cache()
    resp4 = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": token, "answer": payload["answer"]},
    )
    body = resp4.data.decode()
    assert "Correto" in body
    assert "bônus de dupla" in body

    stats = PlayerStats.query.filter_by(user_id=alice.id).first()
    assert stats.xp == 10 + dungeon_service.COOP_BONUS_XP  # difficulty 1 -> 10 XP + 5 bonus
