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
    {"kind": "curiosidade", "text": "Os babilônios usavam um sistema numérico de base 60 (sexagesimal) há mais de 4000 anos — por isso até hoje uma hora tem 60 minutos e um círculo tem 360 graus."},
    {"kind": "curiosidade", "text": "O Papiro de Rhind, escrito no Egito por volta de 1650 a.C., é um dos textos matemáticos mais antigos já encontrados — e já trazia problemas com frações e equações."},
    {"kind": "curiosidade", "text": "A palavra \"álgebra\" vem do árabe \"al-jabr\", parte do título de um livro escrito pelo matemático persa Al-Khwarizmi no século IX."},
    {"kind": "curiosidade", "text": "A palavra \"algoritmo\" é uma homenagem a esse mesmo Al-Khwarizmi — seu nome, latinizado na Europa medieval, virou \"algorithmus\"."},
    {"kind": "curiosidade", "text": "O zero como número de verdade (e não só como \"nada\") foi desenvolvido na Índia — o matemático Brahmagupta descreveu suas regras por volta do ano 628."},
    {"kind": "curiosidade", "text": "Os algarismos que usamos hoje (0 a 9) são chamados de indo-arábicos: nasceram na Índia e chegaram à Europa através de matemáticos do mundo árabe."},
    {"kind": "curiosidade", "text": "Foi o matemático italiano Fibonacci quem popularizou os algarismos indo-arábicos na Europa, no livro Liber Abaci, em 1202 — antes disso o continente usava numerais romanos."},
    {"kind": "curiosidade", "text": "A sequência de Fibonacci (1, 1, 2, 3, 5, 8, 13...) aparece na natureza: no número de pétalas de muitas flores, nas espirais de girassóis e até na concha do náutilo."},
    {"kind": "curiosidade", "text": "O teorema de Pitágoras já era conhecido por babilônios e egípcios séculos antes de Pitágoras nascer — os gregos foram quem provaram por que ele é sempre verdadeiro."},
    {"kind": "curiosidade", "text": "Euclides escreveu \"Os Elementos\" na Grécia antiga por volta de 300 a.C. — um dos livros mais influentes da história, ainda base da geometria que se estuda hoje."},
    {"kind": "curiosidade", "text": "Arquimedes calculou uma aproximação de π desenhando polígonos de até 96 lados dentro e fora de um círculo — sem calculadora, só régua, compasso e paciência."},
    {"kind": "curiosidade", "text": "O ábaco é uma das ferramentas de cálculo mais antigas do mundo — sumérios, chineses, romanos e muitos outros povos tiveram sua própria versão dele."},
    {"kind": "curiosidade", "text": "O símbolo × para multiplicação foi criado pelo inglês William Oughtred em 1631 — antes disso, cada matemático usava sua própria notação."},
    {"kind": "curiosidade", "text": "Os sinais + e - começaram a aparecer em textos comerciais alemães do século XV, para marcar excesso e falta de peso em mercadorias, antes de virarem símbolos matemáticos."},
    {"kind": "curiosidade", "text": "Números negativos já eram usados na China antiga, representados com bastões de cores diferentes, e na Índia — séculos antes de serem aceitos pelos matemáticos europeus."},
    {"kind": "curiosidade", "text": "O Crivo de Eratóstenes, de um matemático grego que também calculou a circunferência da Terra, é até hoje um dos métodos mais simples para encontrar números primos."},
    {"kind": "curiosidade", "text": "Existem infinitos números primos — Euclides provou isso há mais de 2000 anos, com um argumento tão elegante que é ensinado quase do mesmo jeito até hoje."},
    {"kind": "curiosidade", "text": "O número de ouro (aproximadamente 1,618) aparece em obras de arte, arquitetura e na razão entre números consecutivos da sequência de Fibonacci."},
    {"kind": "curiosidade", "text": "\"Os Nove Capítulos sobre a Arte Matemática\", escrito na China há mais de 2000 anos, já apresentava métodos para resolver sistemas de equações."},
    {"kind": "curiosidade", "text": "A palavra \"cálculo\" vem do latim \"calculus\", que significa \"pedrinha\" — os romanos faziam contas movendo pedrinhas sobre um ábaco."},
    {"kind": "regra", "text": "Cada acerto soma XP e aumenta seu domínio no tópico; cada erro reduz um pouco esse domínio — vale mais praticar com calma do que responder no chute."},
    {"kind": "regra", "text": "A dificuldade das questões se ajusta ao seu desempenho: acertos seguidos trazem desafios maiores, e dificuldades trazem questões mais simples de volta."},
    {"kind": "regra", "text": "Respostas com vírgula (0,5) ou ponto (0.5) são aceitas — escreva do jeito que for mais natural para você."},
    {"kind": "regra", "text": "Tópicos com domínio baixo aparecem na fila de Revisão — vale a pena visitá-la de vez em quando para não esquecer o que já aprendeu."},
    {"kind": "regra", "text": "Depois de treinar cada tabuada separadamente, experimente a Tabuada Mista — ela sorteia qualquer tabela de 1 a 10, um bom teste de domínio completo."},
    {"kind": "regra", "text": "Seu rank sobe junto com seu nível — cada rank exige um nível mínimo, então subir de nível é sempre o caminho mais direto até o próximo."},

    # ---- second wave: more curiosities + rules, added alongside a longer
    # on-screen reading time in Salão do Herói (see dashboard.html) so
    # there's actually room to read more of the pool per visit. ----
    {"kind": "curiosidade", "text": "No Triângulo de Pascal, cada número é a soma dos dois números acima dele — uma ferramenta de séculos atrás ainda usada para calcular combinações e probabilidades."},
    {"kind": "curiosidade", "text": "Números primos gêmeos são pares de primos que diferem por apenas 2, como 11 e 13, ou 17 e 19 — ninguém ainda provou se existem infinitos pares assim."},
    {"kind": "curiosidade", "text": "Divisão por zero não tem resultado definido — não existe número que, multiplicado por zero, dê de volta o valor original."},
    {"kind": "curiosidade", "text": "MDC (máximo divisor comum) e MMC (mínimo múltiplo comum) já eram usados na Grécia antiga para simplificar frações e resolver problemas de repetição de eventos."},
    {"kind": "curiosidade", "text": "O sistema de numerais romanos não tinha um símbolo para o zero — o que tornava contas grandes bem mais difíceis do que com os algarismos indo-arábicos que usamos hoje."},
    {"kind": "curiosidade", "text": "A palavra \"geometria\" vem do grego e significa \"medir a terra\" — surgiu no Egito antigo para redemarcar terrenos depois das cheias do rio Nilo."},
    {"kind": "curiosidade", "text": "O matemático francês Blaise Pascal construiu, em 1642, uma das primeiras máquinas de somar mecânicas da história — a \"Pascalina\"."},
    {"kind": "curiosidade", "text": "Um número perfeito é igual à soma dos seus próprios divisores (sem contar ele mesmo) — o menor exemplo é o 6, já que 1 + 2 + 3 = 6."},
    {"kind": "curiosidade", "text": "A notação científica existe para escrever números muito grandes ou muito pequenos de forma compacta — como a distância até outras estrelas."},
    {"kind": "curiosidade", "text": "A simetria aparece tanto na geometria (flores, borboletas, prédios) quanto na álgebra, em funções que se comportam da mesma forma dos dois lados do zero."},

    {"kind": "regra", "text": "Fugir de uma batalha não apaga seu progresso — as respostas certas já dadas continuam valendo; só a vitória cosmética do chefe fica para a próxima tentativa."},
    {"kind": "regra", "text": "Equipamentos só mudam a apresentação da batalha (dano, crítico, fúria) — nunca o XP ou o domínio real, que dependem só das suas respostas certas."},
    {"kind": "regra", "text": "Cada matéria tem sua própria trilha — vencer o guardião final de uma não bloqueia as outras; você pode explorar a ordem que quiser."},
]


def random_tip() -> Tip:
    return random.choice(TIPS)


def random_tips(count: int = 6) -> list[Tip]:
    """A handful of distinct tips, e.g. for a client-side rotating widget —
    random_tip() only ever hands back one, which isn't enough to cycle
    through without repeats until the whole batch is exhausted."""
    return random.sample(TIPS, min(count, len(TIPS)))
