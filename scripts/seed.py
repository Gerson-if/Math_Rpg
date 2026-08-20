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
#
# Each entry is (slug, name, topic_slugs, icon_key) or, for a subject whose
# very first topic should carry an *advisory* cross-subject recommendation
# (never a hard lock — see progression_service.unmet_prerequisites),
# (slug, name, topic_slugs, icon_key, entry_prereqs).
CURRICULUM = [
    ("fundamentos", "Fundamentos", ["numeros-e-contagem", "comparacao-de-quantidades"],
     "images/icons/subjects/fundamentos.png"),
    ("tabuada", "Tabuada", [f"tabuada-do-{n}" for n in range(1, 11)] + ["tabuada-mista"],
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
    # The "castelo final" — new, more advanced content, added at the end of
    # the trail. Recommended only after Porcentagem (see entry_prereqs
    # below), but exactly as jumpable-ahead as everything else; nothing
    # about it is force-locked for lower-level players.
    ("algebra", "Álgebra", ["equacoes-1-grau", "equacoes-1-grau-avancado"],
     None, ["calculo-de-porcentagem"]),
    # Two more regions past the castle, added to continue the trail
    # instead of leaving Álgebra as a dead end (see progression_service.
    # next_topic_for's cross-subject continuation). Equações do 2º Grau is
    # the direct next step from Álgebra's own linear equations; Geometria
    # Básica opens a new skill entirely (perímetro/área) rather than going
    # deeper into algebra a third time in a row.
    ("equacoes-2-grau", "Equações do 2º Grau",
     ["equacoes-2-grau-incompletas", "equacoes-2-grau-fatoravel"],
     None, ["equacoes-1-grau-avancado"]),
    ("geometria-basica", "Geometria Básica",
     ["perimetro-de-figuras", "area-de-figuras"],
     None),
]

# icon_key points at static/images/ranks/<slug>.png (Fase 5 art pack). The
# top 3 tiers have no dedicated art yet — rank_badge() in _macros.html
# already falls back to a 2-letter initial badge with its own per-tier
# color theme (see RANK_THEME there), so they're not blocked on art.
RANKS = [
    ("iniciante", "Iniciante", 1, 1, "images/ranks/iniciante.png"),
    ("bronze", "Bronze", 2, 5, "images/ranks/bronze.png"),
    ("prata", "Prata", 3, 10, "images/ranks/prata.png"),
    ("ouro", "Ouro", 4, 20, "images/ranks/ouro.png"),
    ("platina", "Platina", 5, 35, "images/ranks/platina.png"),
    ("diamante", "Diamante", 6, 50, "images/ranks/diamante.png"),
    ("mestre", "Mestre", 7, 75, "images/ranks/mestre.png"),
    ("grao-mestre", "Grão-Mestre", 8, 100, None),
    ("lenda", "Lenda do Reino", 9, 150, None),
    ("imortal", "Imortal", 10, 200, None),
]

# icon_key points at static/images/achievements/<code>.png (Fase 5 art pack).
ACHIEVEMENTS = [
    ("primeiro_acerto", "Primeiro Acerto", "Responda sua primeira questão corretamente.",
     {"type": "attempts_correct_total", "value": 1}, "images/achievements/primeiro_acerto.png"),
    ("cem_questoes", "100 Questões Respondidas", "Responda 100 questões.",
     {"type": "attempts_total", "value": 100}, "images/achievements/cem_questoes.png"),
    ("sete_dias", "7 Dias de Prática", "Pratique por 7 dias diferentes.",
     {"type": "distinct_practice_days", "value": 7}, "images/achievements/sete_dias.png"),
    ("dominou_potenciacao", "Mestre da Potenciação", "Acerte 20 questões de Potenciação.",
     {"type": "attempts_correct_in_subject", "subject": "potenciacao", "value": 20},
     "images/icons/subjects/potenciacao.png"),
    ("dominou_radiciacao", "Mestre da Radiciação", "Acerte 20 questões de Radiciação.",
     {"type": "attempts_correct_in_subject", "subject": "radiciacao", "value": 20},
     "images/icons/subjects/radiciacao.png"),
    ("dominou_fracoes", "Mestre das Frações", "Acerte 20 questões de Frações.",
     {"type": "attempts_correct_in_subject", "subject": "fracoes", "value": 20},
     "images/icons/subjects/fracoes.png"),
    ("dominou_decimais", "Mestre dos Decimais", "Acerte 20 questões de Números Decimais.",
     {"type": "attempts_correct_in_subject", "subject": "numeros-decimais", "value": 20},
     "images/icons/subjects/numeros-decimais.png"),
    ("dominou_porcentagem", "Mestre da Porcentagem", "Acerte 20 questões de Porcentagem.",
     {"type": "attempts_correct_in_subject", "subject": "porcentagem", "value": 20},
     "images/icons/subjects/porcentagem.png"),
    ("dominou_fundamentos", "Mestre dos Fundamentos", "Acerte 20 questões de Fundamentos.",
     {"type": "attempts_correct_in_subject", "subject": "fundamentos", "value": 20},
     "images/icons/subjects/fundamentos.png"),
    ("dominou_tabuada", "Mestre da Tabuada", "Acerte 20 questões de Tabuada.",
     {"type": "attempts_correct_in_subject", "subject": "tabuada", "value": 20},
     "images/icons/subjects/tabuada.png"),
    ("dominou_operacoes", "Mestre das Operações Fundamentais",
     "Acerte 20 questões de Operações Fundamentais.",
     {"type": "attempts_correct_in_subject", "subject": "operacoes-fundamentais", "value": 20},
     "images/icons/subjects/operacoes-fundamentais.png"),
    # No dedicated art for the ones below (the streak-flame icon they used
    # to point at belonged to the retired UI pack) — they fall back to the
    # FontAwesome trophy/lock badge in _macros.html, which already matches
    # the theme just fine.
    ("sequencia_de_ferro", "Sequência de Ferro", "Alcance uma sequência de 10 acertos seguidos.",
     {"type": "best_streak", "value": 10}, None),
    ("sequencia_lendaria", "Sequência Lendária", "Alcance uma sequência de 25 acertos seguidos.",
     {"type": "best_streak", "value": 25}, None),
    ("quinhentas_questoes", "500 Questões Respondidas", "Responda 500 questões.",
     {"type": "attempts_total", "value": 500}, None),
    ("mil_questoes", "Lenda Viva", "Responda 1000 questões.",
     {"type": "attempts_total", "value": 1000}, None),
    ("trinta_dias", "30 Dias de Prática", "Pratique por 30 dias diferentes.",
     {"type": "distinct_practice_days", "value": 30}, None),
    ("nivel_dez", "Aventureiro Experiente", "Alcance o nível 10.",
     {"type": "level_reached", "value": 10}, None),
    ("nivel_vinte_cinco", "Herói do Reino", "Alcance o nível 25.",
     {"type": "level_reached", "value": 25}, None),

    # ---- second wave: deeper volume/streak/consistency milestones, a
    # "grão-mestre" tier (50 acertos) for every subject mirroring the
    # existing 20-acerto tier above, higher level goals, and rank-reached
    # milestones tied to the new tiers in RANKS. ----
    ("duas_mil_e_quinhentas_questoes", "Mestre Incansável", "Responda 2500 questões.",
     {"type": "attempts_total", "value": 2500}, None),
    ("cinco_mil_questoes", "Lenda Matemática", "Responda 5000 questões.",
     {"type": "attempts_total", "value": 5000}, None),
    ("cem_dias", "Peregrino Centenário", "Pratique por 100 dias diferentes.",
     {"type": "distinct_practice_days", "value": 100}, None),
    ("sequencia_imortal", "Sequência Imortal", "Alcance uma sequência de 50 acertos seguidos.",
     {"type": "best_streak", "value": 50}, None),
    ("grao_mestre_potenciacao", "Grão-Mestre da Potenciação", "Acerte 50 questões de Potenciação.",
     {"type": "attempts_correct_in_subject", "subject": "potenciacao", "value": 50},
     "images/icons/subjects/potenciacao.png"),
    ("grao_mestre_radiciacao", "Grão-Mestre da Radiciação", "Acerte 50 questões de Radiciação.",
     {"type": "attempts_correct_in_subject", "subject": "radiciacao", "value": 50},
     "images/icons/subjects/radiciacao.png"),
    ("grao_mestre_fracoes", "Grão-Mestre das Frações", "Acerte 50 questões de Frações.",
     {"type": "attempts_correct_in_subject", "subject": "fracoes", "value": 50},
     "images/icons/subjects/fracoes.png"),
    ("grao_mestre_decimais", "Grão-Mestre dos Decimais", "Acerte 50 questões de Números Decimais.",
     {"type": "attempts_correct_in_subject", "subject": "numeros-decimais", "value": 50},
     "images/icons/subjects/numeros-decimais.png"),
    ("grao_mestre_porcentagem", "Grão-Mestre da Porcentagem", "Acerte 50 questões de Porcentagem.",
     {"type": "attempts_correct_in_subject", "subject": "porcentagem", "value": 50},
     "images/icons/subjects/porcentagem.png"),
    ("grao_mestre_fundamentos", "Grão-Mestre dos Fundamentos", "Acerte 50 questões de Fundamentos.",
     {"type": "attempts_correct_in_subject", "subject": "fundamentos", "value": 50},
     "images/icons/subjects/fundamentos.png"),
    ("grao_mestre_tabuada", "Grão-Mestre da Tabuada", "Acerte 50 questões de Tabuada.",
     {"type": "attempts_correct_in_subject", "subject": "tabuada", "value": 50},
     "images/icons/subjects/tabuada.png"),
    ("grao_mestre_operacoes", "Grão-Mestre das Operações Fundamentais",
     "Acerte 50 questões de Operações Fundamentais.",
     {"type": "attempts_correct_in_subject", "subject": "operacoes-fundamentais", "value": 50},
     "images/icons/subjects/operacoes-fundamentais.png"),
    ("nivel_cinquenta", "Campeão do Reino", "Alcance o nível 50.",
     {"type": "level_reached", "value": 50}, None),
    ("nivel_cem", "Lenda Absoluta", "Alcance o nível 100.",
     {"type": "level_reached", "value": 100}, None),
    # Rank orders come from RANKS above (platina=5, mestre=7,
    # grao-mestre=8, imortal=10) — kept as plain numbers here (not slugs)
    # to match rank_reached's "at least this order" comparison.
    ("chegou_platina", "Liga de Platina", "Alcance a liga Platina.",
     {"type": "rank_reached", "value": 5}, None),
    ("chegou_mestre", "Liga de Mestre", "Alcance a liga Mestre.",
     {"type": "rank_reached", "value": 7}, None),
    ("chegou_grao_mestre", "Liga de Grão-Mestre", "Alcance a liga Grão-Mestre.",
     {"type": "rank_reached", "value": 8}, None),
    ("chegou_imortal", "Imortal do Reino", "Alcance a liga Imortal — o topo da trilha.",
     {"type": "rank_reached", "value": 10}, None),
]


def seed_curriculum():
    for order, entry in enumerate(CURRICULUM):
        slug, name, topic_slugs, icon_key = entry[0], entry[1], entry[2], entry[3]
        entry_prereqs = entry[4] if len(entry) > 4 else []

        subject = Subject.query.filter_by(slug=slug).first()
        if not subject:
            subject = Subject(slug=slug, name=name, order=order, icon_key=icon_key)
            db.session.add(subject)
            db.session.flush()
        else:
            subject.name, subject.order, subject.icon_key = name, order, icon_key

        for t_order, t_slug in enumerate(topic_slugs):
            # Each topic recommends the one right before it in the same
            # subject's list — a simple linear chain, not a hand-designed
            # dependency graph. The first topic of a subject normally has
            # none, except when entry_prereqs points it at an earlier
            # subject's topic (e.g. Álgebra recommending Porcentagem
            # first). This is always a *recommendation* (see
            # progression_service.unmet_prerequisites), never a hard lock —
            # a player can still jump ahead.
            if t_order > 0:
                prereqs = [topic_slugs[t_order - 1]]
            else:
                prereqs = list(entry_prereqs)

            topic = Topic.query.filter_by(slug=t_slug).first()
            if not topic:
                db.session.add(Topic(
                    slug=t_slug,
                    name=t_slug.replace("-", " ").capitalize(),
                    subject_id=subject.id,
                    order=t_order,
                    prerequisite_slugs=prereqs,
                ))
            else:
                topic.order = t_order
                topic.prerequisite_slugs = prereqs


def seed_levels(count: int = 200):
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
