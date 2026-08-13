# Matemática RPG — Fases 1–8 (Fundação → Produção)

Plataforma de aprendizado de matemática com progressão inspirada em RPG
(XP, níveis, rankings, domínio, conquistas, chat). Flask app factory,
modelos do banco, autenticação, motor de questões, progressão, interface
com identidade visual em construção e chat global — tudo modular por
blueprints, como descrito no documento de especificação original.

A identidade visual ainda é parcial: só existe um personagem (o sprite
`idle`/`walk` em `app/static/images/characters/hero/`, sem poses de
ataque/dano), mas rank/conquista/matéria já usam ícones reais extraídos
de um pacote de artes fantasy (ver Fase 5 abaixo), e a tela de prática
já tem um fundo de cenário (floresta + castelo, ver "Correções e sistema
de batalha" abaixo).

## O que já existe

**Fase 1 — Fundação**
- App factory (`app/__init__.py`) com blueprints modulares por domínio
  (auth, users, mathematics, progression, ranking, achievements, chat, api).
- Todas as entidades do banco descritas na seção 16: `users`, `profiles`,
  `player_stats`, `levels`, `ranks`, `subjects`, `topics`, `questions`,
  `attempts`, `mastery`, `achievements`, `user_achievements`,
  `leaderboards`, `chat_messages`, `notifications`, `study_sessions`.
- Config com troca simples entre SQLite (dev) e PostgreSQL (produção).
- Migração inicial já gerada em `migrations/versions/`.

**Fase 2 — Usuários**
- Cadastro, login e logout funcionando de ponta a ponta.
- Dashboard e perfil, usando o sprite de exemplo (idle/walk) como avatar
  animado provisório.

**Fase 3 — Matemática**
- Motor de geração de questões (`app/services/mathematics_service.py`):
  tabuada (0–10, com variante de fator oculto em dificuldades mais altas)
  e as quatro operações fundamentais, com faixas numéricas por nível de
  dificuldade (1–5). Divisão sempre gera resultado inteiro exato.
- Fluxo de prática (`/math/praticar/<topico>`): pergunta → resposta →
  correção → próxima pergunta, via HTMX, sem recarregar a página.
- A resposta correta nunca é enviada ao cliente em texto puro — fica
  assinada e com expiração num token (`app/services/question_token.py`),
  então não é preciso gravar uma linha de `Question` para cada exercício
  gerado dinamicamente.
- Cada resposta é gravada como um `Attempt` (histórico em `/math/historico`),
  incluindo tempo de resposta calculado no servidor (não confia no
  cliente).
- Script de seed para o currículo inicial (Fundamentos → Tabuada → ... →
  Porcentagem), níveis, ranks e conquistas.
- Testes automatizados com pytest (20 testes: geração de questões,
  cadastro/login, fluxo completo de prática, rejeição de token adulterado).

**Fase 4 — Progressão**
- Serviço central de XP/domínio (`app/services/progression_service.py`),
  chamado uma única vez logo após cada `Attempt` ser salvo — nenhuma outra
  parte do código sabe (nem precisa saber) que XP ou domínio existem.
- XP por acerto, escalado pela dificuldade (1–5); erro não dá XP negativo,
  só não dá XP.
- Subida de nível e troca de rank calculadas a partir da tabela `Level`/
  `Rank` (dados, não código — dá pra reequilibrar a curva sem deploy).
- Domínio por (usuário, tópico) via média móvel exponencial, ponderada
  pela dificuldade da questão, com **decaimento por retenção**: ficar
  muitos dias sem praticar um tópico reduz o domínio mesmo sem erros
  novos — é isso que alimenta a fila de revisão da seção 4.
- Fila de revisão (`/progressao/revisao`) lista tópicos com
  `Mastery.needs_review = true`.
- Conquistas com critério declarativo em JSON (`Achievement.criteria`),
  checadas a cada resposta; desbloqueio gera `UserAchievement` +
  `Notification`.
- Ranking global (`/ranking`) — leitura direta de `PlayerStats` ordenado
  por XP. `LeaderboardEntry` e `ranking_service.recompute_leaderboard()`
  ficam prontos para boards semanais/mensais assim que houver um job
  agendado para rodá-los periodicamente.
- Feedback de XP/level-up/conquista aparece direto na tela de prática.

**Fase 5 — Interface**
- Efeitos visuais (`app/static/css/effects.css`) animados via CSS puro a
  partir de spritesheets em grade — acerto, erro, level-up, conquista
  desbloqueada e um spinner de carregamento, todos disparados na tela de
  prática sem nenhuma dependência de JS externa.
- Badges de rank (7 tiers) e de conquista com fallback em CSS quando não
  há arte (`app/templates/_macros.html`), e ícones reais extraídos de um
  pacote de ícones fantasy para ranks, conquistas e as 8 matérias do
  currículo — tudo ligado via `Rank.icon_key` / `Achievement.icon_key` /
  `Subject.icon_key`, então trocar a arte no futuro é só atualizar esses
  campos (via `scripts/seed.py`), sem tocar em template.
- Atmosfera visual (gradiente sutil no fundo) mantendo a paleta provisória
  — a paleta em si só será trocada quando o pacote de personagens/fundos
  completo chegar.
- Pacotes de arte originais ficam fora do repositório (`app/static/assets/`,
  gitignored) por licença — só as artes já recortadas e em uso vivem em
  `app/static/images/`.

**Fase 6 — Social**
- Chat global (`/chat/`) via HTMX: histórico renderizado no servidor,
  polling a cada 4s para novas mensagens, envio sem recarregar a página.
- `app/services/chat_service.py`: cooldown de 3s entre mensagens, bloqueio
  de mensagem idêntica repetida em até 60s, e uma heurística leve que
  marca (`is_flagged`) mensagens suspeitas (CAPS LOCK longo, caractere
  repetido) sem nunca bloquear o envio — fica visível para moderação
  futura em vez de ser censurada silenciosamente.
- `ChatMessage.room` já aceita qualquer string — salas, DMs e grupos
  podem ser adicionados depois sem mudança de schema.

**Fase 7 — Expansão**
- Cinco novos módulos no motor de questões (`app/services/mathematics_service.py`),
  seguindo o mesmo padrão de gerador-por-slug das Fases 3/4: Potenciação
  (básica + propriedades: produto, quociente e potência de potência),
  Radiciação (raiz quadrada e cúbica, sempre resultado exato), Frações
  (simplificação e as quatro operações, via `fractions.Fraction` — sem
  erro de ponto flutuante), Números Decimais (leitura e operações) e
  Porcentagem (cálculo direto e inverso).
- `_normalize()` em `app/mathematics/routes.py` ganhou suporte a vírgula
  decimal (`0,3` == `0.3`, convenção brasileira) e a floats de valor
  inteiro (`3.0` == `3`), além do que já existia para frações como
  string (`5/6`). Sem isso, um aluno digitando do jeito natural em
  português teria a resposta certa marcada como errada.
- Um novo critério declarativo de conquista, `attempts_correct_in_subject`,
  permite "Mestre de X" por matéria sem mudar o motor de conquistas —
  seis conquistas novas usam isso (uma por matéria nova) mais uma usando
  `best_streak`, que já existia no código mas nunca tinha sido usada.
- A arquitetura aguentou a expansão sem refatoração: adicionar os 5
  módulos foi só registrar novas entradas no dicionário de geradores —
  nenhuma rota, model ou template precisou mudar.

**Pendências resolvidas (do fim da Fase 4)**
- Dificuldade dinâmica de verdade: `progression_service.get_effective_difficulty()`
  lê o `Mastery` do usuário naquele tópico (score da média móvel + streak
  atual) e ajusta a dificuldade servida pra cima ou pra baixo dentro da
  faixa 1..5 do tópico — exige pelo menos 3 tentativas antes de reagir,
  pra um acerto/erro isolado não fazer a dificuldade oscilar. Os
  geradores em si continuam sem acesso a banco, por design; quem decide
  a dificuldade efetiva é a camada de rotas.
- Boards semanais/mensais rodando de verdade: `flask recompute-leaderboards
  --scope weekly|monthly|global` — comando de CLI pensado pra ser chamado
  por um agendador externo (cron, systemd timer, Task Scheduler), não por
  um scheduler dentro do processo (que duplicaria a execução com múltiplos
  workers do Gunicorn).
- Títulos de perfil por conquista: toda vez que uma conquista nova é
  desbloqueada, `Profile.title` passa a mostrar o nome dela automaticamente
  (a mais recente da leva, se mais de uma desbloquear no mesmo instante).

**Fase 8 — Produção**
- Rate limiting explícito (Flask-Limiter): 10/hora em cadastro, 10/min em
  login (força bruta), 120/min em responder questão, 200/hora como teto
  geral — desligado em teste (`RATELIMIT_ENABLED=False`) porque a suíte
  bate nas rotas bem mais que um usuário real bateria.
- Logs estruturados (`app/logging_config.py`): JSON por linha em stdout
  quando `DEBUG=False` (o formato que qualquer agregador de log de nuvem
  já sabe ler), texto legível em dev/teste. Todo request loga
  method/path/status/user_id; exceções não tratadas entram com traceback
  completo no campo `exception`.
- Páginas de erro próprias (404/500) sem vazar stack trace — a de 500
  propositalmente *não* estende `base.html`, porque a navbar lê
  `current_user` (consulta ao banco) e um 500 pode ser justamente o banco
  fora do ar.
- Cookies de sessão com `HttpOnly`/`SameSite=Lax` sempre, e `Secure` em
  produção (não em dev, que roda em HTTP puro); headers
  `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` em toda
  resposta. HSTS fica por conta do Caddy, que já adiciona automaticamente.
- `gunicorn.conf.py`, `Caddyfile` e `deploy/math-rpg.service` prontos pra
  uso — variáveis de ambiente pra tudo que costuma variar por host.
- `scripts/backup_db.py`: `pg_dump` (Postgres) ou cópia de arquivo
  (SQLite), gzip, poda automática por retenção — pensado pra rodar via
  cron, mesma lógica de "nada agenda a si mesmo dentro do processo" do
  `recompute-leaderboards`.
- **Validado de verdade, não só no papel**: rodei `flask db upgrade` e um
  smoke test completo (registro, os 9 tópicos de matemática, conquista via
  critério JSON, chat, ranking) contra um Postgres 18 local real — isso
  achou e corrigiu um bug que quebraria toda e qualquer requisição em
  produção (`RATELIMIT_DEFAULT` como lista em vez de string). Ver
  [DEPLOY.md](DEPLOY.md) para o runbook completo — deploy num servidor de
  verdade não foi feito por não haver credenciais de nuvem disponíveis
  neste ambiente de desenvolvimento.

**Correções pós-Fase 8**
- Dois tópicos de Fundamentos (`numeros-e-contagem`, `comparacao-de-quantidades`)
  estavam no currículo semeado (`scripts/seed.py`) mas sem gerador
  registrado em `mathematics_service.py` — toda tentativa de praticar
  esses tópicos caía no `except ValueError: abort(404)` da rota. Ambos
  geram questões numéricas simples (contar símbolos, comparar dois
  números), compatíveis com o campo de resposta `inputmode="numeric"`
  existente, sem exigir nenhum símbolo novo de digitação.
- **Mentor sidekick**: uma curiosidade matemática ou regra do jogo por
  sessão de prática (`app/services/mentor_tips.py`, lista curada,
  `random.choice`), mostrada na tela de história antes da batalha.

**Remodelagem visual completa (Tailwind + tema medieval em todo o site)**
O projeto passou por duas gerações de identidade visual antes desta. A
primeira era pixel art (Sprout Lands + sprites de herói reconstruídos de
`.aseprite` — `scripts/rebuild_hero_sprites.py` ainda está no repo,
mas não é mais usado). A segunda foi um sistema de batalha animado com
sprites reais (soldier vs. orc) e parallax em camadas, que foi
**removido a pedido do usuário** para priorizar estabilidade. A versão
atual é uma terceira geração: o usuário forneceu um template HTML
(Tailwind CSS via CDN + Google Fonts MedievalSharp/Cinzel + FontAwesome)
para a tela de login, e pediu para essa identidade — paleta
parchment/blood/gold/mystic, ícones FontAwesome em vez de sprites —
virar o padrão do site inteiro:
- `base.html` agora carrega a mesma stack Tailwind/fontes/ícones do
  login e define a navbar, os flashes e o rodapé de "voltar" que toda
  página autenticada herda. `ui.css` e `effects.css` foram removidos —
  não sobrou nenhuma regra CSS própria no projeto, é tudo classes
  utilitárias Tailwind mais um punhado de `@keyframes` locais no bloco
  `extra_head` da tela de batalha.
- Rank e conquistas (`_macros.html`) não usam mais imagem — são
  emblemas desenhados com Tailwind + `<i>` do FontAwesome, então não
  dependem mais de nenhum `icon_key` apontando pra um arquivo.
- Os assets órfãos da geração anterior (`images/characters/`,
  `images/backgrounds/`, `images/battle/`, `images/ui/*`, a fonte
  pixelada) foram removidos do repo — nada mais os referencia.
- `register.html` foi redesenhado no mesmo estilo de pergaminho da
  tela de login (mesmo `parchment-bg`, mesmos campos), então login e
  cadastro finalmente compartilham a mesma cara.

**Sistema de batalha — reconstruído com questões e XP reais**
A tela de prática (`mathematics/practice.html`) agora é uma arena de
batalha de verdade, adaptada de um template de batalha fornecido pelo
usuário: tela de história (nome do tópico + dica do mentor) → arena
com barra de vida do "Aprendiz" vs. o "Guardião" → cada resposta
correta ou errada dispara uma animação (golpe do herói, brilho no
Guardião, ou um flash sutil na borda da arena) e ajusta as barras de
HP no cliente. Nada disso é cosmético por cima de dados falsos: o
loop de pergunta/resposta é o mesmo endpoint HTMX de sempre
(`/math/praticar/<slug>/questao` e `/responder`), então toda resposta
continua gerando XP, atualizando maestria e desbloqueando conquistas
de verdade — a "barra de vida" é só uma forma mais game-like de
mostrar acertos/erros consecutivos, sem estado novo no backend.
Vitória e derrota abrem um "portal" (`gate-rift`) sutil no estilo dos
portões de Solo Leveling — uma fenda estreita que brilha, não um
círculo girando cobrindo a tela inteira. A única exceção deliberada é
o portal de ressurgir: a pedido do usuário, esse é o "grande momento"
— uma onda vermelha (`clip-path: circle()` animado) engole a arena
inteira antes de revelar a batalha resetada.

## O que ainda não existe

- O deploy em si (servidor real, domínio, TLS emitido de verdade) — os
  artefatos e o runbook estão prontos em [DEPLOY.md](DEPLOY.md), falta
  alguém com acesso a um provedor de nuvem executar os passos.
- Os links decorativos "O Códice" e "Salão dos Heróis" na navbar da
  tela de login apontam para `auth.login` como placeholder — não
  existem rotas reais para esses conceitos ainda.

## Instalação local

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

## Rodando os testes

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
workers do Gunicorn). Aponte um agendador do sistema operacional pro
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
  users/           dashboard, perfil
  mathematics/     motor de questões (9 tópicos: tabuada, 4 operações + potenciação,
                   radiciação, frações, decimais, porcentagem)
  progression/     XP, níveis, domínio, fila de revisão
  ranking/         leaderboard global
  achievements/    conquistas
  chat/            chat global (HTMX + polling)
  api/             endpoints internos para HTMX/Alpine.js
  models/          um arquivo por domínio (user, mathematics, progression, chat, ...)
  services/        regras de negócio (mathematics_service, progression_service,
                   chat_service, ranking_service, question_token)
  repositories/    acesso a dados mais complexo, quando necessário
  templates/       HTML (Jinja2)
  static/css/      effects.css (VFX) e ui.css (badges, chat, atmosfera)
  static/images/   artes em uso (characters, icons/subjects, ranks, achievements, ui, backgrounds)
  static/assets/   pacotes de arte originais — fora do git (licença), só local
config/            classes de configuração (dev/test/produção)
migrations/        Flask-Migrate/Alembic — já commitado, só rodar `flask db upgrade`
scripts/seed.py    popula currículo, níveis, ranks, conquistas (upsert — roda de novo sem duplicar)
scripts/rebuild_hero_sprites.py  regenera as spritesheets do herói a partir dos .aseprite fonte
tests/             pytest (79 testes)
deploy/            unit systemd de exemplo para o Gunicorn
gunicorn.conf.py   config do servidor WSGI de produção
Caddyfile          proxy reverso + HTTPS automático
DEPLOY.md          runbook completo de deploy (ver Fase 8)
```

## Próximo passo recomendado

Fases 1–8 já estão cobertas no código: o loop completo de "responder →
ganhar XP → subir de nível → dominar ou precisar revisar → desbloquear
conquista → aparecer no ranking → conversar no chat" funciona de ponta a
ponta com todos os 26 tópicos praticáveis do currículo (4 operações
fundamentais + 10 tabuadas + 2 de Fundamentos + 10 das Fases 7),
sistema de batalha e mentor sidekick incluídos, e a aplicação está pronta
pra produção (Postgres validado, rate limiting, logs estruturados,
backup, Gunicorn/Caddy) — falta só alguém com acesso a um provedor de
nuvem seguir o runbook em [DEPLOY.md](DEPLOY.md) e efetivamente publicar.
A identidade visual definitiva (poses de ataque/dano, um segundo
personagem de verdade) continua dependendo de um pacote de artes com
personagens chegar.
