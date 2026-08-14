# Matemática RPG

Plataforma de aprendizado de matemática com progressão inspirada em RPG
(XP, níveis, rankings, domínio, conquistas, batalhas, equipamentos, chat).
Flask app factory, modelos do banco, autenticação, motor de questões,
progressão, identidade visual medieval e chat global — tudo modular por
blueprints.

A identidade visual é Tailwind CSS + FontAwesome em tema medieval (ver
"Remodelagem visual completa" mais abaixo) — não há mais sprites de
personagem; rank, conquista e matéria usam ícones reais em pixel art
extraídos de um pacote de artes fantasy, e o avatar do jogador é um
ícone FontAwesome escolhido entre um conjunto curado (ver "Perfil
editável e avatar" mais abaixo).

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

**Ícones reais de volta, currículo e conteúdo mais espertos**
- `_macros.html` (rank/conquista) e a tela de Tópicos voltaram a mostrar
  a arte pixel art real (`images/icons/subjects/`, `images/ranks/`,
  `images/achievements/` — pacote "Raven Fantasy Icons", ver
  `images/icons/CREDITS.txt`) dentro dos mesmos emblemas com borda
  dourada do tema, em vez do ícone FontAwesome genérico — com fallback
  automático para FontAwesome/iniciais quando um rank/conquista não tem
  `icon_key`, então nada quebra se a arte um dia sumir de novo.
- **Tabuada Mista**: novo tópico (`tabuada-mista`) que sorteia a base
  entre 1 e 10 a cada pergunta — um teste de domínio completo depois de
  praticar cada tabuada individualmente. Reaproveita o gerador de
  `tabuada-do-N` internamente, então herda a variante de fator oculto em
  dificuldades altas de graça.
- Banco de dicas do mentor (`app/services/mentor_tips.py`) ganhou ~20
  curiosidades novas baseadas em fatos reais de história da matemática
  (numeração babilônica em base 60, papiro de Rhind, origem de
  "álgebra"/"algoritmo" em Al-Khwarizmi, o zero na Índia, Fibonacci e o
  Liber Abaci, Eratóstenes, número de ouro, etc.) em vez de só as ~8
  curiosidades genéricas anteriores.
- Mais conquistas em `scripts/seed.py`: mestre dos 3 assuntos que
  faltavam (Fundamentos, Tabuada, Operações Fundamentais), marcos de
  volume (500/1000 questões, 30 dias de prática, sequência de 25), e um
  critério novo (`level_reached`) para conquistas por nível alcançado
  (10 e 25) — `progression_service._meets_criteria` ganhou esse branch.
- Ranking (`ranking/index.html`) redesenhado num estilo "liga" à Clash
  of Clans: pódio com os 3 primeiros colocados (medalha
  ouro/prata/bronze, card do 1º elevado), badge de rank/liga em cada
  linha da tabela abaixo.

**Perfil editável, avatar e amigos**
- `/profile/editar`: nome de exibição e bio editáveis, mais um seletor
  de avatar — deliberadamente um conjunto **curado de 12 ícones
  FontAwesome** (`app/users/forms.py`), não upload de imagem livre. Sem
  pipeline de upload/moderação para manter, e nenhuma forma de um
  jogador colocar uma imagem que viole os termos de uso na tela de
  outra pessoa. O avatar escolhido aparece no dashboard, perfil, arena
  de batalha, ranking e no chat (quando a linha não tem badge de rank).
- Sistema de amigos (`app/friends/`, modelo `Friendship`): pedido por
  nome de usuário, aceitar/recusar, lista de amigos, desfazer amizade.
  Contador de pendências (pedidos + convites de masmorra) aparece como
  badge vermelho no "Amigos" da navbar via um `context_processor`.
- **Convite de masmorra (co-op)**: convide um amigo aceito para ajudar
  num tópico (`DungeonInvite`). Isso **não é** uma batalha multiplayer
  sincronizada — o app não tem transporte realtime (WebSocket/SSE), e
  fingir uma barra de vida compartilhada sobre duas sessões HTTP
  independentes seria enganoso. O que existe de verdade: o aliado
  aparece ao lado do herói na arena ("Lutando ao lado de...") e ambos
  ganham um bônus de XP pequeno e verificado no servidor
  (`dungeon_service.active_ally`) enquanto praticam o mesmo tópico
  dentro da janela do convite aceito (30 min) — decisão deliberada de
  escopo, documentada aqui para quem quiser evoluir para algo
  sincronizado de verdade no futuro.

**Sistema de batalha rico: combo, crítico, fúria, fases do chefe e loot/equipamento**
A pedido do usuário, o arena de batalha foi reconstruído a partir de um
segundo template de referência bem mais elaborado que o anterior
(combo, crítico, fúria/ultimate, fases do chefe, partículas/projéteis em
canvas, áudio 100% procedural via Web Audio API, e um sistema de loot com
4 raridades e 6 slots de equipamento). A pergunta continua 100% real
(`mathematics_service`/HTMX, o mesmo de sempre) — o que mudou foi a
apresentação por cima dela:
- **Combo, crítico visual, fúria/ultimate e fase do chefe são cosméticos**
  — não alteram XP real, só amplificam a mesma barra de vida cosmética
  que já existia (decisão deliberada, ver `app/services/loot_service.py`,
  para não abrir uma superfície de "otimizar equipamento pra grindar XP"
  num app educacional).
- **O crítico que decide se cai loot é sorteado no servidor**
  (`answer_question`, usando os buffs reais do equipamento via
  `loot_service.compute_buffs`) — o cliente só anima o que o servidor já
  decidiu, nunca inventa uma recompensa sozinho. Loot garantido ao
  derrotar o chefe passa por um endpoint próprio
  (`POST /praticar/<slug>/vitoria`), rate-limited e com uma checagem
  proporcional de integridade (existe um `Attempt` correto recente).
- **Equipamento é escolhido antes da batalha**, em páginas reais
  (`/personagem/equipamentos`, `/personagem/espolios`) — 6 slots (arma,
  anel, amuleto, armadura, capacete, botas), 4 raridades, 6 passivos.
  Consumíveis (poção/pergaminho) continuam por-batalha, não persistentes,
  numa tela cheia dedicada dentro do arena — nunca um modal pequeno.
- **A batalha agora é uma tela exclusiva de verdade**: `#battle-fullscreen`
  cobre todo o viewport (navbar incluso), com as invocações de início
  (`showInvocation`) e renascimento (`showRebirth`) portadas quase
  literalmente do template de referência, barras de HP com "afterimage"
  (ghost bar) + texto numérico, e filtros de morte (dessintegração do
  chefe, dessaturação do jogador) — escopados a `#arena-content` para não
  escurecer a própria tela de derrota por cima.
- JS extraído para `app/static/js/` (primeira vez que o projeto tem JS em
  arquivo próprio) em módulos: `battle-audio.js`, `battle-fx.js`,
  `battle-loot.js`, `battle-arena.js` (orquestrador).
- Novos jogadores já entram no nível 1 e no rank mais baixo da liga
  desde o cadastro (antes ficavam com "-" até a primeira resposta), e o
  ranking ganhou uma trilha visual com todos os ranks — não só o atual.

**Guardiões por matéria, pré-requisitos, mapa de aventura e crônicas do reino**
- Cada matéria agora tem seu próprio guardião — nome, ícone e cor
  distintos (`app/services/guardians.py`) — em vez do mesmo dragão
  genérico em toda batalha. Fallback automático para qualquer matéria
  fora da lista, então nada quebra se o currículo crescer sem atualizar
  o arquivo.
- `Topic.prerequisite_slugs` (campo que já existia no modelo, nunca
  usado) agora é populado pelo `scripts/seed.py` — cada tópico recomenda
  o anterior na mesma matéria — e lido por
  `progression_service.unmet_prerequisites`. É uma **recomendação, não
  um bloqueio**: o tópico continua 100% acessível, só aparece um aviso
  ("recomendado praticar primeiro: X") quando a maestria no
  pré-requisito ainda está abaixo de 50%.
- A tela de Tópicos virou o **Mapa de Aventura** (`/math/`, renomeado em
  toda a navegação): cada matéria é uma trilha de nós numerados ligados
  por um caminho, terminando no guardião daquela matéria — não mais uma
  lista de links empilhados.
- **Crônicas do Reino** (`/math/cronicas`): um parágrafo curto de lore
  por matéria (`app/services/lore.py`), amarrando o currículo à mesma
  ambientação "Ruínas de Arith" já estabelecida na abertura da batalha.
  Cada crônica é "descoberta" assim que o jogador responde qualquer
  questão daquela matéria — antes disso aparece como "???".
- A suíte de testes ganhou uma fixture `autouse` que fixa a semente do
  `random` antes de cada teste (`tests/conftest.py`) — o módulo `random`
  é global ao processo, então quantas vezes um teste anterior sorteou
  algo (pergunta, crítico, raridade de loot) mudava o que o próximo
  teste sorteava, causando falhas intermitentes dependentes da ordem de
  execução. Isso também expôs um bug real: um crítico suprimia a
  palavra "Correto!" do feedback (substituída por "Golpe Crítico!"),
  quebrando a confirmação de acerto — corrigido.

### Sistema de classes de personagem

- `app/services/classes.py`: 5 classes (Guerreiro/Mago/Arqueiro/
  Clérigo/Ladino), cada uma associada a uma categoria de bônus cosmético
  (dano/crítico/fúria/combo/vida/vampirismo — as mesmas do
  `loot_service`). O jogador escolhe livremente na primeira vez; depois
  só pode trocar (mesma classe ou outra) quando um novo nível de
  habilidade desbloqueia (nível 10 "Adepto", nível 25 "Mestre" — mesmos
  marcos das conquistas "Aventureiro Experiente"/"Herói do Reino"),
  ganhando uma habilidade nova nomeada por classe+tier a cada troca.
  `Profile.character_class`/`class_tier_claimed` persistem a escolha.
- `loot_service.compute_buffs` agora soma o bônus da classe ao bônus do
  equipamento num único dict — mesma filosofia cosmética de sempre:
  afeta a apresentação da batalha (chance de crítico real incluída,
  calculada no servidor) e nunca XP/maestria reais.
- `GET/POST /profile/classe`: tela dedicada de escolha, com elegibilidade
  validada no servidor (`classes.can_choose_class`) mesmo que a UI tente
  contornar. O perfil (`/profile`) mostra a classe/habilidade atuais; o
  painel do Salão do Herói mostra um aviso quando há escolha ou troca
  disponível.

### Ajustes na tela de batalha (alertas flutuantes + atalho de inventário)

- Pequenos banners flutuantes ("⚡ Fúria pronta!", "🔥 Combo x5!",
  "💥 Golpe Crítico!", "☄️ Fúria Arcana Suprema!", uso de poção/
  pergaminho) aparecem sobre a arena e somem sozinhos — `position:
  absolute` com `pointer-events: none`, nunca deslocam ou redimensionam
  o layout ao redor.
- Um atalho compacto "Inventário" voltou a aparecer logo abaixo da barra
  de fúria (além do link "Consumíveis" no rodapé da arena), abrindo a
  mesma tela cheia de consumíveis.

### Correções de legibilidade na batalha (balões, dano flutuante, loot)

- `needs_review` no feedback passou a refletir só a **transição** para
  "domínio caiu", não o estado bruto — antes continuava "notificando"
  em toda resposta certa enquanto a maestria seguia abaixo do limiar.
  Ganhou o contraponto "Domínio recuperado!" quando ela volta a cruzar
  a linha.
- Todos os balões de batalha (acerto/erro/conquista/domínio) seguem o
  mesmo modelo em negrito/alto-contraste da conquista.
- `loot-toast-container` (item ganho) e os balões de fala agora vivem
  dentro da fileira do chefe, espelhados um de cada lado — antes o
  loot-toast ficava preso ao topo da arena inteira, sobre a barra de
  vida do chefe.
- Números de dano flutuantes nascem deslocados do centro do alvo (não
  mais exatamente sobre o sprite) e ganham contorno mais grosso — cor
  de acerto podia coincidir com a cor do próprio guardião.
- Vitória espera o jogador clicar em "Continuar" (com transição em
  tela cheia igual à invocação inicial) antes de revelar a tela de
  vitória, em vez de sumir sozinha em ~3s sem dar tempo de ler a
  crônica revelada.

### Salão do Herói reformulado, páginas públicas ativadas, Mapa ilustrado

- Salão do Herói: remove atalhos duplicados da navbar, adiciona barra
  de progresso até o próximo nível, fila de revisão, precisão, dica do
  mentor rotativa e galeria de heróis/crônicas descobertas.
- "O Códice" e "Salão dos Heróis" na tela de login agora são páginas
  públicas de verdade (sem login): a primeira explica as mecânicas do
  jogo, a segunda mostra os 10 melhores jogadores e qual guardião cada
  um está enfrentando (se ativo nos últimos 30 min).
- **Mapa de Aventura reformulado** como um mapa ilustrado de pergaminho
  com uma trilha sinuosa única ligando todas as matérias (marco +
  ícone do guardião por matéria, pontos de tópico, bússola, legenda) —
  no lugar da lista de cartões empilhados anterior.
- **Nova matéria: Álgebra** ("O Grande Castelo das Incógnitas") — dois
  tópicos (equações do 1º grau simples e com a incógnita dos dois
  lados). É conteúdo avançado, recomendado só depois de Porcentagem
  (`scripts/seed.py`'s `entry_prereqs`), mas nunca bloqueado — como
  todo o resto do currículo, pode ser praticado a qualquer momento.
- No Mapa de Aventura, a barra de rolagem nativa da trilha virou dois
  botões "‹›" com rolagem suave, e cada marco só aparece (fade + leve
  escala) quando entra na área visível, dando uma sensação de "revelar
  o caminho" em vez de arrastar uma barra crua.

### Loja de equipamentos: vender, descartar, nível mínimo por raridade

- `loot_service.sell`/`discard`: um espólio não equipado agora pode
  ser vendido (vira Ouro, novo campo em `PlayerStats`, escalado por
  raridade) ou descartado para sempre — ambos exigem desequipar
  primeiro, pra nunca perder um bônus ativo sem querer. Ainda não há
  loja de compra — só o lado de venda existe por enquanto.
- `MIN_LEVEL_BY_RARITY`: equipar agora exige um nível mínimo por
  raridade (alinhado aos mesmos degraus de rank já exibidos no
  ranking — Bronze/Prata/Ouro), validado no servidor em `equip()`, não
  só escondido na interface. Um jogador de nível baixo não consegue
  mais equipar um item lendário sem antes progredir de verdade.
- Corrige um bug real de exibição: o bônus "vida" (e "fúria") é um
  valor fixo (ex.: +8 de vida), não uma fração — mas o template
  multiplicava por 100 e mostrava como porcentagem (`+1440%`).
  `_macros.html`'s `passive_label()` agora usa a mesma convenção do
  `battle-loot.js`, reutilizada nas duas telas de equipamento.

### "As Crônicas de Arith" — história do reino expandida em capítulos

- Cada matéria tinha um parágrafo curto de lore, revelado frase a
  frase e repetitivo depois de 3-4 vitórias. Virou uma única trama
  contínua ("a princesa Sela, aprisionada por uma maldição tecida pelo
  Mercador das Sombras") contada em ~5 capítulos por matéria
  (`Chronicle.stages`, no lugar de um texto único) — cada vitória
  revela o próximo capítulo daquela trilha, e a página Crônicas do
  Reino mostra a trama inteira, numerada, assim que a matéria é
  descoberta.
- Cada classe ganhou uma linha de sabor própria (`classes.CLASS_LORE`)
  amarrada à mesma trama, mostrada no seletor de classe e no perfil.
- A primeira escolha de classe agora abre com um parágrafo de
  ambientação — o mistério da princesa Sela e a missão do jogador —
  em vez de ir direto para o formulário.

## O que ainda não existe

- O deploy em si (servidor real, domínio, TLS emitido de verdade) — os
  artefatos e o runbook estão prontos em [DEPLOY.md](DEPLOY.md), falta
  alguém com acesso a um provedor de nuvem executar os passos.
- Masmorra em co-op é assíncrona por design (ver acima) — não há
  batalha ao vivo sincronizada entre dois jogadores.
- PvP ranqueado com troféus — decidido como assíncrono por pontuação
  (mesmo desafio para os dois jogadores, comparado depois), ainda não
  implementado.
- Sistema de amigos: doação de itens, presença online/offline,
  incursão de masmorra em dupla de verdade — pedido, ainda não
  implementado.
- Troca de senha na conta e sistema de moderação de chat (palavras-
  chave + sanções graduais) — pedidos, ainda não implementados.

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
