import pytest

from app.extensions import db
from app.models import Duel, Notification, Subject, Topic, User
from app.services import duel_service


def _make_user(username):
    user = User(email=f"{username}@example.com", username=username)
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.flush()
    return user


def _make_topic(slug="adicao"):
    subject = Subject(slug="operacoes-fundamentais", name="Operações Fundamentais", order=0)
    db.session.add(subject)
    db.session.flush()
    topic = Topic(slug=slug, name="Adição", subject_id=subject.id, order=0, base_difficulty=1)
    db.session.add(topic)
    db.session.flush()
    return topic


def test_create_challenge_persists_a_pending_duel_and_notifies_the_opponent(app, db):
    with app.app_context():
        challenger = _make_user("challenger")
        opponent = _make_user("opponent")
        topic = _make_topic()
        db.session.commit()

        duel = duel_service.create_challenge(challenger.id, opponent.id, topic.id)

        assert duel.status == Duel.STATUS_PENDING
        assert duel.challenger_hp == duel_service.STARTING_HP
        assert duel.opponent_hp == duel_service.STARTING_HP
        assert duel.room_code

        notif = Notification.query.filter_by(user_id=opponent.id, type="duel_challenge").first()
        assert notif is not None
        assert notif.payload["duel_id"] == duel.id


def test_create_challenge_rejects_challenging_yourself(app, db):
    with app.app_context():
        user = _make_user("solo")
        topic = _make_topic()
        db.session.commit()

        with pytest.raises(duel_service.DuelError):
            duel_service.create_challenge(user.id, user.id, topic.id)


def test_create_challenge_rejects_a_second_pending_challenge_between_the_same_pair(app, db):
    with app.app_context():
        challenger = _make_user("chal_dup")
        opponent = _make_user("opp_dup")
        topic = _make_topic()
        db.session.commit()

        duel_service.create_challenge(challenger.id, opponent.id, topic.id)

        with pytest.raises(duel_service.DuelError):
            duel_service.create_challenge(challenger.id, opponent.id, topic.id)


def test_create_challenge_rejects_the_reverse_direction_too(app, db):
    with app.app_context():
        challenger = _make_user("chal_rev")
        opponent = _make_user("opp_rev")
        topic = _make_topic()
        db.session.commit()

        duel_service.create_challenge(challenger.id, opponent.id, topic.id)

        # Same pair, opponent challenging back before the first request was
        # even answered — should be blocked exactly like a same-direction
        # duplicate would be.
        with pytest.raises(duel_service.DuelError):
            duel_service.create_challenge(opponent.id, challenger.id, topic.id)


def test_create_challenge_allows_a_new_one_once_the_previous_duel_finished(app, db):
    with app.app_context():
        challenger = _make_user("chal_done")
        opponent = _make_user("opp_done")
        topic = _make_topic()
        db.session.commit()

        first = duel_service.create_challenge(challenger.id, opponent.id, topic.id)
        first.status = Duel.STATUS_FINISHED
        db.session.commit()

        second = duel_service.create_challenge(challenger.id, opponent.id, topic.id)
        assert second.id != first.id


def test_respond_to_challenge_accept_starts_the_first_round(app, db):
    with app.app_context():
        challenger = _make_user("challenger2")
        opponent = _make_user("opponent2")
        topic = _make_topic()
        db.session.commit()
        duel = duel_service.create_challenge(challenger.id, opponent.id, topic.id)

        started = duel_service.respond_to_challenge(duel.id, opponent.id, accept=True)

        assert started.status == Duel.STATUS_ACTIVE
        assert started.current_prompt
        assert started.current_answer
        assert started.round_number == 1


def test_respond_to_challenge_decline_marks_it_declined(app, db):
    with app.app_context():
        challenger = _make_user("challenger3")
        opponent = _make_user("opponent3")
        topic = _make_topic()
        db.session.commit()
        duel = duel_service.create_challenge(challenger.id, opponent.id, topic.id)

        declined = duel_service.respond_to_challenge(duel.id, opponent.id, accept=False)

        assert declined.status == Duel.STATUS_DECLINED


def test_only_the_challenged_opponent_can_respond(app, db):
    with app.app_context():
        challenger = _make_user("challenger4")
        opponent = _make_user("opponent4")
        stranger = _make_user("stranger4")
        topic = _make_topic()
        db.session.commit()
        duel = duel_service.create_challenge(challenger.id, opponent.id, topic.id)

        with pytest.raises(duel_service.DuelError):
            duel_service.respond_to_challenge(duel.id, stranger.id, accept=True)


def test_submit_answer_rejects_a_wrong_answer_without_changing_hp(app, db):
    with app.app_context():
        challenger = _make_user("challenger5")
        opponent = _make_user("opponent5")
        topic = _make_topic()
        db.session.commit()
        duel = duel_service.create_challenge(challenger.id, opponent.id, topic.id)
        duel_service.respond_to_challenge(duel.id, opponent.id, accept=True)

        result = duel_service.submit_answer(duel.id, challenger.id, "definitely-not-the-answer-123456")

        assert result["is_correct"] is False
        refreshed = Duel.query.get(duel.id)
        assert refreshed.challenger_hp == duel_service.STARTING_HP
        assert refreshed.opponent_hp == duel_service.STARTING_HP


def test_submit_answer_damages_the_other_player_on_a_correct_answer(app, db):
    with app.app_context():
        challenger = _make_user("challenger6")
        opponent = _make_user("opponent6")
        topic = _make_topic()
        db.session.commit()
        duel = duel_service.create_challenge(challenger.id, opponent.id, topic.id)
        duel_service.respond_to_challenge(duel.id, opponent.id, accept=True)
        correct_answer = duel.current_answer

        result = duel_service.submit_answer(duel.id, challenger.id, correct_answer)

        assert result["is_correct"] is True
        assert result["opponent_hp"] == duel_service.STARTING_HP - duel_service.DAMAGE_PER_ROUND
        assert result["challenger_hp"] == duel_service.STARTING_HP
        assert result["finished"] is False
        # A new round starts automatically -> a fresh question is ready.
        assert result["next_prompt"]


def test_submit_answer_rejects_a_non_participant(app, db):
    with app.app_context():
        challenger = _make_user("challenger7")
        opponent = _make_user("opponent7")
        stranger = _make_user("stranger7")
        topic = _make_topic()
        db.session.commit()
        duel = duel_service.create_challenge(challenger.id, opponent.id, topic.id)
        duel_service.respond_to_challenge(duel.id, opponent.id, accept=True)

        with pytest.raises(duel_service.DuelError):
            duel_service.submit_answer(duel.id, stranger.id, duel.current_answer)


def test_duel_ends_when_a_players_hp_reaches_zero_and_notifies_both(app, db):
    with app.app_context():
        challenger = _make_user("challenger8")
        opponent = _make_user("opponent8")
        topic = _make_topic()
        db.session.commit()
        duel = duel_service.create_challenge(challenger.id, opponent.id, topic.id)
        duel_service.respond_to_challenge(duel.id, opponent.id, accept=True)

        rounds_to_win = duel_service.STARTING_HP // duel_service.DAMAGE_PER_ROUND
        result = None
        for _ in range(rounds_to_win):
            duel = Duel.query.get(duel.id)
            result = duel_service.submit_answer(duel.id, challenger.id, duel.current_answer)

        assert result["finished"] is True
        assert result["winner_id"] == challenger.id

        finished = Duel.query.get(duel.id)
        assert finished.status == Duel.STATUS_FINISHED
        assert finished.opponent_hp == 0

        challenger_notif = Notification.query.filter_by(user_id=challenger.id, type="duel_result").first()
        opponent_notif = Notification.query.filter_by(user_id=opponent.id, type="duel_result").first()
        assert challenger_notif.payload["won"] is True
        assert opponent_notif.payload["won"] is False


def test_forfeit_ends_the_duel_in_favor_of_the_other_player(app, db):
    with app.app_context():
        challenger = _make_user("challenger9")
        opponent = _make_user("opponent9")
        topic = _make_topic()
        db.session.commit()
        duel = duel_service.create_challenge(challenger.id, opponent.id, topic.id)
        duel_service.respond_to_challenge(duel.id, opponent.id, accept=True)

        finished = duel_service.forfeit(duel.id, challenger.id)

        assert finished.status == Duel.STATUS_FINISHED
        assert finished.winner_id == opponent.id
        assert finished.challenger_hp == 0


def test_list_pending_challenges_only_returns_this_users_incoming_ones(app, db):
    with app.app_context():
        challenger = _make_user("challenger10")
        opponent = _make_user("opponent10")
        other = _make_user("other10")
        topic = _make_topic()
        db.session.commit()
        duel_service.create_challenge(challenger.id, opponent.id, topic.id)

        assert len(duel_service.list_pending_challenges(opponent.id)) == 1
        assert len(duel_service.list_pending_challenges(other.id)) == 0
        assert len(duel_service.list_pending_challenges(challenger.id)) == 0
