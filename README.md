# Matemática RPG — Fases 1–4 (Fundação, Usuários, Matemática, Progressão)

Plataforma de aprendizado de matemática com progressão inspirada em RPG
(XP, níveis, rankings, domínio, conquistas). Este é o esqueleto inicial do
projeto: Flask app factory, modelos do banco, autenticação básica e a
estrutura de pastas modular descrita no documento de especificação.

O pacote de artes de exemplo (`idle`/`walk`) enviado já está posicionado em
`app/static/images/characters/hero/` e usado como identidade visual
**provisória** no dashboard/perfil, até o pacote completo de artes ser
analisado (ver seção 13 do prompt original).

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

## O que ainda não existe (próximas fases)

- Dificuldade dinâmica (a dificuldade hoje é fixa por tópico, propositalmente
  — ver seção 9 do prompt original: ajuste automático é explicitamente
  "futuro").
- Boards semanais/mensais rodando de verdade (a função existe, falta o
  agendador que a chama periodicamente).
- Chat em tempo real (Fase 6).
- Identidade visual definitiva a partir do pacote completo de artes (Fase 5)
  — hoje usa só o sprite de exemplo enviado.
- Títulos de perfil ganhos por conquista (`Profile.title` existe no modelo,
  mas nada ainda o preenche automaticamente).

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

# 4. Banco de dados (SQLite local por padrão)
mkdir -p instance
flask db init          # apenas na primeira vez
flask db migrate -m "initial schema"
flask db upgrade

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
  mathematics/     motor de questões (stub — Fase 3)
  progression/     XP, níveis, domínio (stub — Fase 4)
  ranking/         leaderboards (stub — Fase 4)
  achievements/    conquistas (stub — Fase 4)
  chat/            chat entre jogadores (stub — Fase 6)
  api/             endpoints internos para HTMX/Alpine.js
  models/          um arquivo por domínio (user, mathematics, progression, ...)
  services/        regras de negócio (vazio por enquanto — ver Fase 3/4)
  repositories/    acesso a dados mais complexo, quando necessário
  templates/        HTML (Jinja2)
  static/images/    artes do jogo (characters, backgrounds, icons, ranks, badges, achievements, ui)
config/            classes de configuração (dev/test/produção)
migrations/        gerado por `flask db init`
scripts/seed.py    popula currículo, níveis, ranks e conquistas iniciais
tests/             pytest
```

## Próximo passo recomendado

Fases 1–4 já estão cobertas — o loop completo de "responder → ganhar XP →
subir de nível → dominar ou precisar revisar → desbloquear conquista →
aparecer no ranking" já funciona de ponta a ponta. O próximo passo natural
é a Fase 5 (Interface): analisar o pacote completo de artes quando ele
chegar (hoje só há o sprite de exemplo idle/walk) e substituir a paleta
provisória em `app/templates/base.html` pela identidade visual definitiva,
sem precisar tocar em lógica de negócio.
