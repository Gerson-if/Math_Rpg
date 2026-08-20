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
  mesmo tópico dentro da janela do convite. Deliberadamente não
  sincronizado — ver Duelos abaixo para a exceção real-time do app.

### Duelos em tempo real

- Único recurso do app com transporte ao vivo — Flask-SocketIO por trás
  de tudo o mais (que continua HTTP/HTMX comum). Um amigo aceito pode
  desafiar o outro para um duelo 1x1 num tópico à escolha; aceitar abre
  uma arena dedicada (`/duelo/<id>`) onde os dois veem a **mesma**
  pergunta ao mesmo tempo — quem responde certo primeiro causa dano no
  oponente (100 HP cada, -20 por rodada vencida).
- Como em qualquer outro lugar do app, quem decide a resposta certa e
  aplica o dano é o servidor (`app/services/duel_service.py`), nunca o
  cliente — o Socket.IO é só o transporte que avisa os dois jogadores na
  hora, no lugar do polling HTMX usado no chat.
- Emotes rápidos (👋😂🔥😅😤🤝) podem ser trocados durante o duelo,
  aparecendo como balões flutuantes sobre o avatar de quem enviou.
- Resultado registrado via `Notification` para os dois jogadores
  (`duel_result`), do mesmo jeito que qualquer outra notificação do app.

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
  host. `scripts/backup_db.py`/`restore_db.py` cobrem `pg_dump`/cópia de
  arquivo SQLite com poda automática por retenção e restauração segura
  (sempre snapshotando o banco atual antes de sobrescrever).
- `deploy/install.sh` instala tudo isso num Ubuntu/Debian limpo (VM ou
  VPS): pacotes, banco, Caddy com HTTPS automático (Let's Encrypt/
  ZeroSSL com domínio, certificado autoassinado só com IP), systemd,
  firewall e backups/leaderboards agendados — e depois vira uma
  ferramenta de gerência com atualização segura (backup + rollback
  automático se algo falhar), status dos serviços, reinício,
  backup/restore e migração completa para outro servidor sob demanda.
  Etapas de rede (apt, repositórios do Caddy/Node.js, git, pip, npm)
  tentam de novo automaticamente antes de desistir, com diagnóstico
  específico (DNS, timeout, chave GPG, etc.) em vez de uma falha
  genérica; o instalador também detecta de antemão containers de
  desenvolvimento (Codespaces/Dev Containers/Docker) onde ele não
  funciona. Ver [DEPLOY.md](DEPLOY.md).
- Validado contra um Postgres real local (registro, prática nas 9
  matérias, conquista via critério JSON, chat, ranking) antes de ser
  considerado pronto para produção. O deploy num servidor real depende
  apenas de credenciais de um provedor de nuvem.
- **Sem CDN em produção** — Tailwind CSS, fontes (MedievalSharp/Cinzel),
  FontAwesome e htmx eram carregados de `cdn.tailwindcss.com`,
  `fonts.googleapis.com`, `cdnjs.cloudflare.com` e `unpkg.com` a cada
  visita; agora são compilados/copiados localmente em build-time
  (`npm run build`, ver "Assets locais" abaixo) e servidos como qualquer
  outro arquivo estático do app — nenhuma requisição a um CDN acontece em
  runtime, e a aplicação nunca fica de pé refém da disponibilidade de um
  serviço de terceiro. Os dois padrões de textura que vinham de
  `transparenttextures.com` também foram trocados por ruído SVG
  autocontido (`data:` URI, sem arquivo nem requisição nenhuma).

## Roadmap

- Publicar de fato num servidor real (falta apenas as credenciais de um
  provedor de nuvem) — artefatos, instalador automatizado e runbook
  prontos em [DEPLOY.md](DEPLOY.md).
- Duelos ranqueados com troféus/placar histórico — os duelos em si já
  existem (ver acima); falta a camada de ranking sobre os resultados.
- Sistema de amigos: doação de itens, presença online/offline, incursão
  de masmorra em dupla sincronizada de verdade (o transporte real-time
  dos duelos poderia ser reaproveitado aqui no futuro).
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

# 4. Assets do frontend (Tailwind CSS, fontes, FontAwesome, htmx) — só
# precisa do Node.js instalado; nada disso roda em produção, é só
# compilado/copiado uma vez aqui e servido como arquivo estático.
npm install
npm run build

# 5. Banco de dados (SQLite local por padrão) — as migrações já estão no
# repo em migrations/versions/, então é só aplicar:
mkdir -p instance
flask db upgrade
# (só rode "flask db migrate" de novo se você alterar um model)

# 6. Popular currículo/níveis/ranks/conquistas iniciais
python scripts/seed.py

# 7. Rodar o servidor
python run.py
# ou: flask --app run run --debug
```

A aplicação sobe em `http://localhost:5000`. `/health` retorna `{"status": "ok"}`.

### Assets locais (sem CDN)

O CSS (Tailwind), as fontes (MedievalSharp/Cinzel), o FontAwesome e o
htmx eram carregados de CDNs externos a cada requisição; agora são
compilados/copiados uma vez para `app/static/` e servidos localmente —
ver `package.json`, `tailwind.config.js`, `assets/css/input.css` e
`assets/copy-vendor-assets.js`. Nada disso é commitado no git
(`app/static/vendor/` e `app/static/css/tailwind.css` estão no
`.gitignore` — são build output, não código-fonte), então **é preciso
rodar `npm install && npm run build` antes da primeira vez que subir o
servidor**, e de novo sempre que:

- mudar alguma classe Tailwind num template (`npm run watch:css` recompila
  o CSS automaticamente a cada salvamento, útil durante o desenvolvimento);
- atualizar `package.json` (nova versão de alguma dependência de frontend).

`npm run build` roda os dois passos de uma vez:

```bash
npm run copy:vendor   # copia htmx/FontAwesome/fontes de node_modules para app/static/vendor/
npm run build:css     # compila assets/css/input.css -> app/static/css/tailwind.css (minificado)
```

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
  duels/           duelos 1x1 em tempo real (rotas HTTP + handlers Socket.IO)
  api/             endpoints internos para HTMX
  models/          um arquivo por domínio (user, mathematics, progression, chat, inventory, ...)
  services/        regras de negócio (mathematics_service, progression_service,
                   loot_service, market_service, guardians, lore, chat_service, ...)
  templates/       HTML (Jinja2)
  static/js/       módulos de batalha (battle-audio, battle-fx, battle-loot, battle-arena)
  static/images/   artes em uso (icons/subjects, ranks, achievements)
  static/assets/   pacotes de arte originais — fora do git (licença), só local
  static/css/      Tailwind compilado (tailwind.css) — gerado por `npm run build`, fora do git
  static/vendor/   htmx/FontAwesome/fontes copiados de node_modules — gerado por `npm run build`, fora do git
assets/            fonte do pipeline de build do frontend (input.css, copy-vendor-assets.js)
config/            classes de configuração (dev/test/produção)
migrations/        Flask-Migrate/Alembic — já commitado, só rodar `flask db upgrade`
scripts/seed.py    popula currículo, níveis, ranks, conquistas (upsert — roda de novo sem duplicar)
scripts/backup_db.py / restore_db.py   backup e restauração do banco (Postgres/SQLite)
tests/             pytest
package.json, tailwind.config.js   pipeline de build do frontend (Tailwind CSS local, sem CDN)
deploy/install.sh  instalador + gerenciador (instalar, atualizar com segurança,
                   status, reiniciar, backup/restore) para VM/VPS Ubuntu/Debian
deploy/*.service, *.timer   unidades systemd (app, backup diário, leaderboards)
gunicorn.conf.py   config do servidor WSGI de produção
Caddyfile          proxy reverso + HTTPS automático
DEPLOY.md          runbook completo de deploy
```

## Licença

Distribuído sob a licença [MIT](LICENSE).
