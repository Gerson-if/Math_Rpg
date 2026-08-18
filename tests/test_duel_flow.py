from flask_login import login_user

from app.duels import socket_events
from app.extensions import db, socketio
from app.models import Duel, Subject, Topic, User
from app.services import duel_service, friends_service


def _create_and_login(client, db, username):
    user = User(email=f"{username}@example.com", username=username)
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    client.post("/auth/login", data={"email": f"{username}@example.com", "password": "senhaforte123"})
    return user


def _login_as(test_client, user_id):
    """Logs a *second* test client in as a specific user (by plain id, not
    an ORM instance — avoids DetachedInstanceError after the commit that
    created it expires the object) by writing the Flask-Login session key
    directly instead of POSTing to /auth/login.

    Needed here because the pytest `app` fixture keeps one outer
    app_context open for the whole test — Flask reuses that already-active
    context (and its `g`, where Flask-Login caches current_user) for
    same-app test-client requests instead of pushing a fresh one, so a
    *second* POST-based login within the same test would see `current_user`
    still cached as whoever logged in first and get bounced by the
    login view's "already authenticated" redirect before ever
    authenticating as the new user. session_transaction() writes the
    session cookie directly and sidesteps the view entirely, so it isn't
    affected by that caching. Not a real app bug — outside tests, each
    request gets its own natural context."""
    with test_client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _make_friends(db, a, b):
    friendship = friends_service.send_request(a.id, b.username)
    friends_service.respond(friendship.id, b.id, accept=True)


def _make_topic(db):
    subject = Subject(slug="operacoes-fundamentais", name="Operações Fundamentais", order=0)
    db.session.add(subject)
    db.session.flush()
    topic = Topic(slug="adicao", name="Adição", subject_id=subject.id, order=0, base_difficulty=1)
    db.session.add(topic)
    db.session.commit()
    return topic


def test_challenge_route_requires_actual_friendship(client, db, app):
    challenger = _create_and_login(client, db, "chalflow1")
    with app.app_context():
        opponent = User(email="oppflow1@example.com", username="oppflow1")
        opponent.set_password("senhaforte123")
        db.session.add(opponent)
        topic = _make_topic(db)
        db.session.commit()
        opponent_id, topic_id = opponent.id, topic.id

    resp = client.post("/duelo/desafiar", data={"friend_id": opponent_id, "topic_id": topic_id}, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert Duel.query.count() == 0


def test_challenge_route_creates_a_pending_duel_between_friends(client, db, app):
    challenger = _create_and_login(client, db, "chalflow2")
    with app.app_context():
        opponent = User(email="oppflow2@example.com", username="oppflow2")
        opponent.set_password("senhaforte123")
        db.session.add(opponent)
        db.session.flush()
        _make_friends(db, challenger, opponent)
        topic = _make_topic(db)
        opponent_id, topic_id = opponent.id, topic.id

    resp = client.post("/duelo/desafiar", data={"friend_id": opponent_id, "topic_id": topic_id}, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert Duel.query.count() == 1


def test_arena_route_404s_for_a_non_participant(client, db, app):
    with app.app_context():
        challenger = User(email="chalflow3@example.com", username="chalflow3")
        challenger.set_password("senhaforte123")
        opponent = User(email="oppflow3@example.com", username="oppflow3")
        opponent.set_password("senhaforte123")
        db.session.add_all([challenger, opponent])
        db.session.flush()
        topic = _make_topic(db)
        duel = duel_service.create_challenge(challenger.id, opponent.id, topic.id)
        duel_service.respond_to_challenge(duel.id, opponent.id, accept=True)
        duel_id = duel.id

    _create_and_login(client, db, "strangerflow3")
    resp = client.get(f"/duelo/{duel_id}")
    assert resp.status_code == 404


def test_arena_route_redirects_when_challenge_still_pending(client, db, app):
    challenger = _create_and_login(client, db, "chalflow4")
    with app.app_context():
        opponent = User(email="oppflow4@example.com", username="oppflow4")
        opponent.set_password("senhaforte123")
        db.session.add(opponent)
        db.session.flush()
        topic = _make_topic(db)
        duel = duel_service.create_challenge(challenger.id, opponent.id, topic.id)
        duel_id = duel.id

    resp = client.get(f"/duelo/{duel_id}", follow_redirects=True)
    assert resp.status_code == 200
    assert "/amigos" in resp.request.path


def test_socketio_join_and_answer_flow_between_two_real_clients(client, db, app):
    """End-to-end over the real Socket.IO handlers: both players join the
    duel room and the challenger answers correctly — the round result
    must reach both connected clients, and HP must reflect real damage,
    exactly like a real duel would play out."""
    challenger = _create_and_login(client, db, "chalflow5")
    with app.app_context():
        opponent = User(email="oppflow5@example.com", username="oppflow5")
        opponent.set_password("senhaforte123")
        db.session.add(opponent)
        db.session.flush()
        topic = _make_topic(db)
        duel = duel_service.create_challenge(challenger.id, opponent.id, topic.id)
        duel_service.respond_to_challenge(duel.id, opponent.id, accept=True)
        duel_id = duel.id
        correct_answer = duel.current_answer
        opponent_id = opponent.id

    challenger_client = client
    opponent_client = app.test_client()
    _login_as(opponent_client, opponent_id)

    challenger_sio = socketio.test_client(app, flask_test_client=challenger_client)
    opponent_sio = socketio.test_client(app, flask_test_client=opponent_client)

    join_resp = challenger_sio.emit("join_duel", {"duel_id": duel_id}, callback=True)
    assert join_resp["you_are"] == "challenger"
    assert join_resp["challenger_hp"] == duel_service.STARTING_HP

    opponent_sio.emit("join_duel", {"duel_id": duel_id}, callback=True)
    # Drain the join-time noop broadcasts, if any, from both queues.
    challenger_sio.get_received()
    opponent_sio.get_received()

    ack = challenger_sio.emit("submit_answer", {"duel_id": duel_id, "answer": correct_answer}, callback=True)
    assert ack == {"ok": True}

    challenger_events = challenger_sio.get_received()
    opponent_events = opponent_sio.get_received()
    assert any(e["name"] == "round_result" for e in challenger_events)
    assert any(e["name"] == "round_result" for e in opponent_events)

    result = next(e["args"][0] for e in opponent_events if e["name"] == "round_result")
    assert result["is_correct"] is True
    assert result["answered_by"] == challenger.id
    assert result["opponent_hp"] == duel_service.STARTING_HP - duel_service.DAMAGE_PER_ROUND

    challenger_sio.disconnect()
    opponent_sio.disconnect()


def test_join_duel_handler_rejects_a_stranger(app, db):
    """Calls the real socket_events.handle_join function directly under an
    explicit login_user(), rather than through the fake Socket.IO
    transport — a second, genuinely distinct logged-in identity within
    one test is exactly the scenario where Flask's test-client g/app-
    context reuse (see _login_as's docstring above) makes the full
    transport unreliable to assert on. The handler itself doesn't know
    or care whether it's called from a real socket event or directly."""
    with app.app_context():
        challenger = User(email="chalflow6@example.com", username="chalflow6")
        challenger.set_password("senhaforte123")
        opponent = User(email="oppflow6@example.com", username="oppflow6")
        opponent.set_password("senhaforte123")
        stranger = User(email="strangerflow6@example.com", username="strangerflow6")
        stranger.set_password("senhaforte123")
        db.session.add_all([challenger, opponent, stranger])
        db.session.flush()
        topic = _make_topic(db)
        duel = duel_service.create_challenge(challenger.id, opponent.id, topic.id)
        duel_service.respond_to_challenge(duel.id, opponent.id, accept=True)
        duel_id = duel.id
        stranger_id = stranger.id

    with app.test_request_context():
        login_user(User.query.get(stranger_id))
        result = socket_events.handle_join({"duel_id": duel_id})

    assert result is not None and result.get("error")


def test_send_emote_handler_is_restricted_to_an_allowed_set(app, db, monkeypatch):
    with app.app_context():
        challenger = User(email="chalflow7@example.com", username="chalflow7")
        challenger.set_password("senhaforte123")
        opponent = User(email="oppflow7@example.com", username="oppflow7")
        opponent.set_password("senhaforte123")
        db.session.add_all([challenger, opponent])
        db.session.flush()
        topic = _make_topic(db)
        duel = duel_service.create_challenge(challenger.id, opponent.id, topic.id)
        duel_service.respond_to_challenge(duel.id, opponent.id, accept=True)
        duel_id = duel.id
        challenger_id = challenger.id

    emitted = []
    monkeypatch.setattr(socket_events, "emit", lambda *a, **k: emitted.append((a, k)))

    with app.test_request_context():
        login_user(User.query.get(challenger_id))
        socket_events.handle_emote({"duel_id": duel_id, "emote": "<script>alert(1)</script>"})
        assert emitted == []

        socket_events.handle_emote({"duel_id": duel_id, "emote": "fire"})
        assert len(emitted) == 1
        args, kwargs = emitted[0]
        assert args[0] == "emote_received"
        assert args[1]["emote"] == "fire"
