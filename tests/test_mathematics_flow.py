import re

import pytest

from app.models import User, Subject, Topic, Attempt, Mastery
from app.services import question_token


def _create_and_login(client, db, email="aluno@example.com"):
    user = User(email=email, username="aluno")
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.commit()
    client.post("/auth/login", data={"email": email, "password": "senhaforte123"})
    return user


def _create_topic(db, slug="tabuada-do-7"):
    subject = Subject(slug="tabuada", name="Tabuada", order=0)
    db.session.add(subject)
    db.session.flush()
    topic = Topic(slug=slug, name="Tabuada do 7", subject_id=subject.id, order=0, base_difficulty=1)
    db.session.add(topic)
    db.session.commit()
    return topic


def _extract_token(html: str) -> str:
    match = re.search(r'name="token" value="([^"]+)"', html)
    assert match, "token field not found in question fragment"
    return match.group(1)


def test_practice_screen_shows_the_generic_ultimate_name_with_no_class_chosen(client, db):
    _create_and_login(client, db)
    topic = _create_topic(db)

    resp = client.get(f"/math/praticar/{topic.slug}")
    assert "Fúria Arcana Suprema" in resp.data.decode()


def test_practice_screen_shows_the_players_own_class_ability_as_the_ultimate(client, db, app):
    from app.models import Profile

    user = _create_and_login(client, db)
    topic = _create_topic(db)
    db.session.add(Profile(
        user_id=user.id, display_name="aluno",
        character_class="mago", class_tier_claimed=0,
    ))
    db.session.commit()

    resp = client.get(f"/math/praticar/{topic.slug}")
    body = resp.data.decode()
    assert "Centelha Arcana" in body  # mago's tier-0 ability (see classes_service.CLASS_ABILITIES)
    assert "Fúria Arcana Suprema" not in body


def test_new_question_requires_login(client, db):
    topic = _create_topic(db)
    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    assert resp.status_code in (301, 302)  # bounced to login


def test_correct_answer_is_recorded(client, db, app):
    user = _create_and_login(client, db)
    topic = _create_topic(db)

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    assert resp.status_code == 200
    token = _extract_token(resp.data.decode())

    with app.app_context():
        payload = question_token.read_token(token)
    correct_answer = payload["answer"]

    resp2 = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": token, "answer": correct_answer},
    )
    assert resp2.status_code == 200
    assert 'data-correct="true"' in resp2.data.decode()
    assert 'data-xp=' in resp2.data.decode()

    attempt = Attempt.query.filter_by(user_id=user.id, topic_id=topic.id).first()
    assert attempt is not None
    assert attempt.is_correct is True
    assert attempt.response_time_ms >= 0


def test_wrong_answer_is_recorded_as_incorrect(client, db, app):
    user = _create_and_login(client, db)
    topic = _create_topic(db)

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    token = _extract_token(resp.data.decode())

    resp2 = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": token, "answer": "definitely-not-a-number"},
    )
    assert resp2.status_code == 200

    attempt = Attempt.query.filter_by(user_id=user.id, topic_id=topic.id).first()
    assert attempt is not None
    assert attempt.is_correct is False


def test_tampered_token_is_rejected(client, db):
    _create_and_login(client, db)
    topic = _create_topic(db)

    resp = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": "not-a-real-token", "answer": "42"},
    )
    assert resp.status_code == 400


# --- Fase 7: new topic families, exercised through the real HTTP cycle ----

def test_fraction_answer_is_accepted_through_the_real_flow(client, db, app):
    user = _create_and_login(client, db)
    topic = _create_topic(db, slug="fracoes-basicas")

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    assert resp.status_code == 200
    token = _extract_token(resp.data.decode())

    with app.app_context():
        payload = question_token.read_token(token)
    correct_answer = payload["answer"]  # e.g. "3/4" or a whole number like "2"

    resp2 = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": token, "answer": correct_answer},
    )
    assert 'data-correct="true"' in resp2.data.decode()

    attempt = Attempt.query.filter_by(user_id=user.id, topic_id=topic.id).first()
    assert attempt.is_correct is True


def test_decimal_answer_with_pt_br_comma_is_accepted(client, db, app):
    """Brazilian users naturally type '0,3', not '0.3' — the answer
    comparison must treat the comma as a decimal separator."""
    _create_and_login(client, db)
    topic = _create_topic(db, slug="leitura-de-decimais")

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    token = _extract_token(resp.data.decode())

    with app.app_context():
        payload = question_token.read_token(token)
    comma_answer = payload["answer"].replace(".", ",")

    resp2 = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": token, "answer": comma_answer},
    )
    assert 'data-correct="true"' in resp2.data.decode()


def test_decimal_operation_whole_result_matches_plain_integer_input(client, db, app):
    """A decimal subtraction that lands on a whole number (e.g. '3.0')
    must still accept a plain '3' from the user."""
    _create_and_login(client, db)
    topic = _create_topic(db, slug="operacoes-com-decimais")

    for _ in range(30):  # only some draws land on a whole-number result
        resp = client.get(f"/math/praticar/{topic.slug}/questao")
        token = _extract_token(resp.data.decode())
        with app.app_context():
            payload = question_token.read_token(token)
        answer = payload["answer"]
        if float(answer).is_integer():
            resp2 = client.post(
                f"/math/praticar/{topic.slug}/responder",
                data={"token": token, "answer": str(int(float(answer)))},
            )
            assert 'data-correct="true"' in resp2.data.decode()
            return
    raise AssertionError("did not draw a whole-number decimal result in 30 tries")


def test_dynamic_difficulty_rises_after_a_streak_of_correct_answers(client, db, app):
    """Pendência: difficulty was static per topic; it now adapts to
    mastery/streak. A long streak of correct answers on a base-difficulty-1
    topic should eventually serve a harder question, end to end through
    the real HTTP flow (not just the service function in isolation)."""
    _create_and_login(client, db)
    topic = _create_topic(db, slug="adicao")
    assert topic.base_difficulty == 1

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    token = _extract_token(resp.data.decode())

    difficulties = []
    for _ in range(8):
        with app.app_context():
            payload = question_token.read_token(token)
        difficulties.append(payload["difficulty"])
        resp = client.post(
            f"/math/praticar/{topic.slug}/responder",
            data={"token": token, "answer": payload["answer"]},
        )
        token = _extract_token(resp.data.decode())

    assert max(difficulties) > topic.base_difficulty


def test_tabuada_mista_topic_is_reachable_through_the_real_flow(client, db, app):
    """The mixed-review tabuada topic (all ten tables, random base per
    question) added alongside tabuada-do-1..10 — same real-HTTP round trip
    as the other topic regression tests above."""
    _create_and_login(client, db)
    topic = _create_topic(db, slug="tabuada-mista")

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    assert resp.status_code == 200
    token = _extract_token(resp.data.decode())

    with app.app_context():
        payload = question_token.read_token(token)

    resp2 = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": token, "answer": payload["answer"]},
    )
    assert resp2.status_code == 200
    assert 'data-correct="true"' in resp2.data.decode()


# --- Battle arena combat feel: crit roll + boss-kill loot claim --------

def test_answer_fragment_always_carries_a_data_crit_attribute(client, db, app):
    _create_and_login(client, db)
    topic = _create_topic(db, slug="adicao")

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    token = _extract_token(resp.data.decode())
    with app.app_context():
        payload = question_token.read_token(token)

    resp2 = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": token, "answer": payload["answer"]},
    )
    assert 'data-crit="true"' in resp2.data.decode() or 'data-crit="false"' in resp2.data.decode()


def test_answer_fragment_carries_next_topic_and_mastery_progress_when_a_next_topic_exists(client, db, app):
    from app.models import Subject

    _create_and_login(client, db)
    subject = Subject(slug="tabuada-flow", name="Tabuada", order=0)
    db.session.add(subject)
    db.session.flush()
    # Topic slugs must match TABUADA_RE ("tabuada-do-N") for
    # generate_question to recognize them — the *subject* slug is what's
    # namespaced per-test, not these.
    first = Topic(slug="tabuada-do-1", name="Tabuada do 1", subject_id=subject.id, order=0, base_difficulty=1)
    second = Topic(slug="tabuada-do-2", name="Tabuada do 2", subject_id=subject.id, order=1, base_difficulty=1)
    db.session.add_all([first, second])
    db.session.commit()

    resp = client.get(f"/math/praticar/{first.slug}/questao")
    token = _extract_token(resp.data.decode())
    with app.app_context():
        payload = question_token.read_token(token)

    resp2 = client.post(
        f"/math/praticar/{first.slug}/responder",
        data={"token": token, "answer": payload["answer"]},
    )
    body = resp2.data.decode()
    assert 'data-next-topic-slug="tabuada-do-2"' in body
    assert 'data-next-topic-name="Tabuada do 2"' in body
    assert 'data-mastery-threshold="0.5"' in body
    assert 'data-mastery-score="' in body


def test_answer_fragment_has_no_next_topic_for_the_last_topic_in_a_subject(client, db, app):
    _create_and_login(client, db)
    topic = _create_topic(db, slug="tabuada-do-10")

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    token = _extract_token(resp.data.decode())
    with app.app_context():
        payload = question_token.read_token(token)

    resp2 = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": token, "answer": payload["answer"]},
    )
    assert 'data-next-topic-slug=""' in resp2.data.decode()


def test_answer_fragment_continues_into_the_next_subject_after_defeating_a_boss(client, db, app):
    # Beating a subject's last topic (its boss) used to leave the player
    # stranded there — no way forward except rematching the same boss.
    # See progression_service.next_topic_for.
    from app.models import Subject

    _create_and_login(client, db)
    subject_a = Subject(slug="subj-a-flow", name="Subject A", order=0)
    subject_b = Subject(slug="subj-b-flow", name="Subject B", order=1)
    db.session.add_all([subject_a, subject_b])
    db.session.flush()
    boss = Topic(slug="tabuada-do-9", name="Chefe A", subject_id=subject_a.id, order=0, base_difficulty=1)
    next_first = Topic(slug="tabuada-do-8", name="Primeiro B", subject_id=subject_b.id, order=0, base_difficulty=1)
    db.session.add_all([boss, next_first])
    db.session.commit()

    resp = client.get(f"/math/praticar/{boss.slug}/questao")
    token = _extract_token(resp.data.decode())
    with app.app_context():
        payload = question_token.read_token(token)

    resp2 = client.post(
        f"/math/praticar/{boss.slug}/responder",
        data={"token": token, "answer": payload["answer"]},
    )
    body = resp2.data.decode()
    assert 'data-next-topic-slug="tabuada-do-8"' in body
    assert 'data-next-topic-name="Primeiro B"' in body


def test_practice_summary_requires_login(client, db):
    topic = _create_topic(db)
    resp = client.get(f"/math/praticar/{topic.slug}/resumo")
    assert resp.status_code in (302, 401)


def test_practice_summary_includes_next_topic_urls_for_chaining(client, db):
    from app.models import Subject

    _create_and_login(client, db)
    subject = Subject(slug="tabuada-summary", name="Tabuada", order=0)
    db.session.add(subject)
    db.session.flush()
    first = Topic(slug="tabuada-do-1", name="Tabuada do 1", subject_id=subject.id, order=0, base_difficulty=1)
    second = Topic(slug="tabuada-do-2", name="Tabuada do 2", subject_id=subject.id, order=1, base_difficulty=1)
    db.session.add_all([first, second])
    db.session.commit()

    resp = client.get(f"/math/praticar/{first.slug}/resumo")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["topicSlug"] == "tabuada-do-1"
    assert data["topicName"] == "Tabuada do 1"
    assert data["guardian"]["name"]
    assert data["nextTopic"]["slug"] == "tabuada-do-2"
    assert data["nextTopic"]["url"].endswith("/math/praticar/tabuada-do-2")
    assert data["nextTopic"]["resumoUrl"].endswith("/math/praticar/tabuada-do-2/resumo")
    assert data["victoryUrl"].endswith(f"/math/praticar/{first.slug}/vitoria")
    assert data["newQuestionUrl"].endswith(f"/math/praticar/{first.slug}/questao")


def test_practice_summary_has_no_next_topic_for_the_last_topic_in_a_subject(client, db):
    _create_and_login(client, db)
    topic = _create_topic(db, slug="tabuada-do-10")

    resp = client.get(f"/math/praticar/{topic.slug}/resumo")
    data = resp.get_json()
    assert data["nextTopic"] is None


def test_a_single_correct_answer_never_carries_a_spurious_needs_review_flag(client, db, app):
    """Regression: needs_review used to mirror the *persisted* Mastery flag,
    which only ever flips after 5 attempts — a fresh topic's very first,
    correct answer must never claim mastery just dropped."""
    _create_and_login(client, db)
    topic = _create_topic(db, slug="adicao")

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    token = _extract_token(resp.data.decode())
    with app.app_context():
        payload = question_token.read_token(token)

    resp2 = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": token, "answer": payload["answer"]},
    )
    assert 'data-needs-review="false"' in resp2.data.decode()


def test_claim_victory_grants_an_item_after_a_recent_correct_answer(client, db, app):
    _create_and_login(client, db)
    topic = _create_topic(db, slug="adicao")

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    token = _extract_token(resp.data.decode())
    with app.app_context():
        payload = question_token.read_token(token)
    client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": token, "answer": payload["answer"]},
    )

    resp2 = client.post(f"/math/praticar/{topic.slug}/vitoria")
    assert resp2.status_code == 200
    body = resp2.get_json()
    assert body["rarity"] in {"comum", "magico", "raro", "lendario"}

    from app.models import ItemInstance
    with app.app_context():
        assert ItemInstance.query.count() >= 1


def test_claim_victory_without_a_recent_correct_answer_is_rejected(client, db, app):
    _create_and_login(client, db)
    topic = _create_topic(db, slug="adicao")

    resp = client.post(f"/math/praticar/{topic.slug}/vitoria")
    assert resp.status_code == 400


@pytest.mark.parametrize("slug", ["numeros-e-contagem", "comparacao-de-quantidades"])
def test_fundamentos_topic_is_reachable_through_the_real_flow(client, db, app, slug):
    """Regression: these two topics are seeded in the curriculum
    (scripts/seed.py) but had no generator registered in
    mathematics_service — every question load 404'd because
    new_question() catches the resulting ValueError and aborts."""
    _create_and_login(client, db)
    topic = _create_topic(db, slug=slug)

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    assert resp.status_code == 200
    token = _extract_token(resp.data.decode())

    with app.app_context():
        payload = question_token.read_token(token)

    resp2 = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": token, "answer": payload["answer"]},
    )
    assert resp2.status_code == 200
    assert 'data-correct="true"' in resp2.data.decode()


def test_map_boss_landmark_is_locked_until_its_prerequisite_topic_is_mastered(client, db, app):
    """The adventure map's guardian landmark used to just scroll down to
    the subject section and do nothing else -- now it's a real "fight the
    boss" shortcut, but only once the topic that leads to it is mastered
    (same prerequisite chain used everywhere else, see
    progression_service.unmet_prerequisites)."""
    user = _create_and_login(client, db, email="mapboss@example.com")
    with app.app_context():
        subject = Subject(slug="operacoes-fundamentais", name="Operacoes Fundamentais", order=0)
        db.session.add(subject)
        db.session.flush()
        minion = Topic(slug="soma-mapboss", name="Soma", subject_id=subject.id, order=0, base_difficulty=1)
        boss = Topic(
            slug="chefe-mapboss", name="Chefe Final", subject_id=subject.id, order=1,
            base_difficulty=1, prerequisite_slugs=["soma-mapboss"],
        )
        db.session.add_all([minion, boss])
        db.session.commit()
        minion_id = minion.id

    # The boss topic's own dot in the per-subject listing is always a link
    # (advisory-only, unaffected by this gate) -- what's being asserted
    # here is the *landmark* badge/status specific to the map shortcut.
    resp = client.get("/math/")
    body = resp.data.decode()
    assert "boss-action-badge ready" not in body
    assert "complete a trilha" in body

    with app.app_context():
        db.session.add(Mastery(user_id=user.id, topic_id=minion_id, mastery_score=0.9, correct_count=10))
        db.session.commit()

    resp2 = client.get("/math/")
    body2 = resp2.data.decode()
    assert "boss-action-badge ready" in body2
    assert "Chefe liberado" in body2


# --- concept/vocabulary questions ---------------------------------------

def test_no_concept_question_before_the_minimum_number_of_attempts(client, db):
    _create_and_login(client, db)
    topic = _create_topic(db)

    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    assert 'data-concept="false"' in resp.data.decode()


def test_concept_question_can_appear_once_mastery_is_still_building(client, db, app, monkeypatch):
    from app.mathematics import routes as mathematics_routes

    user = _create_and_login(client, db)
    topic = _create_topic(db)
    with app.app_context():
        db.session.add(Mastery(
            user_id=user.id, topic_id=topic.id,
            mastery_score=0.3, correct_count=4, wrong_count=1,
        ))
        db.session.commit()

    monkeypatch.setattr(mathematics_routes.random, "random", lambda: 0.0)  # always below any chance threshold
    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    body = resp.data.decode()
    assert 'data-concept="true"' in body
    assert 'inputmode="text"' in body


def test_concept_question_is_rare_once_mastery_is_already_solid(client, db, app, monkeypatch):
    from app.mathematics import routes as mathematics_routes

    user = _create_and_login(client, db)
    topic = _create_topic(db)
    with app.app_context():
        db.session.add(Mastery(
            user_id=user.id, topic_id=topic.id,
            mastery_score=0.9, correct_count=10, wrong_count=0,
        ))
        db.session.commit()

    # 0.1 clears the "still building" chance (0.25) but not the "already
    # solid" chance (0.05) -- confirms the ramp-down actually applies once
    # mastery crosses the threshold, not just that *a* chance exists.
    monkeypatch.setattr(mathematics_routes.random, "random", lambda: 0.1)
    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    assert 'data-concept="false"' in resp.data.decode()


def test_answering_a_concept_question_accepts_the_answer_without_accents(client, db, app, monkeypatch):
    from app.mathematics import routes as mathematics_routes

    user = _create_and_login(client, db)
    subject = Subject(slug="fracoes", name="Frações", order=0)
    db.session.add(subject)
    db.session.flush()
    topic = Topic(slug="fracoes-basicas", name="Frações básicas", subject_id=subject.id, order=0, base_difficulty=1)
    db.session.add(topic)
    db.session.flush()
    db.session.add(Mastery(
        user_id=user.id, topic_id=topic.id,
        mastery_score=0.3, correct_count=4, wrong_count=1,
    ))
    db.session.commit()

    monkeypatch.setattr(mathematics_routes.random, "random", lambda: 0.0)
    resp = client.get(f"/math/praticar/{topic.slug}/questao")
    body = resp.data.decode()
    assert 'data-concept="true"' in body
    token = _extract_token(body)
    with app.app_context():
        payload = question_token.read_token(token)
    real_answer = payload["answer"]

    # Strip accents and mangle the case the way a player typing fast on a
    # phone might -- normalize_answer's accent-folding should still match.
    import unicodedata
    deaccented = "".join(c for c in unicodedata.normalize("NFKD", real_answer) if not unicodedata.combining(c))

    resp2 = client.post(
        f"/math/praticar/{topic.slug}/responder",
        data={"token": token, "answer": deaccented.upper()},
    )
    assert 'data-correct="true"' in resp2.data.decode()
