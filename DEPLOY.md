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

## 1. Provisionar o servidor

Qualquer VM Linux (Ubuntu/Debian) com acesso root serve — droplet da
DigitalOcean, instância EC2, Hetzner, etc. Requisitos mínimos: 1 vCPU,
1GB RAM é suficiente para começar. Aponte o DNS do seu domínio para o IP
do servidor antes de configurar o Caddy (ele precisa disso pra emitir o
certificado TLS automaticamente).

## 2. Instalar dependências do sistema

```bash
sudo apt update
sudo apt install -y python3-venv python3-pip postgresql-client git

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

## 3. Criar o banco e o usuário da aplicação

```bash
sudo -u postgres createuser math_rpg
sudo -u postgres createdb math_rpg_production --owner=math_rpg
sudo -u postgres psql -c "ALTER USER math_rpg WITH PASSWORD 'escolha-uma-senha-forte';"
```

## 4. Colocar o código no servidor

```bash
sudo useradd --system --create-home --home-dir /opt/math-rpg math-rpg
sudo -u math-rpg git clone https://github.com/Gerson-if/Math_Rpg.git /opt/math-rpg
cd /opt/math-rpg
sudo -u math-rpg python3 -m venv .venv
sudo -u math-rpg .venv/bin/pip install -r requirements.txt
```

## 5. Configurar variáveis de ambiente

```bash
sudo -u math-rpg cp .env.example .env
sudo -u math-rpg nano .env
```

No mínimo:

```bash
FLASK_ENV=production
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

## 6. Migrações e seed

```bash
cd /opt/math-rpg
sudo -u math-rpg .venv/bin/flask db upgrade
sudo -u math-rpg .venv/bin/python scripts/seed.py
```

## 7. Gunicorn como serviço systemd

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

## 8. Caddy (proxy reverso + HTTPS automático)

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

## 9. Agendar os jobs periódicos

Nenhum scheduler roda dentro do processo da aplicação (ver comentários em
`gunicorn.conf.py` e `app/__init__.py` — com múltiplos workers, um
scheduler interno rodaria em duplicidade). Use cron:

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
mesmo disco do banco não sobrevive a uma falha de disco.

## 10. Checagem final

```bash
curl -sf https://seu-dominio.com/health
# {"status": "ok"}
```

Veja `journalctl -u math-rpg -f` para os logs estruturados em JSON da
aplicação (um objeto por linha — `timestamp`, `level`, `message`, e pra
cada requisição `method`/`path`/`status`/`user_id`), e
`journalctl -u caddy -f` para os logs de acesso do proxy.

## Rollback

```bash
cd /opt/math-rpg
sudo -u math-rpg git checkout <commit-anterior>
sudo -u math-rpg .venv/bin/pip install -r requirements.txt
sudo -u math-rpg .venv/bin/flask db upgrade   # migrações são só pra frente —
                                                # ver downgrade() em cada
                                                # arquivo de migrations/versions/
                                                # se precisar reverter o schema
sudo systemctl restart math-rpg
```
