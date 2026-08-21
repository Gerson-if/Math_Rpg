from app.extensions import db
from app.models import User, Subject, Topic, Mastery
from app.services import diagnostics_service, math_areas


def _make_user(email="learner@example.com"):
    user = User(email=email, username=email.split("@")[0])
    user.set_password("senhaforte123")
    db.session.add(user)
    db.session.flush()
    return user


def _make_topic(slug, subject, order):
    topic = Topic(slug=slug, name=slug, subject_id=subject.id, order=order, base_difficulty=1)
    db.session.add(topic)
    db.session.flush()
    return topic


def _set_mastery(user, topic, score, correct_count=1, wrong_count=0):
    db.session.add(Mastery(
        user_id=user.id, topic_id=topic.id, mastery_score=score,
        correct_count=correct_count, wrong_count=wrong_count,
    ))
    db.session.commit()


def test_area_report_treats_an_untouched_topic_as_zero_mastery(app, db):
    with app.app_context():
        user = _make_user()
        subject = Subject(slug="operacoes-fundamentais", name="Operações Fundamentais", order=0)
        db.session.add(subject)
        db.session.flush()
        _make_topic("adicao", subject, 0)  # never attempted
        subtracao = _make_topic("subtracao", subject, 1)
        _set_mastery(user, subtracao, score=1.0)

        report = diagnostics_service.area_report(user.id)
        area = next(r for r in report if r["slug"] == "operacoes-aritmeticas")
        # (0.0 + 1.0) / 2 topics = 50%
        assert area["mastery_pct"] == 50
        assert area["topics_practiced"] == 1
        assert area["topics_total"] == 2
        assert area["weakest_topic"].slug == "adicao"


def test_area_report_sorts_weakest_area_first(app, db):
    with app.app_context():
        user = _make_user()
        strong_subject = Subject(slug="tabuada", name="Tabuada", order=0)
        weak_subject = Subject(slug="fracoes", name="Frações", order=1)
        db.session.add_all([strong_subject, weak_subject])
        db.session.flush()

        strong_topic = _make_topic("tabuada-do-1", strong_subject, 0)
        weak_topic = _make_topic("fracoes-basicas", weak_subject, 0)
        _set_mastery(user, strong_topic, score=0.9)
        _set_mastery(user, weak_topic, score=0.1)

        report = diagnostics_service.area_report(user.id)
        assert report[0]["slug"] == "fracoes"
        assert report[0]["mastery_pct"] == 10
        assert report[-1]["mastery_pct"] >= report[0]["mastery_pct"]


def test_area_report_skips_topics_with_no_mapped_math_area(app, db):
    """A topic slug not present in math_areas.TOPIC_AREAS (e.g. curriculum
    content added ahead of updating that map) is quietly excluded rather
    than crashing the report."""
    with app.app_context():
        user = _make_user()
        subject = Subject(slug="mystery-subject", name="Mystery", order=0)
        db.session.add(subject)
        db.session.flush()
        _make_topic("not-a-mapped-slug", subject, 0)

        report = diagnostics_service.area_report(user.id)
        assert all(row["slug"] != "not-a-mapped-slug" for row in report)


def test_area_report_is_empty_when_no_topics_exist(app, db):
    with app.app_context():
        user = _make_user()
        assert diagnostics_service.area_report(user.id) == []


def test_area_report_flags_a_weak_prerequisite_area(app, db):
    # pensamento-algebrico depends on operacoes-aritmeticas (and
    # porcentagem) — a player weak in the prerequisite should see it
    # called out on the dependent area's row.
    with app.app_context():
        user = _make_user()
        ops_subject = Subject(slug="operacoes-fundamentais", name="Operações Fundamentais", order=0)
        algebra_subject = Subject(slug="algebra", name="Álgebra", order=1)
        db.session.add_all([ops_subject, algebra_subject])
        db.session.flush()
        adicao = _make_topic("adicao", ops_subject, 0)
        equacao = _make_topic("equacoes-1-grau", algebra_subject, 0)
        _set_mastery(user, adicao, score=0.1)  # weak — below the gap threshold
        _set_mastery(user, equacao, score=0.9)  # strong on its own

        report = diagnostics_service.area_report(user.id)
        algebra_row = next(r for r in report if r["slug"] == "pensamento-algebrico")
        gap_slugs = [g["slug"] for g in algebra_row["prereq_gaps"]]
        assert "operacoes-aritmeticas" in gap_slugs


def test_area_report_does_not_flag_a_strong_prerequisite_area(app, db):
    with app.app_context():
        user = _make_user()
        ops_subject = Subject(slug="operacoes-fundamentais", name="Operações Fundamentais", order=0)
        algebra_subject = Subject(slug="algebra", name="Álgebra", order=1)
        db.session.add_all([ops_subject, algebra_subject])
        db.session.flush()
        adicao = _make_topic("adicao", ops_subject, 0)
        equacao = _make_topic("equacoes-1-grau", algebra_subject, 0)
        _set_mastery(user, adicao, score=0.9)  # already solid
        _set_mastery(user, equacao, score=0.9)

        report = diagnostics_service.area_report(user.id)
        algebra_row = next(r for r in report if r["slug"] == "pensamento-algebrico")
        assert algebra_row["prereq_gaps"] == []


def test_radar_chart_svg_plots_every_area_axis():
    rows_by_slug = {"senso-numerico": {"mastery_pct": 80}}
    svg = diagnostics_service.radar_chart_svg(rows_by_slug)
    assert svg.startswith("<svg")
    # One axis label per area in the taxonomy, even the ones missing from
    # rows_by_slug (an area with no data yet still gets plotted at 0%).
    for area in math_areas.AREAS.values():
        assert area["short_name"] in svg


def test_radar_chart_svg_handles_an_empty_report():
    svg = diagnostics_service.radar_chart_svg({})
    assert svg.startswith("<svg")


# --- confidence / "weakest with real data" -------------------------------
#
# An untouched topic reporting 0% mastery (see
# test_area_report_treats_an_untouched_topic_as_zero_mastery above) is
# indistinguishable from a genuinely-struggled-with topic by mastery_pct
# alone — confidence and weakest_with_data are what let a caller tell
# "never explored" apart from "actually weak".

def test_confidence_is_none_for_a_never_attempted_area(app, db):
    with app.app_context():
        user = _make_user()
        subject = Subject(slug="fundamentos", name="Fundamentos", order=0)
        db.session.add(subject)
        db.session.flush()
        _make_topic("numeros-e-contagem", subject, 0)  # never attempted

        report = diagnostics_service.area_report(user.id)
        area = next(r for r in report if r["slug"] == "senso-numerico")
        assert area["confidence"] == "nenhum"
        assert area["attempts_total"] == 0


def test_confidence_is_baixa_with_only_a_couple_of_attempts(app, db):
    with app.app_context():
        user = _make_user()
        subject = Subject(slug="fundamentos", name="Fundamentos", order=0)
        db.session.add(subject)
        db.session.flush()
        topic = _make_topic("numeros-e-contagem", subject, 0)
        _set_mastery(user, topic, score=0.3, correct_count=1, wrong_count=1)

        report = diagnostics_service.area_report(user.id)
        area = next(r for r in report if r["slug"] == "senso-numerico")
        assert area["confidence"] == "baixa"
        assert area["attempts_total"] == 2


def test_confidence_is_alta_with_plenty_of_attempts_across_every_topic(app, db):
    with app.app_context():
        user = _make_user()
        subject = Subject(slug="operacoes-fundamentais", name="Operações Fundamentais", order=0)
        db.session.add(subject)
        db.session.flush()
        adicao = _make_topic("adicao", subject, 0)
        subtracao = _make_topic("subtracao", subject, 1)
        _set_mastery(user, adicao, score=0.9, correct_count=15, wrong_count=5)
        _set_mastery(user, subtracao, score=0.9, correct_count=15, wrong_count=5)

        report = diagnostics_service.area_report(user.id)
        area = next(r for r in report if r["slug"] == "operacoes-aritmeticas")
        assert area["confidence"] == "alta"


def test_weakest_with_data_prefers_a_practiced_area_over_an_untouched_one(app, db):
    with app.app_context():
        user = _make_user()
        subject = Subject(slug="fundamentos", name="Fundamentos", order=0)
        db.session.add(subject)
        db.session.flush()
        # senso-numerico: never touched (0%, but no real data).
        _make_topic("numeros-e-contagem", subject, 0)
        # comparacao: genuinely practiced and still weak (30%, real data).
        comparacao = _make_topic("comparacao-de-quantidades", subject, 1)
        _set_mastery(user, comparacao, score=0.3, correct_count=3, wrong_count=7)

        report = diagnostics_service.area_report(user.id)
        weakest = diagnostics_service.weakest_with_data(report)
        assert weakest["slug"] == "comparacao"


def test_weakest_with_data_falls_back_to_untouched_when_nothing_has_been_practiced(app, db):
    with app.app_context():
        user = _make_user()
        subject = Subject(slug="fundamentos", name="Fundamentos", order=0)
        db.session.add(subject)
        db.session.flush()
        _make_topic("numeros-e-contagem", subject, 0)

        report = diagnostics_service.area_report(user.id)
        weakest = diagnostics_service.weakest_with_data(report)
        assert weakest is not None
        assert weakest["attempts_total"] == 0


def test_weakest_with_data_handles_an_empty_report():
    assert diagnostics_service.weakest_with_data([]) is None
