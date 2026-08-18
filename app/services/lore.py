"""Kingdom lore — "As Crônicas de Arith", one continuous story arc spun
across every subject, tying the curriculum to the "Ruínas de Arith"
setting already established in the battle arena's intro overlay. Purely
flavor text, curated like mentor_tips.py: no DB table, just a keyed lookup
read by app/mathematics/routes.py.

Each subject's chronicle is a list of `stages` — short chapters, not one
wall of text — revealed one stage per boss defeated (see
battle-arena.js's nextLoreSnippet), so progress through the curriculum
reads as progress through an actual plot. A chronicle is "discovered"
(all its stages become readable on the Crônicas do Reino page) once the
player has practiced anything in that subject — see chronicles() in
app/mathematics/routes.py for the reveal check.
"""
from typing import TypedDict


class Chronicle(TypedDict):
    title: str
    stages: list[str]


LORE: dict[str, Chronicle] = {
    "fundamentos": {
        "title": "Os Primeiros Passos",
        "stages": [
            "Antes de existirem números, existia apenas a contagem — pastores marcando ovelhas com pedras, mercadores comparando montes de grãos. Diz a lenda que o Reino de Arith nasceu assim, do simples ato de contar e comparar.",
            "Por gerações, Arith prosperou sob a Casa de Sela, guardiã das Ruínas e de tudo que nelas foi selado. O último desses guardiões teve uma única filha: a princesa Sela, nomeada em homenagem à própria linhagem, criada para um dia proteger o reino como seus ancestrais.",
            "Contam os anciãos que Sela nasceu numa noite em que todas as constelações de Arith se alinharam em números perfeitos — um sinal, diziam eles, de que seu destino estaria para sempre entrelaçado com os mistérios que o reino guarda.",
            "Você é apenas mais um aprendiz nas trilhas de Arith — sem título, sem linhagem — mas todo aprendiz começa exatamente aqui, como começou o próprio reino: contando, comparando, aprendendo a enxergar padrões onde antes só havia caos.",
            "As Ruínas que a Casa de Sela jura proteger não guardam ouro nem armas — guardam números antigos demais para serem esquecidos, selados ali por um motivo que nenhum guarda comum tem permissão de conhecer.",
            "Um velho mentor de olhar de coruja notou seu talento nos primeiros exercícios e sussurrou algo que você não esqueceria: \"Quem domina o começo, um dia é chamado para terminar o que outros não conseguiram.\" Você não sabia ainda o quanto essas palavras seriam verdadeiras.",
        ],
    },
    "tabuada": {
        "title": "As Tábuas Sagradas",
        "stages": [
            "Nas ruínas mais profundas de Arith repousam tábuas de argila com mais de quatro mil anos — os primeiros registros de multiplicação já conhecidos. Os sábios do reino acreditavam que decorar essas tábuas era abrir um atalho direto para a mente dos deuses do cálculo.",
            "A princesa Sela foi a última a completar o Rito das Tábuas Sagradas antes de desaparecer — numa noite sem lua, diante de toda a corte, ela simplesmente não estava mais lá quando a última tábua foi recitada.",
            "Não houve grito, não houve luta. Apenas a Hidra das Tábuas, desperta de seu sono milenar, guardando o salão vazio onde a princesa deveria estar — como se algo, ou alguém, tivesse apagado sua presença do próprio tempo.",
            "O rei ofereceu riquezas a quem a encontrasse. Um jovem guarda-aprendiz, que a conhecia desde criança e nunca teve coragem de dizer o que sentia, foi o único que pediu para ir sem exigir nada em troca.",
            "Cabe a você — aprendiz de Arith, tenha escolhido a classe que escolheu — seguir os mesmos passos que ele seguiu, decifrando as tábuas uma a uma até que a Hidra reconheça em você alguém digno de confiança.",
            "Entre as tábuas mais antigas, você encontra uma marca estranha, recente demais para pertencer às ruínas — um símbolo repetido em várias delas, como se alguém tivesse vasculhado esse mesmo salão pouco antes de você.",
            "Um servo da corte, nervoso demais para ser inocente, admite ter visto um mercador estrangeiro rondando o salão das tábuas na semana do desaparecimento — comprando \"proteção\" que ninguém pedira, vendendo respostas que ninguém confirmava.",
        ],
    },
    "operacoes-fundamentais": {
        "title": "A Forja das Quatro Artes",
        "stages": [
            "Soma, subtração, multiplicação e divisão — os quatro martelos da Forja Aritmética, onde todo conhecimento mais complexo de Arith é moldado. Nenhum feitiço maior do reino existe sem que essas quatro ferramentas tenham sido dominadas primeiro.",
            "O rei convocou o Ferreiro-Mestre para forjar uma lâmina capaz de cortar através de qualquer ilusão — a Lâmina das Quatro Artes — para quem se dispusesse a resgatar Sela dos limites conhecidos do reino.",
            "\"Uma lâmina forjada às pressas quebra na primeira mentira que encontrar\", avisou o Ferreiro-Mestre. \"Domine soma, subtração, multiplicação e divisão de verdade, ou volte antes mesmo de partir.\"",
            "A Quimera Aritmética guarda a forja não para impedir aprendizes, mas para testá-los — só quem prova domínio genuíno das quatro artes recebe uma lâmina que não falha na hora certa.",
            "Você entra na forja sabendo o que está em jogo: cada operação fundamental dominada aqui é um golpe a mais na lâmina que, mais adiante, pode ser a diferença entre trazer Sela de volta ou perdê-la para sempre.",
            "A lâmina finalmente forjada, o Ferreiro-Mestre a examina em silêncio antes de entregá-la. \"Ela corta ilusões, não pessoas\", avisa. \"Se um dia você a apontar para alguém e ela falhar em cortar, pergunte-se se está mesmo diante de um inimigo.\"",
            "Antes de você partir, ele acrescenta, baixo, como quem teme ser ouvido: \"O monstro que você precisa vencer pode não rugir. Às vezes ele sorri, cobra em moedas, e chama isso de negócio.\"",
        ],
    },
    "potenciacao": {
        "title": "A Torre que Cresce aos Saltos",
        "stages": [
            "Contam os viajantes que existe uma torre em Arith cujos andares dobram, depois triplicam, depois crescem tão rápido que ninguém jamais alcançou o topo. Os arquitetos a chamam de Torre da Potência.",
            "Um rumor levou o guarda-aprendiz até a base dessa torre: vozes na cidade juravam ter visto uma luz dourada nas janelas mais altas, na mesma noite em que Sela desapareceu.",
            "Cada andar que ele subia dobrava de tamanho e de perigo — o que começava como uma escada virava um labirinto, e o que era um labirinto virava um andar inteiro, exponencialmente maior que o anterior.",
            "No topo, a Fênix Exponencial não atacou — ela testou. \"Poder que cresce sem controle consome quem o carrega\", disse ela, queimando e renascendo diante dele. \"Prove que você entende o quanto cada salto custa, antes de subir mais um andar.\"",
            "Foi ali, exausto mas de pé, que ele soube: a torre não escondia Sela — escondia apenas a prova de que ele estava disposto a pagar o preço de cada andar por ela. A verdadeira trilha estava em outro lugar.",
            "Descendo, encontra presa entre duas pedras soltas uma página arrancada de um diário — a letra é inconfundivelmente de Sela. \"Se alguém encontrar isto\", diz o trecho, \"saiba que escolhi isso. Não me procurem pela raiva. Procurem pela razão.\"",
            "A Fênix, já em brasa novamente, ainda observa do alto. \"Toda queda tem uma altura exata em que deixa de ser acidente e passa a ser escolha\", diz ela antes de se recolher. \"Lembre-se disso quando finalmente entender o que Sela escolheu.\"",
        ],
    },
    "radiciacao": {
        "title": "O Espelho Invertido",
        "stages": [
            "Em algum lugar de Arith há um espelho que não reflete rostos, mas desfaz feitiços — todo número elevado, ao passar por ele, retorna à sua forma original. Os magos chamam isso de radiciação: o caminho inverso da potência.",
            "Foi diante desse espelho, guardado pelo Espectro Glacial, que o guarda-aprendiz finalmente viu Sela outra vez — dúzias dela, na verdade, cada reflexo repetindo um gesto diferente, nenhum deles real.",
            "\"Um espelho não mente\", sussurrou o Espectro. \"Ele só devolve o que você já trouxe consigo — e você trouxe medo demais para enxergar a verdade.\"",
            "Encarando o próprio reflexo em vez dos de Sela, ele finalmente compreendeu: não foi um dragão, nem um monstro, que a levou. Foi uma maldição — tecida por alguém que conhecia bem demais os corredores do castelo.",
            "A raiz de qualquer potência esconde a verdade por trás do exagero. Cabe a você desfazer as ilusões uma a uma, camada por camada, até encontrar o que realmente está por baixo de tudo isso.",
            "Entre os cacos do espelho quebrado por engano numa fase anterior da busca, um reflexo teima em não desaparecer: o rosto de um homem de sorriso fácil e bolsos cheios de moedas, visto por Sela mais vezes do que ela jamais admitiu à corte.",
            "\"Nomes têm raízes, como os números\", murmura o Espectro Glacial ao se dissolver em névoa. \"Encontre a raiz do nome dele, e vai encontrar exatamente o que ele está escondendo de todos vocês.\"",
        ],
    },
    "fracoes": {
        "title": "Os Fragmentos do Cristal Partido",
        "stages": [
            "Um cristal inteiro guardava toda a sabedoria de Arith, até ser partido em pedaços desiguais na Grande Cisão. Cada fragmento — cada fração — ainda carrega uma parte do todo original.",
            "A maldição que prendeu Sela está amarrada a esse mesmo cristal: o Coração de Arith, estilhaçado séculos atrás e disperso pelo reino, cada pedaço guardado por criaturas que nem lembram mais o motivo.",
            "O Aracnídeo do Labirinto guarda o maior fragmento — não por ganância, mas porque foi encarregado disso há tanto tempo que já esqueceu que a guarda deveria ter um fim.",
            "Cada fragmento recuperado revela uma memória: um baile, uma promessa sussurrada, uma discussão na corte sobre segredos que Sela guardava sozinha havia meses antes de desaparecer.",
            "Juntar os fragmentos — juntar as frações — não é só magia. É reconstruir, pedaço por pedaço, a verdade inteira que alguém tentou espalhar longe demais para ser encontrada.",
            "Com quase todos os fragmentos reunidos, o Coração de Arith começa a revelar sua forma original — e nela, gravado no centro, um símbolo que também aparecia nas moedas estranhas encontradas no mercado.",
            "O Aracnídeo, agora manso, entrega o último pedaço que guardava sem lutar. \"A maldição não precisa de todo o cristal para ser desfeita\", ele adverte, \"só precisa que alguém tenha coragem de juntar o suficiente para enxergar a imagem inteira.\"",
        ],
    },
    "numeros-decimais": {
        "title": "A Ponte de Cristal",
        "stages": [
            "Entre uma torre e outra de Arith existe uma ponte transparente, dividida em dez, cem, mil degraus invisíveis — números decimais que permitem cruzar o espaço entre um número inteiro e o próximo com precisão cirúrgica.",
            "Um passo maior ou menor do que o exato despenca no vazio entre os números — a Serpente de Cristal que guarda a ponte não perdoa imprecisão, por menor que seja.",
            "Foi na metade dessa travessia, com o cristal cantando sob seus pés, que o guarda-aprendiz encontrou o último fragmento — e com ele, a memória mais dolorosa: a voz da própria Sela, pedindo para ser selada.",
            "\"Se eu ficar, a maldição se espalha para todo o reino\", ela dissera, sozinha, a um espelho vazio, na noite em que desapareceu. Não foi um sequestro. Foi um sacrifício silencioso, feito para proteger todos que ela amava.",
            "A precisão da ponte de cristal ensina algo que nenhuma arma ensina: às vezes o gesto mais heroico não é o mais espalhafatoso, mas o mais exato — o único passo certo, no momento certo, para salvar quem se ama sem que ninguém perceba o custo.",
            "Do outro lado da ponte, uma câmara selada espera, silenciosa. É ali, sente o guarda-aprendiz, que Sela finalmente escolheu ficar — não presa, mas montando guarda sobre a própria maldição, sozinha, há meses.",
            "\"Não venha me salvar sem primeiro descobrir quem se beneficia de eu continuar selada\", ecoa a voz dela uma última vez pela ponte de cristal. \"Salvar-me cedo demais só devolve o poder a quem nunca deveria tê-lo tido.\"",
        ],
    },
    "porcentagem": {
        "title": "O Mercado das Cem Moedas",
        "stages": [
            "No coração de Arith fica o Mercado das Cem Moedas, onde tudo — impostos, descontos, lucros — é medido em partes de cem. \"Per cento\", diziam os antigos comerciantes: por cada cem, uma fração de valor.",
            "Foi entre as barracas desse mercado que o guarda-aprendiz encontrou o Mercador das Sombras — um homem que vendia \"proteção\" contra a maldição havia meses, cobrando cada vez mais conforme o medo do povo crescia.",
            "As contas não fechavam: o mercador lucrava exatamente na proporção em que o medo aumentava. Cem por cento de lucro, sempre que a esperança do reino caía mais um pouco.",
            "Confrontado, ele riu. \"A maldição de Sela não é acidente, aprendiz. Uma princesa desaparecida vale mais para mim viva-e-sumida do que livre. Cuidado com quem se beneficia da sua desgraça.\"",
            "Ele escapou pelas sombras do próprio mercado antes que pudesse ser detido — mas deixou para trás a pista final: seu verdadeiro nome, escondido dentro de uma equação que só um mestre da álgebra seria capaz de resolver.",
            "Seguindo os livros-caixa abandonados às pressas, o guarda-aprendiz reconstrói a rota do Mercador: cada \"desconto\" vendido, cada moeda extra cobrada, todas apontando na mesma direção — para os portões do Castelo Final, no topo de Arith.",
            "Os mercadores da cidade, libertos do medo que os prendia a comprar \"proteção\", finalmente falam livremente: o homem sempre soube demais sobre a maldição para ser só um oportunista de passagem.",
        ],
    },
    "algebra": {
        "title": "O Grande Castelo das Incógnitas",
        "stages": [
            "No topo de Arith ergue-se um castelo cujos portões só se abrem para quem encontra o que se esconde atrás da letra x. É lá que o Mercador das Sombras se refugiou, e é lá que Sela permanece selada, protegendo o reino à custa da própria liberdade.",
            "Dizem que o próprio Mercador escondeu seu nome verdadeiro dentro de uma equação havia anos — vaidade de quem nunca imaginou que alguém chegaria tão longe a ponto de precisar resolvê-la.",
            "Você chega ao Castelo Final carregando tudo que aprendeu: a lâmina forjada nas quatro artes, o peso das potências, a clareza do espelho invertido, os fragmentos reunidos do Coração de Arith, a precisão da ponte de cristal.",
            "O Guardião do Castelo Final não é um monstro comum — é a própria incógnita, a última equação entre você e a verdade. Resolvê-la é o único jeito de romper a maldição e libertar Sela para sempre.",
            "E quando o x finalmente se revela — um nome, uma identidade, uma verdade que o Mercador das Sombras jamais quis que ninguém descobrisse — o Reino de Arith respira de novo, e uma nova crônica, ainda não escrita, começa a se formar no horizonte.",
            "Sela retorna à corte não como uma princesa resgatada, mas como quem escolheu seu próprio sacrifício e venceu por conta própria — o guarda-aprendiz apenas resolveu a última equação que faltava para que ela pudesse finalmente sair.",
            "Nas comemorações que tomam Arith por dias, um mensageiro chega exausto das fronteiras mais distantes do reino, trazendo rumores de números ainda maiores, ruínas ainda mais antigas, e um mistério novo esperando por quem tiver coragem de segui-lo.",
        ],
    },
}


def for_subject(subject_slug: str) -> Chronicle | None:
    return LORE.get(subject_slug)
