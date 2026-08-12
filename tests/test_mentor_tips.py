from app.services import mentor_tips


def test_random_tip_has_a_valid_kind_and_nonempty_text():
    for _ in range(50):
        tip = mentor_tips.random_tip()
        assert tip["kind"] in ("curiosidade", "regra")
        assert tip["text"].strip()


def test_tip_pool_has_both_kinds_represented():
    kinds = {tip["kind"] for tip in mentor_tips.TIPS}
    assert kinds == {"curiosidade", "regra"}


def test_practice_page_shows_a_mentor_tip(client, db):
    from app.models import User, Subject, Topic

    user = User(email="mentor@example.com", username="mentor")
    user.set_password("senhaforte123")
    db.session.add(user)
    subject = Subject(slug="fundamentos", name="Fundamentos", order=0)
    db.session.add(subject)
    db.session.flush()
    topic = Topic(slug="numeros-e-contagem", name="Números e contagem", subject_id=subject.id, order=0)
    db.session.add(topic)
    db.session.commit()

    client.post("/auth/login", data={"email": "mentor@example.com", "password": "senhaforte123"})
    resp = client.get(f"/math/praticar/{topic.slug}")
    assert resp.status_code == 200
    assert "mentor-tip" in resp.data.decode()
