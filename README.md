# Matemática RPG — Fases 1–7 (Fundação → Expansão)

Plataforma de aprendizado de matemática com progressão inspirada em RPG
(XP, níveis, rankings, domínio, conquistas, chat). Flask app factory,
modelos do banco, autenticação, motor de questões, progressão, interface
com identidade visual em construção e chat global — tudo modular por
blueprints, como descrito no documento de especificação original.

A identidade visual ainda é parcial: personagens e fundos ilustrados
completos ainda não chegaram (só o sprite `idle`/`walk` de exemplo em
`app/static/images/characters/hero/`), mas rank/conquista/matéria já usam
ícones reais extraídos de um pacote de artes fantasy (ver Fase 5 abaixo).

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

## O que ainda não existe (pendências e próximas fases)

- Dificuldade dinâmica (a dificuldade hoje é fixa por tópico, propositalmente
  — ver seção 9 do prompt original: ajuste automático é explicitamente
  "futuro").
- Boards semanais/mensais rodando de verdade (a função existe, falta o
  agendador que a chama periodicamente).
- Personagens variados e fundos ilustrados — hoje só existe o sprite de
  exemplo idle/walk enviado na Fase 1.
- Títulos de perfil ganhos por conquista (`Profile.title` existe no modelo,
  mas nada ainda o preenche automaticamente).
- Produção de verdade (Fase 8): Postgres, Gunicorn/Caddy, rate limiting,
  logs estruturados, backup, deploy.

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
  static/images/   artes em uso (characters, icons/subjects, ranks, achievements, ui)
  static/assets/   pacotes de arte originais — fora do git (licença), só local
config/            classes de configuração (dev/test/produção)
migrations/        Flask-Migrate/Alembic — já commitado, só rodar `flask db upgrade`
scripts/seed.py    popula currículo, níveis, ranks, conquistas (upsert — roda de novo sem duplicar)
tests/             pytest (50 testes)
```

## Próximo passo recomendado

Fases 1–7 já estão cobertas — o loop completo de "responder → ganhar XP →
subir de nível → dominar ou precisar revisar → desbloquear conquista →
aparecer no ranking → conversar no chat" já funciona de ponta a ponta, com
9 tópicos de matemática diferentes. O próximo passo natural é a Fase 8
(Produção): Postgres real, Gunicorn/Caddy, rate limiting, logs
estruturados, backup e deploy — ver seção "Produção" abaixo assim que
existir. A identidade visual definitiva (personagens/fundos completos)
continua dependendo do pacote de artes chegar por inteiro.
