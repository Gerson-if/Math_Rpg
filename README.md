# Matemática RPG

Plataforma de aprendizado de matemática com progressão inspirada em RPG:
XP, níveis, domínio por tópico, conquistas, batalhas, equipamento, economia
e chat entre jogadores. Construída como uma aplicação Flask modular (app
factory + blueprints por domínio), com um motor de questões que gera
exercícios dinamicamente — nada de banco de perguntas fixo — e todo o
ciclo de progressão centralizado num único serviço.

A identidade visual é Tailwind CSS + FontAwesome sobre um tema medieval
(paleta parchment/blood/gold/mystic, tipografia MedievalSharp/Cinzel).
Rank, conquista e matéria usam ícones em pixel art extraídos de um pacote
de artes fantasy (ver `app/static/images/icons/CREDITS.txt`); o avatar do
jogador é escolhido entre um conjunto curado de ícones FontAwesome.

## Funcionalidades

### Currículo e motor de questões

- 9 matérias e 29 tópicos praticáveis (`app/services/mathematics_service.py`):
  Fundamentos, Tabuada (0–10 + uma variante mista que sorteia a base),
  as quatro operações fundamentais, Potenciação, Radiciação, Frações,
  Números Decimais, Porcentagem e Álgebra (equações do 1º grau).
- Cada tópico tem um gerador dedicado, sem acesso a banco de dados —
  registrar um tópico novo é só adicionar uma entrada ao dicionário de
  geradores, sem tocar em rota, model ou template.
- Frações usam `fractions.Fraction` (sem erro de ponto flutuante);
  divisão sempre gera resultado inteiro exato; a comparação de resposta
  aceita vírgula decimal (`0,3` == `0.3`) e floats de valor inteiro
  (`3.0` == `3`), além de frações como string (`5/6`).
- Fluxo de prática (`/math/praticar/<tópico>`): pergunta → resposta →
  correção → próxima pergunta, via HTMX, sem recarregar a página. A
  resposta correta nunca é enviada ao cliente em texto puro — fica
  assinada e com expiração num token (`app/services/question_token.py`),
  então não é preciso gravar uma linha de `Question` por exercício.
- `Topic.prerequisite_slugs` é uma recomendação, nunca um bloqueio: um
  tópico cujo pré-requisito ainda não tem domínio razoável mostra um
  aviso ("recomendado praticar primeiro: X"), mas continua 100%
  acessível.

### Progressão

- Serviço central de XP/domínio (`app/services/progression_service.py`),
  chamado uma única vez logo após cada `Attempt` ser salvo — nenhuma
  outra parte do código precisa saber que XP ou domínio existem.
- XP por acerto, escalado pela dificuldade (1–5); dificuldade efetiva se
  adapta ao desempenho recente do jogador naquele tópico (mastery score +
  streak), com um mínimo de tentativas antes de reagir para um
  acerto/erro isolado não fazer a dificuldade oscilar.
- Subida de nível e troca de rank calculadas a partir das tabelas
  `Level`/`Rank` (dados, não código).
- Domínio por (usuário, tópico) via média móvel exponencial ponderada
  pela dificuldade, com decaimento por retenção — ficar muitos dias sem
  praticar um tópico reduz o domínio mesmo sem erros novos, alimentando a
  fila de revisão (`/progressao/revisao`).
- Conquistas com critério declarativo em JSON (`Achievement.criteria`),
  checadas a cada resposta; desbloqueio gera `UserAchievement` +
  `Notification`. Até 3 conquistas desbloqueadas podem ser marcadas "em
  destaque" para aparecer no perfil público.
- Ranking global (`/ranking`), estilo "liga": pódio com os 3 primeiros
  colocados e badge de rank em cada linha da tabela. `LeaderboardEntry` +
  `flask recompute-leaderboards --scope weekly|monthly|global` ficam
  prontos para boards periódicos assim que um agendador externo (cron,
  systemd timer, Task Scheduler) for apontado para o comando.

### Sistema de batalha

A tela de prática é uma arena de batalha em tela cheia — mas a pergunta
por trás dela é sempre a mesma pergunta real de sempre. Combo, crítico
visual, fúria/ultimate e fases do chefe são uma camada de apresentação
por cima do loop real de pergunta/resposta (HTMX,
`/math/praticar/<tópico>/questao` e `/responder`): toda resposta continua
gerando XP, atualizando maestria e desbloqueando conquistas de verdade,
deliberadamente sem nenhuma forma de "otimizar equipamento para grindar
XP" — ver `app/services/loot_service.py`.

- Herói vs. Guardião, com barras de HP com efeito "afterimage" (ghost
  bar), combo, barra de fúria/ultimate, partículas/projéteis em canvas e
  áudio 100% procedural via Web Audio API — nada disso depende de asset
  externo.
- **Progressão real por matéria, não repetição**: os tópicos de cada
  matéria escalam em minion → minion de elite → o guardião real (só no
  último tópico) → uma versão suprema ressuscitada depois da primeira
  vitória sobre o guardião. Nomes de minion/elite variam por tópico
  dentro da mesma matéria (com sufixo de "onda" em romano quando uma
  matéria tem mais tópicos que o conjunto de nomes), então o jogador não
  enfrenta o mesmo monstro nomeado repetidas vezes.
- Uma resposta certa e rápida rende mais estrelas (0–3, decidido no
  servidor a partir do tempo de resposta) — cosmético, nunca afeta XP
  real: uma resposta correta lenta ainda conta inteira para a progressão.
- O chefe não pode cair antes de pelo menos 10 respostas certas naquela
  luta, não importa quanto dano combo/crítico/ultimate acumulem — uma
  fileira de marcadores mostra o progresso rumo a esse mínimo, evitando
  que um combo de sorte encerre a luta em poucas perguntas.
- O crítico que decide se cai loot é sorteado no servidor
  (`answer_question`, usando os buffs reais do equipamento via
  `loot_service.compute_buffs`) — o cliente só anima o que o servidor já
  decidiu. Loot garantido ao derrotar o chefe passa por um endpoint
  próprio (`POST /praticar/<tópico>/vitoria`), rate-limited e com uma
  checagem de integridade proporcional ao que está em jogo (existe um
  `Attempt` correto recente para aquele tópico).
- Ao vencer, uma tela de vitória em tela cheia revela o próximo capítulo
  da crônica daquela matéria e aguarda confirmação do jogador para ler —
  mas a transição para o próximo desafio depois disso é automática
  (com opção de agir antes, se preferir), sem exigir mais um clique.
- Consumíveis (poção/pergaminho) são por-batalha, não persistentes, numa
  tela cheia dedicada dentro do arena — nunca um modal.

### Mapa de Aventura e Crônicas do Reino

- O currículo é apresentado como um mapa ilustrado de pergaminho
  (`/math/`) com uma trilha sinuosa ligando todas as matérias — marco e
  ícone de guardião por matéria, pontos de tópico, bússola, legenda.
- O guardião de cada matéria pode ser desafiado diretamente a partir do
  próprio mapa (sem precisar navegar pelos tópicos um a um) assim que a
  trilha até ele estiver com domínio suficiente; antes disso, o marco
  mostra um indicador de bloqueado explicando o que falta.
- **"As Crônicas de Arith"**: uma trama contínua (a princesa Sela, uma
  maldição tecida pelo Mercador das Sombras) contada em capítulos por
  matéria (`app/services/lore.py`) — cada vitória sobre o guardião revela
  o próximo capítulo daquela trilha. A leitura acontece num leitor
  dedicado em tela cheia (`/math/cronicas/<matéria>`), um capítulo por
  vez, com transição de página animada e navegação por clique/setas.

### Loot, equipamento e economia

- Espólios têm 4 raridades e 6 slots de equipamento (arma, anel,
  amuleto, armadura, capacete, botas), cada um com um bônus passivo
  cosmético (dano/crítico/fúria/combo/vida/vampirismo). Equipar um item
  raro exige um nível mínimo do jogador, validado no servidor.
- Um espólio não equipado pode ser vendido ao reino por Ouro, descartado
  para sempre, ou anunciado na Loja dos Jogadores — todas as ações
  exigem desequipar primeiro, para nunca perder um bônus ativo sem
  querer.
- **Loja do Reino** (`/mercado`): estoque de itens gerado pelo próprio
  jogo, comprável com Ouro, renovado automaticamente a cada 24h.
- **Loja dos Jogadores**: qualquer espólio não equipado pode ser
  anunciado por um preço definido pelo dono; o anúncio fica visível para
  outros jogadores por um prazo limitado — se ninguém comprar, volta
  sozinho ao inventário do dono. Comprar transfere item e Ouro entre os
  dois jogadores numa única transação, e nunca contorna o nível mínimo
  para equipar.
- Equipamentos e espólios são preparados antes da batalha, no Salão do
  Herói — nunca trocados no meio de uma pergunta.

### Classes de personagem

- 5 classes (Guerreiro, Mago, Arqueiro, Clérigo, Ladino), cada uma
  associada a uma categoria de bônus cosmético — as mesmas do sistema de
  equipamento (`app/services/classes.py`). Escolha livre na primeira
  vez; depois só é possível trocar quando um novo nível de habilidade é
  desbloqueado (nível 10 "Adepto", nível 25 "Mestre"), ganhando uma
  habilidade nomeada por classe+tier a cada troca.
- Elegibilidade validada no servidor mesmo que a interface tente
  contornar; o perfil mostra a classe/habilidade atuais.

### Social

- Chat global (`/chat/`) via HTMX com polling — histórico renderizado no
  servidor, cooldown entre mensagens, bloqueio de mensagem repetida, uma
  heurística leve que sinaliza mensagens suspeitas para moderação
  (nunca bloqueia o envio sozinha), denúncia manual por qualquer
  jogador, e um badge de mensagens não lidas na navbar. O nome de cada
  jogador no chat é um link para o perfil público dele.
- Perfil público somente-leitura (`/jogador/<usuário>`) — classe,
  estatísticas e insígnias em destaque, sem e-mail e sem edição.
- Sistema de amigos (`app/friends/`): pedido por nome de usuário,
  aceitar/recusar, desfazer amizade, com badge de pendências na navbar.
- Convite de masmorra (co-op) assíncrono: um amigo aceito pode ajudar
  num tópico — o aliado aparece ao lado do herói na arena e ambos ganham
  um bônus de XP pequeno e verificado no servidor enquanto praticam o
  mesmo tópico dentro da janela do convite. Não é uma batalha
  sincronizada em tempo real (o app não tem transporte realtime).

## Produção

- Rate limiting explícito (Flask-Limiter) em rotas sensíveis (cadastro,
  login, resposta de questão, ações de economia), desligado em teste.
- Logs estruturados (`app/logging_config.py`): JSON por linha em stdout
  em produção, texto legível em desenvolvimento/teste — todo request
  loga method/path/status/user_id; exceções não tratadas entram com
  traceback completo.
- Páginas de erro próprias (404/500) sem vazar stack trace — a de 500
  não estende o layout autenticado, já que a navbar consulta o banco e
  um 500 pode ser justamente o banco fora do ar.
- Cookies de sessão com `HttpOnly`/`SameSite=Lax` sempre e `Secure` em
  produção; headers `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy` em toda resposta (HSTS fica por conta do proxy).
- `gunicorn.conf.py`, `Caddyfile` e `deploy/math-rpg.service` prontos
  para uso, com variáveis de ambiente para o que costuma variar por
  host. `scripts/backup_db.py` cobre `pg_dump`/cópia de arquivo SQLite
  com poda automática por retenção, pensado para rodar via cron.
- Validado contra um Postgres real local (registro, prática nas 9
  matérias, conquista via critério JSON, chat, ranking) antes de ser
  considerado pronto para produção. Ver [DEPLOY.md](DEPLOY.md) para o
  runbook completo — o deploy num servidor real depende apenas de
  credenciais de um provedor de nuvem.

## Roadmap

- Deploy em servidor real (domínio, TLS emitido de verdade) — artefatos
  e runbook prontos em [DEPLOY.md](DEPLOY.md).
- PvP ranqueado com troféus (desenho: assíncrono por pontuação, mesmo
  desafio para os dois jogadores, comparado depois).
- Sistema de amigos: doação de itens, presença online/offline, incursão
  de masmorra em dupla sincronizada de verdade.
- Troca de senha na conta.
- Moderação de chat automática: detecção por palavras-chave e fila de
  sanção graduada (a denúncia manual e o sinalizador já existem — falta
  a parte automática).

## Como rodar localmente

```bash
# 1. Ambiente virtual
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Dependências
pip install -r requirements.txt

# 3. Variáveis de ambiente
cp .env.example .env
# edite .env e defina uma SECRET_KEY própria

# 4. Banco de dados (SQLite local por padrão) — as migrações já estão no
# repo em migrations/versions/, então é só aplicar:
mkdir -p instance
flask db upgrade
# (só rode "flask db migrate" de novo se você alterar um model)

# 5. Popular currículo/níveis/ranks/conquistas iniciais
python scripts/seed.py

# 6. Rodar o servidor
python run.py
# ou: flask --app run run --debug
```

A aplicação sobe em `http://localhost:5000`. `/health` retorna `{"status": "ok"}`.

## Testes

```bash
pytest
```

## Trocando para PostgreSQL

Defina `DATABASE_URL` (ex.: `postgresql://user:senha@localhost:5432/math_rpg`)
e `FLASK_ENV=production` no `.env` ou nas variáveis de ambiente do servidor.
Como tudo passa por SQLAlchemy/Flask-Migrate, nenhuma mudança de código é
necessária — apenas rode `flask db upgrade` apontando para o Postgres.

## Leaderboards semanais/mensais

`recompute_leaderboard()` só congela um snapshot quando é chamado — não há
scheduler embutido no processo (evita rodar em duplicidade com múltiplos
workers do Gunicorn). Aponte um agendador do sistema operacional para o
comando de CLI:

```bash
# manual / debug
flask recompute-leaderboards --scope weekly

# cron (toda segunda à meia-noite, ajuste o caminho do venv/projeto)
0 0 * * 1 cd /caminho/do/projeto && .venv/bin/flask recompute-leaderboards --scope weekly
0 0 1 * * cd /caminho/do/projeto && .venv/bin/flask recompute-leaderboards --scope monthly
```

## Estrutura de pastas

```text
app/
  auth/            cadastro, login, logout
  users/           dashboard (Salão do Herói), perfil, escolha de classe
  mathematics/     motor de questões, mapa de aventura, crônicas do reino
  progression/     XP, níveis, domínio, fila de revisão
  ranking/         leaderboard global
  achievements/    conquistas e insígnias em destaque
  chat/            chat global (HTMX + polling)
  friends/         amigos e convites de masmorra
  character/       equipamentos e espólios
  market/          loja do reino e mercado entre jogadores
  api/             endpoints internos para HTMX
  models/          um arquivo por domínio (user, mathematics, progression, chat, inventory, ...)
  services/        regras de negócio (mathematics_service, progression_service,
                   loot_service, market_service, guardians, lore, chat_service, ...)
  templates/       HTML (Jinja2)
  static/js/       módulos de batalha (battle-audio, battle-fx, battle-loot, battle-arena)
  static/images/   artes em uso (icons/subjects, ranks, achievements)
  static/assets/   pacotes de arte originais — fora do git (licença), só local
config/            classes de configuração (dev/test/produção)
migrations/        Flask-Migrate/Alembic — já commitado, só rodar `flask db upgrade`
scripts/seed.py    popula currículo, níveis, ranks, conquistas (upsert — roda de novo sem duplicar)
tests/             pytest (218 testes)
deploy/            unit systemd de exemplo para o Gunicorn
gunicorn.conf.py   config do servidor WSGI de produção
Caddyfile          proxy reverso + HTTPS automático
DEPLOY.md          runbook completo de deploy
```
