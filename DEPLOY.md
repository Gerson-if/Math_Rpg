# Deploy em produção

Runbook para colocar a Matemática RPG num servidor de verdade: Postgres,
Gunicorn, Caddy, backups e o agendador de leaderboards. Os artefatos
(`gunicorn.conf.py`, `Caddyfile`, `deploy/math-rpg.service`) já estão no
repo — este documento é o passo a passo de como usá-los.

**O que foi validado durante o desenvolvimento, e o que não foi:** rodei
`flask db upgrade` e a suíte de smoke (registro, prática nos 9 tópicos,
conquista via critério JSON, chat, ranking) contra um Postgres 18 real
local — isso pegou um bug de verdade (`RATELIMIT_DEFAULT` mal formatado
quebrava toda requisição) que só apareceria em produção. O que eu **não**
tenho é uma conta em nuvem ou servidor real para de fato publicar isto —
os passos abaixo são o runbook para você (ou quem for fazer o deploy)
seguir; eu não consigo executá-los por não ter acesso a essa infra.

## Instalação automatizada (recomendado)

`deploy/install.sh` automatiza tudo que a instalação manual abaixo
descreve — pacotes do sistema, PostgreSQL (ou SQLite), Caddy com HTTPS
automático, usuário de sistema, migrações, o serviço systemd e as rotinas
agendadas de backup/leaderboard — e depois de instalado vira uma
ferramenta de gerência (atualizar com segurança, ver status, reiniciar,
backup/restore). Requer um servidor Ubuntu/Debian limpo com acesso root.
Se for usar domínio, aponte o DNS pro IP do servidor antes de instalar.

```bash
curl -fsSL -o install.sh https://raw.githubusercontent.com/Gerson-if/Math_Rpg/main/deploy/install.sh
sudo bash install.sh
```

Baixe o script antes de rodar — nunca `curl | sudo bash` diretamente: sem
um terminal de verdade o menu interativo não funciona (o stdin já está
ocupado pelo próprio script), e você perde a chance de revisar o script
antes de executar como root.

O script pergunta:

- **Domínio ou IP** — com domínio, emite um certificado TLS de verdade
  (Let's Encrypt ou ZeroSSL, à sua escolha); só com o IP do servidor,
  gera um certificado autoassinado localmente confiável (`tls internal`
  do Caddy) — o navegador vai avisar na primeira visita, isso é esperado
  sem um domínio de verdade.
- **E-mail** — usado pela autoridade certificadora para avisos de
  expiração do certificado.
- **Banco de dados** — PostgreSQL (recomendado) ou SQLite (mais simples,
  ok pra uso pequeno/teste).

Ao final, a tela mostra — e salva em
`/root/math-rpg-install-credentials.txt` (permissão 600, só root lê) — a
`SECRET_KEY` e as credenciais do banco geradas **nessa** instalação
(sempre novas a cada instalação, nunca reaproveitadas). Copie para um
cofre de senhas e apague o arquivo depois.

Uso não interativo (automação):

```bash
sudo bash install.sh --action=install --domain=math.seusite.com --email=voce@seusite.com --ssl=letsencrypt --db=postgres --yes
sudo bash install.sh --action=install --ip --db=sqlite --yes   # sem domínio, certificado autoassinado
```

### Depois de instalado: gerenciar

Rode `sudo bash /opt/math-rpg/deploy/install.sh` de novo (sem flags) para
abrir o menu:

1. **Instalar/reinstalar** — reconfigura por cima; gera `SECRET_KEY` e
   senha do banco **novas** (avisa antes — isso encerra sessões ativas).
   Os dados do banco em si são preservados.
2. **Atualizar a aplicação** — rotina pensada pra não derrubar produção:
   recusa rodar se houver alterações locais não commitadas; faz backup
   do banco antes de tocar em qualquer coisa; só avança
   (`git merge --ff-only`) se for um fast-forward de verdade; instala
   dependências, roda as migrações, reinicia o serviço e espera
   `/health` responder. **Se a migração ou o health check falhar depois,
   reverte sozinho**: código volta pro commit anterior, o banco é
   restaurado a partir do backup feito segundos antes, reinicia de novo
   e confere a saúde mais uma vez. Só para sem resolver sozinho se o
   próprio rollback falhar — nesse caso avisa exatamente o que checar
   manualmente (`journalctl -u math-rpg`).
3. **Ver status dos serviços** — `math-rpg`, `caddy`, `postgresql`,
   timers de backup/leaderboard: ativo/habilitado, versão (commit) atual,
   saúde da aplicação, último backup, próximas execuções agendadas.
4. **Reiniciar a aplicação** — `systemctl restart math-rpg` e confere
   `/health` depois.
5. **Backup do banco agora** — chama `scripts/backup_db.py` sob demanda
   (além do timer diário automático).
6. **Restaurar um backup** — lista os backups disponíveis, pede
   confirmação explícita (digitar `RESTAURAR`) e sempre salva uma cópia
   de segurança do banco atual antes de sobrescrever
   (`pre-restore-safety-*`).

Cada ação também roda direto, sem menu: `--action=update`,
`--action=status`, `--action=restart`, `--action=backup`.

### O que o instalador configura

- **Backups automáticos** — `deploy/math-rpg-backup.timer` roda
  `scripts/backup_db.py` todo dia às 3h15 (Postgres: `pg_dump` gzipado;
  SQLite: cópia do arquivo), com 14 dias de retenção por padrão
  (`BACKUP_RETENTION_DAYS`). `scripts/restore_db.py` é o par — restaura
  um backup, sempre snapshotando o banco atual antes de sobrescrever.
- **Leaderboards** — `math-rpg-leaderboards-weekly.timer` e
  `-monthly.timer` recalculam o ranking (substituem os cron jobs
  descritos na seção manual abaixo por unidades systemd, mais fáceis de
  inspecionar com `systemctl status`/`journalctl`).
- **Firewall (ufw)** — libera a porta SSH detectada automaticamente (não
  assume 22 fixo), 80 e 443; todo o resto fica bloqueado.
- **systemd** — `math-rpg.service` roda a aplicação via Gunicorn (worker
  `eventlet`, necessário para os duelos em tempo real).
- **Assets do frontend sem CDN** — Node.js é instalado só para compilar,
  em build-time, o Tailwind CSS e copiar as cópias locais de htmx/
  FontAwesome/fontes (`npm ci && npm run build`, ver seção 6 abaixo);
  nada disso fica rodando em produção, e a aplicação nunca faz uma
  requisição a `cdn.tailwindcss.com`, `fonts.googleapis.com`,
  `cdnjs.cloudflare.com` ou qualquer outro CDN em tempo de execução.

A seção abaixo documenta cada passo manualmente — útil pra entender o que
o script faz por baixo dos panos, ou pra customizar algo que ele não
cobre (outra distro, infra gerenciada, etc.).

## Instalação manual (passo a passo)

### 1. Provisionar o servidor

Qualquer VM Linux (Ubuntu/Debian) com acesso root serve — droplet da
DigitalOcean, instância EC2, Hetzner, etc. Requisitos mínimos: 1 vCPU,
1GB RAM é suficiente para começar. Aponte o DNS do seu domínio para o IP
do servidor antes de configurar o Caddy (ele precisa disso pra emitir o
certificado TLS automaticamente).

### 2. Instalar dependências do sistema

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip postgresql-client git

# Node.js — só usado em build-time, para compilar o Tailwind CSS e copiar
# as cópias locais de htmx/FontAwesome/fontes (ver passo 6 abaixo e
# README.md's "Assets locais"). Não fica rodando em produção.
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo bash -
sudo apt install -y nodejs

# Caddy (repositório oficial)
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

Postgres pode ser um serviço gerenciado (RDS, Cloud SQL, Supabase,
DigitalOcean Managed Databases, ...) — recomendado, evita ter que cuidar
de backup/failover do banco você mesmo. Se preferir self-hosted:
`sudo apt install -y postgresql`.

### 3. Criar o banco e o usuário da aplicação

```bash
sudo -u postgres createuser math_rpg
sudo -u postgres createdb math_rpg_production --owner=math_rpg
sudo -u postgres psql -c "ALTER USER math_rpg WITH PASSWORD 'escolha-uma-senha-forte';"
```

### 4. Colocar o código no servidor

```bash
sudo useradd --system --create-home --home-dir /opt/math-rpg math-rpg
sudo -u math-rpg git clone https://github.com/Gerson-if/Math_Rpg.git /opt/math-rpg
cd /opt/math-rpg
sudo -u math-rpg python3 -m venv .venv
sudo -u math-rpg .venv/bin/pip install -r requirements.txt
```

### 5. Configurar variáveis de ambiente

```bash
sudo -u math-rpg cp .env.example .env
sudo -u math-rpg nano .env
```

No mínimo:

```bash
FLASK_ENV=production
# FLASK_APP diz ao CLI "flask" (usado nos passos 6 e 9 abaixo) onde achar
# a aplicação — sem isso os comandos "flask db upgrade" / "flask
# recompute-leaderboards" falham com "Could not locate a Flask
# application" (não há app.py/wsgi.py no projeto, só run.py).
FLASK_APP=run.py
SECRET_KEY=<gere com: python -c "import secrets; print(secrets.token_hex(32))">
DATABASE_URL=postgresql://math_rpg:escolha-uma-senha-forte@localhost:5432/math_rpg_production

# Só necessário com mais de 1 worker do Gunicorn (ver gunicorn.conf.py) —
# sem isso, cada worker tem seu próprio contador e o rate limit não é
# aplicado de forma consistente entre eles. Requer "pip install redis"
# (não vem em requirements.txt — é opcional, só quem usa Redis precisa).
RATELIMIT_STORAGE_URI=redis://localhost:6379

# Duelos em tempo real (Flask-SocketIO). Deixe SOCKETIO_ASYNC_MODE de fora
# em produção com um único worker eventlet (é o padrão do gunicorn.conf.py)
# — só defina explicitamente se estiver rodando atrás de outro arranjo.
# SOCKETIO_MESSAGE_QUEUE só é necessário se você for rodar MAIS de um
# worker: uma conexão WebSocket fica presa a um único worker, então sem
# uma fila compartilhada os dois duelistas podem cair em workers
# diferentes e nunca verem os eventos um do outro. Mesmo Redis do
# RATELIMIT_STORAGE_URI acima serve.
# SOCKETIO_MESSAGE_QUEUE=redis://localhost:6379
```

### 6. Compilar os assets do frontend

A aplicação não depende de nenhum CDN em produção (Tailwind CSS, fontes,
FontAwesome e htmx são todos servidos localmente) — mas por isso mesmo
precisam ser compilados/copiados uma vez, aqui, antes de subir a
aplicação:

```bash
cd /opt/math-rpg
sudo -u math-rpg npm ci
sudo -u math-rpg npm run build
```

Isso gera `app/static/css/tailwind.css` (compilado a partir de
`assets/css/input.css` + `tailwind.config.js`) e copia htmx/FontAwesome/
fontes de `node_modules` para `app/static/vendor/` (ver
`assets/copy-vendor-assets.js`). Nenhum dos dois é commitado no git —
rode este passo de novo sempre que atualizar o código (o script de
atualização automatizado do `deploy/install.sh` já faz isso sozinho).

### 7. Migrações e seed

```bash
cd /opt/math-rpg
sudo -u math-rpg .venv/bin/flask db upgrade
sudo -u math-rpg .venv/bin/python scripts/seed.py
```

### 8. Gunicorn como serviço systemd

```bash
sudo cp deploy/math-rpg.service /etc/systemd/system/math-rpg.service
sudo systemctl daemon-reload
sudo systemctl enable --now math-rpg
sudo systemctl status math-rpg   # deve mostrar "active (running)"
```

`gunicorn.conf.py` já lê `GUNICORN_WORKERS`/`GUNICORN_BIND`/etc. de
variáveis de ambiente se você quiser ajustar sem editar o arquivo.

O worker padrão agora é `eventlet` (não `sync`) — necessário para os
duelos em tempo real via WebSocket. Com um único worker (o padrão sem
`SOCKETIO_MESSAGE_QUEUE` configurado) não precisa de mais nada: um worker
eventlet já lida bem com muitas conexões simultâneas via green threads,
diferente de um worker `sync`. Só suba para mais de um worker depois de
configurar `SOCKETIO_MESSAGE_QUEUE` (Redis) — ver seção 5.

### 9. Caddy (proxy reverso + HTTPS automático)

Edite `Caddyfile` na raiz do projeto: troque `math-rpg.example.com` pelo
seu domínio de verdade.

```bash
sudo mkdir -p /var/log/caddy
export APP_DIR=/opt/math-rpg   # usado dentro do Caddyfile
sudo caddy validate --config /opt/math-rpg/Caddyfile
sudo cp /opt/math-rpg/Caddyfile /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Na primeira requisição HTTPS pro domínio, o Caddy emite o certificado
Let's Encrypt sozinho — nada de certbot ou renovação manual.

### 10. Agendar os jobs periódicos

Nenhum scheduler roda dentro do processo da aplicação (ver comentários em
`gunicorn.conf.py` e `app/__init__.py` — com múltiplos workers, um
scheduler interno rodaria em duplicidade). `deploy/install.sh` resolve
isso com unidades systemd (`math-rpg-backup.timer`,
`math-rpg-leaderboards-weekly.timer`, `math-rpg-leaderboards-monthly.timer`
— copie os `.service`/`.timer` de `deploy/` para
`/etc/systemd/system/` e rode `systemctl enable --now <nome>.timer`).
Se preferir cron em vez de systemd, o equivalente é:

```bash
sudo -u math-rpg crontab -e
```

```cron
# Leaderboard semanal — toda segunda à meia-noite
0 0 * * 1 cd /opt/math-rpg && .venv/bin/flask recompute-leaderboards --scope weekly >> /var/log/math-rpg/leaderboards.log 2>&1

# Leaderboard mensal — todo dia 1 à meia-noite
0 0 1 * * cd /opt/math-rpg && .venv/bin/flask recompute-leaderboards --scope monthly >> /var/log/math-rpg/leaderboards.log 2>&1

# Backup do banco — todo dia às 3h
0 3 * * * cd /opt/math-rpg && DATABASE_URL=$(grep DATABASE_URL .env | cut -d= -f2-) .venv/bin/python scripts/backup_db.py >> /var/log/math-rpg/backup.log 2>&1
```

Em produção, prefira copiar os backups pra fora do servidor (S3, backup
gerenciado do provedor do Postgres, etc.) — um backup que vive só no
mesmo disco do banco não sobrevive a uma falha de disco. Para restaurar
um backup gerado por qualquer um dos dois caminhos, use
`scripts/restore_db.py --latest` (veja `--help`).

### 11. Checagem final

```bash
curl -sf https://seu-dominio.com/health
# {"status": "ok"}
```

Veja `journalctl -u math-rpg -f` para os logs estruturados em JSON da
aplicação (um objeto por linha — `timestamp`, `level`, `message`, e pra
cada requisição `method`/`path`/`status`/`user_id`), e
`journalctl -u caddy -f` para os logs de acesso do proxy.

### Rollback

```bash
cd /opt/math-rpg
sudo -u math-rpg git checkout <commit-anterior>
sudo -u math-rpg .venv/bin/pip install -r requirements.txt
sudo -u math-rpg npm ci
sudo -u math-rpg npm run build
sudo -u math-rpg .venv/bin/flask db upgrade   # migrações são só pra frente —
                                                # ver downgrade() em cada
                                                # arquivo de migrations/versions/
                                                # se precisar reverter o schema
sudo systemctl restart math-rpg
```
