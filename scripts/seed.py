"""
Seeds the catalog tables (subjects/topics, levels, ranks, a couple of
achievements). Safe to run more than once — it upserts by slug/code.

Usage:
    python scripts/seed.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from app.extensions import db
from app.models import Subject, Topic, Level, Rank, Achievement

# Order matches section 1 of the spec. This is a starting point, not a
# fixed structure — subjects/topics can be reorganized freely later.
# icon_key points at static/images/icons/subjects/<slug>.png (Fase 5 art pack).
CURRICULUM = [
    ("fundamentos", "Fundamentos", ["numeros-e-contagem", "comparacao-de-quantidades"],
     "images/icons/subjects/fundamentos.png"),
    ("tabuada", "Tabuada", [f"tabuada-do-{n}" for n in range(1, 11)],
     "images/icons/subjects/tabuada.png"),
    ("operacoes-fundamentais", "Operações Fundamentais",
     ["adicao", "subtracao", "multiplicacao", "divisao"],
     "images/icons/subjects/operacoes-fundamentais.png"),
    ("potenciacao", "Potenciação", ["potencias-basicas", "propriedades-da-potenciacao"],
     "images/icons/subjects/potenciacao.png"),
    ("radiciacao", "Radiciação", ["raiz-quadrada", "raiz-cubica"],
     "images/icons/subjects/radiciacao.png"),
    ("fracoes", "Frações", ["fracoes-basicas", "operacoes-com-fracoes"],
     "images/icons/subjects/fracoes.png"),
    ("numeros-decimais", "Números Decimais", ["leitura-de-decimais", "operacoes-com-decimais"],
     "images/icons/subjects/numeros-decimais.png"),
    ("porcentagem", "Porcentagem", ["porcentagem-basica", "calculo-de-porcentagem"],
     "images/icons/subjects/porcentagem.png"),
]

# icon_key points at static/images/ranks/<slug>.png (Fase 5 art pack).
RANKS = [
    ("iniciante", "Iniciante", 1, 1, "images/ranks/iniciante.png"),
    ("bronze", "Bronze", 2, 5, "images/ranks/bronze.png"),
    ("prata", "Prata", 3, 10, "images/ranks/prata.png"),
    ("ouro", "Ouro", 4, 20, "images/ranks/ouro.png"),
    ("platina", "Platina", 5, 35, "images/ranks/platina.png"),
    ("diamante", "Diamante", 6, 50, "images/ranks/diamante.png"),
    ("mestre", "Mestre", 7, 75, "images/ranks/mestre.png"),
]

# icon_key points at static/images/achievements/<code>.png (Fase 5 art pack).
ACHIEVEMENTS = [
    ("primeiro_acerto", "Primeiro Acerto", "Responda sua primeira questão corretamente.",
     {"type": "attempts_correct_total", "value": 1}, "images/achievements/primeiro_acerto.png"),
    ("cem_questoes", "100 Questões Respondidas", "Responda 100 questões.",
     {"type": "attempts_total", "value": 100}, "images/achievements/cem_questoes.png"),
    ("sete_dias", "7 Dias de Prática", "Pratique por 7 dias diferentes.",
     {"type": "distinct_practice_days", "value": 7}, "images/achievements/sete_dias.png"),
]


def seed_curriculum():
    for order, (slug, name, topic_slugs, icon_key) in enumerate(CURRICULUM):
        subject = Subject.query.filter_by(slug=slug).first()
        if not subject:
            subject = Subject(slug=slug, name=name, order=order, icon_key=icon_key)
            db.session.add(subject)
            db.session.flush()
        else:
            subject.name, subject.order, subject.icon_key = name, order, icon_key

        for t_order, t_slug in enumerate(topic_slugs):
            topic = Topic.query.filter_by(slug=t_slug).first()
            if not topic:
                db.session.add(Topic(
                    slug=t_slug,
                    name=t_slug.replace("-", " ").capitalize(),
                    subject_id=subject.id,
                    order=t_order,
                ))


def seed_levels(count: int = 50):
    for number in range(1, count + 1):
        if Level.query.filter_by(number=number).first():
            continue
        # Simple curve: gentle at first, steeper later. Tune freely later —
        # this lives in the DB, not in code, on purpose. Level 1 requires
        # 0 XP so a brand-new player starts there instead of "unleveled".
        xp_required = int(50 * (number - 1) ** 1.4)
        db.session.add(Level(number=number, xp_required=xp_required))


def seed_ranks():
    for slug, name, order, min_level, icon_key in RANKS:
        rank = Rank.query.filter_by(slug=slug).first()
        if not rank:
            db.session.add(Rank(
                slug=slug, name=name, order=order, min_level=min_level, icon_key=icon_key,
            ))
        else:
            rank.name, rank.order, rank.min_level, rank.icon_key = name, order, min_level, icon_key


def seed_achievements():
    for code, name, description, criteria, icon_key in ACHIEVEMENTS:
        achievement = Achievement.query.filter_by(code=code).first()
        if not achievement:
            db.session.add(Achievement(
                code=code, name=name, description=description, criteria=criteria,
                icon_key=icon_key,
            ))
        else:
            achievement.name = name
            achievement.description = description
            achievement.criteria = criteria
            achievement.icon_key = icon_key


def main():
    app = create_app()
    with app.app_context():
        seed_curriculum()
        seed_levels()
        seed_ranks()
        seed_achievements()
        db.session.commit()
        print("Seed concluído.")


if __name__ == "__main__":
    main()
