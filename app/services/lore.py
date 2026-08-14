"""Kingdom lore — one short chronicle per subject, tying the curriculum to
the "Ruínas de Arith" setting already established in the battle arena's
intro overlay. Purely flavor text, curated like mentor_tips.py: no DB
table, just a keyed lookup read by app/mathematics/routes.py. A chronicle
is "discovered" once the player has practiced anything in that subject —
see chronicles() in app/mathematics/routes.py for the reveal check.
"""
from typing import TypedDict


class Chronicle(TypedDict):
    title: str
    text: str


LORE: dict[str, Chronicle] = {
    "fundamentos": {
        "title": "Os Primeiros Passos",
        "text": (
            "Antes de existirem números, existia apenas a contagem — pastores marcando "
            "ovelhas com pedras, mercadores comparando montes de grãos. Diz a lenda que o "
            "Reino de Arith nasceu assim, do simples ato de contar e comparar. Todo "
            "aprendiz começa por aqui, como começou o próprio reino."
        ),
    },
    "tabuada": {
        "title": "As Tábuas Sagradas",
        "text": (
            "Nas ruínas mais profundas de Arith repousam tábuas de argila com mais de "
            "quatro mil anos — os primeiros registros de multiplicação já conhecidos. "
            "Os sábios do reino acreditavam que decorar essas tábuas era abrir um atalho "
            "direto para a mente dos deuses do cálculo."
        ),
    },
    "operacoes-fundamentais": {
        "title": "A Forja das Quatro Artes",
        "text": (
            "Soma, subtração, multiplicação e divisão — os quatro martelos da Forja "
            "Aritmética, onde todo conhecimento mais complexo de Arith é moldado. Nenhum "
            "feitiço maior do reino existe sem que essas quatro ferramentas tenham sido "
            "dominadas primeiro."
        ),
    },
    "potenciacao": {
        "title": "A Torre que Cresce aos Saltos",
        "text": (
            "Contam os viajantes que existe uma torre em Arith cujos andares dobram, "
            "depois triplicam, depois crescem tão rápido que ninguém jamais alcançou o "
            "topo. Os arquitetos a chamam de Torre da Potência — cada exponente, um novo "
            "andar impossível de prever a olho nu."
        ),
    },
    "radiciacao": {
        "title": "O Espelho Invertido",
        "text": (
            "Em algum lugar de Arith há um espelho que não reflete rostos, mas desfaz "
            "feitiços — todo número elevado, ao passar por ele, retorna à sua forma "
            "original. Os magos chamam isso de radiciação: o caminho inverso da potência."
        ),
    },
    "fracoes": {
        "title": "Os Fragmentos do Cristal Partido",
        "text": (
            "Um cristal inteiro guardava toda a sabedoria de Arith, até ser partido em "
            "pedaços desiguais na Grande Cisão. Cada fragmento — cada fração — ainda "
            "carrega uma parte do todo original, e só juntando-os de novo o reino "
            "recupera o que foi perdido."
        ),
    },
    "numeros-decimais": {
        "title": "A Ponte de Cristal",
        "text": (
            "Entre uma torre e outra de Arith existe uma ponte transparente, dividida em "
            "dez, cem, mil degraus invisíveis — números decimais que permitem cruzar o "
            "espaço entre um número inteiro e o próximo com precisão cirúrgica."
        ),
    },
    "porcentagem": {
        "title": "O Mercado das Cem Moedas",
        "text": (
            "No coração de Arith fica o Mercado das Cem Moedas, onde tudo — impostos, "
            "descontos, lucros — é medido em partes de cem. \"Per cento\", diziam os "
            "antigos comerciantes: por cada cem, uma fração de valor."
        ),
    },
    "algebra": {
        "title": "O Grande Castelo das Incógnitas",
        "text": (
            "No topo de Arith ergue-se um castelo cujos portões só se abrem para quem "
            "encontra o que se esconde atrás da letra x. Dizem que o próprio fundador do "
            "reino escondeu seu nome verdadeiro dentro de uma equação, e que só um "
            "verdadeiro mestre da álgebra seria capaz de resolvê-la e descobrir quem ele foi."
        ),
    },
}


def for_subject(subject_slug: str) -> Chronicle | None:
    return LORE.get(subject_slug)
