"""
Curated curiosities/rules shown by the mentor sidekick on the practice
screen. No character art exists for a second NPC yet, so the mentor is a
CSS-drawn avatar (see .mentor-avatar in ui.css); this module only owns the
copy, kept DB-free like the rest of app/services so it can be picked with a
plain random.choice() from the route.
"""
import random
from typing import TypedDict


class Tip(TypedDict):
    kind: str  # "curiosidade" | "regra"
    text: str


TIPS: list[Tip] = [
    {"kind": "curiosidade", "text": "O símbolo \"=\" foi criado em 1557 pelo matemático Robert Recorde — ele estava cansado de escrever \"é igual a\" o tempo todo."},
    {"kind": "curiosidade", "text": "O número π (pi) tem infinitas casas decimais e nunca se repete. Ninguém jamais vai terminar de escrevê-lo."},
    {"kind": "curiosidade", "text": "Usamos o sistema decimal (base 10) provavelmente porque temos 10 dedos nas mãos."},
    {"kind": "curiosidade", "text": "O símbolo de porcentagem (%) vem da abreviação italiana \"per cento\", que significa \"por cento\"."},
    {"kind": "curiosidade", "text": "Frações já eram usadas pelos egípcios antigos há mais de 4000 anos — mas quase sempre com numerador 1."},
    {"kind": "curiosidade", "text": "O zero não é positivo nem negativo, e levou séculos até ser aceito como um número de verdade."},
    {"kind": "curiosidade", "text": "A tabuada como você conhece existe há mais de 4000 anos — tábuas de multiplicação já apareciam em tabletes babilônicos."},
    {"kind": "curiosidade", "text": "Todo número elevado a zero é igual a 1 — inclusive o próprio zero elevado a zero é, por convenção, 1 em quase todos os contextos."},
    {"kind": "regra", "text": "Cada acerto soma XP e aumenta seu domínio no tópico; cada erro reduz um pouco esse domínio — vale mais praticar com calma do que responder no chute."},
    {"kind": "regra", "text": "A dificuldade das questões se ajusta ao seu desempenho: acertos seguidos trazem desafios maiores, e dificuldades trazem questões mais simples de volta."},
    {"kind": "regra", "text": "Respostas com vírgula (0,5) ou ponto (0.5) são aceitas — escreva do jeito que for mais natural para você."},
    {"kind": "regra", "text": "Tópicos com domínio baixo aparecem na fila de Revisão — vale a pena visitá-la de vez em quando para não esquecer o que já aprendeu."},
]


def random_tip() -> Tip:
    return random.choice(TIPS)
