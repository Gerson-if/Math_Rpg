#!/usr/bin/env bash
#
# Matematica RPG — instalador e gerenciador para VM/VPS Ubuntu ou Debian.
#
# Primeira execução instala tudo do zero (pacotes de sistema, banco de
# dados, Caddy com HTTPS, systemd, backups agendados). Execuções seguintes
# abrem um menu para atualizar com segurança, ver status, reiniciar,
# fazer backup/restaurar, ou migrar o jogo inteiro para outro servidor.
#
# Requer uma VM/VPS Ubuntu ou Debian de verdade, com systemd como PID 1 e
# acesso de saída à internet (apt, o repositório do Caddy, o do Node.js,
# GitHub, npm). NÃO funciona em containers de desenvolvimento efêmeros
# (GitHub Codespaces, VS Code Dev Containers, `docker run` sem systemd) —
# o instalador detecta isso e avisa antes de começar (ver
# "Verificar ambiente" no menu, ou --action=check-env), mas se você só
# quer rodar o jogo localmente para testar/desenvolver, use
# `python run.py` direto (ver README.md), não este instalador.
#
# Uso interativo (recomendado):
#   sudo bash install.sh
#
# Uso não interativo (automação/CI):
#   sudo bash install.sh --action=install --domain=math.exemplo.com --email=voce@exemplo.com
#   sudo bash install.sh --action=install --ip --db=sqlite --yes
#   sudo bash install.sh --action=update
#   sudo bash install.sh --action=status
#   sudo bash install.sh --action=restart
#   sudo bash install.sh --action=backup
#   sudo bash install.sh --action=restore
#   sudo bash install.sh --action=check-env
#   sudo bash install.sh --action=migrate-export
#   sudo bash install.sh --action=migrate-import --file=/caminho/math-rpg-migration-*.tar.gz
#
# Migrar o jogo para outro servidor (visão geral — ver seção "Migração"
# do menu para o passo a passo completo):
#   1. Neste servidor:      sudo bash install.sh --action=migrate-export
#   2. Copie o .tar.gz gerado para o servidor novo (scp).
#   3. No servidor novo:    sudo bash install.sh --action=install ...   (instalação normal)
#   4. No servidor novo:    sudo bash install.sh --action=migrate-import --file=<arquivo>
#
# Não rode isto com "curl | sudo bash" — sem um terminal de verdade o menu
# interativo não funciona (o stdin já está ocupado pelo próprio script) e
# você perde a chance de revisar o script antes de executar como root.
# Baixe primeiro, depois rode:
#   curl -fsSL -o install.sh https://raw.githubusercontent.com/Gerson-if/Math_Rpg/main/deploy/install.sh
#   sudo bash install.sh

set -Eeuo pipefail
umask 077

# ---------------------------------------------------------------------------
# Constantes / configuração fixa
# ---------------------------------------------------------------------------
REPO_URL_DEFAULT="https://github.com/Gerson-if/Math_Rpg.git"
APP_DIR="/opt/math-rpg"
APP_USER="math-rpg"
DB_NAME="math_rpg_production"
DB_USER="math_rpg"
LOG_FILE="/var/log/math-rpg-install.log"
CRED_FILE="/root/math-rpg-install-credentials.txt"
STATE_FILE="/etc/math-rpg-install.conf"
HEALTH_URL_LOCAL="http://127.0.0.1:8000/health"

# ---------------------------------------------------------------------------
# Saída / log
# ---------------------------------------------------------------------------
log_line() { printf '%s [%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$1" "$2" >>"$LOG_FILE" 2>/dev/null || true; }
info() { echo -e "\033[36m➜ $*\033[0m"; log_line INFO "$*"; }
ok()   { echo -e "\033[32m✔ $*\033[0m"; log_line OK "$*"; }
warn() { echo -e "\033[33m⚠ $*\033[0m" >&2; log_line WARN "$*"; }
err()  { echo -e "\033[31m✘ $*\033[0m" >&2; log_line ERROR "$*"; }
die()  { err "$*"; exit 1; }

trap 'err "Falha inesperada na linha $LINENO (comando: $BASH_COMMAND). A maioria das etapas deste instalador é idempotente — corrija o problema (veja '"$LOG_FILE"' para o log completo) e rode o script de novo; ele retoma de onde parou em vez de refazer tudo."' ERR

# ---------------------------------------------------------------------------
# Rede / pacotes — tolerância a falhas transitórias
# ---------------------------------------------------------------------------
# apt-get, curl para chaves/repositórios de terceiros (Caddy, Node.js) e git
# são os pontos mais prováveis de falha numa instalação "do zero" — uma
# hiccup de rede de alguns segundos aí não deveria derrubar a instalação
# inteira com uma mensagem genérica de "falha na linha X". Os helpers
# abaixo dão a essas etapas: (1) algumas tentativas com espera entre elas
# antes de desistir, e (2) uma mensagem específica e acionável quando
# mesmo assim falham, em vez de só apontar para o log.

retry() {
  # retry <tentativas> <espera_segundos> -- <comando...>
  local tries="$1" delay="$2" n=1
  shift 2
  until "$@"; do
    if (( n >= tries )); then
      return 1
    fi
    warn "Comando falhou (tentativa $n/$tries) — tentando de novo em ${delay}s..."
    sleep "$delay"
    n=$((n + 1))
  done
  return 0
}

explain_apt_failure() {
  echo >&2
  echo "----- últimas linhas do log ($LOG_FILE) -----" >&2
  tail -n 25 "$LOG_FILE" >&2 2>/dev/null || true
  echo "----------------------------------------------" >&2
  local tail_text
  tail_text=$(tail -n 80 "$LOG_FILE" 2>/dev/null || true)
  if grep -qiE 'temporary failure resolving|could not resolve|name or service not known' <<<"$tail_text"; then
    warn "Diagnóstico provável: falha de DNS — este servidor não conseguiu resolver um nome de host. Verifique a conectividade de saída e /etc/resolv.conf."
  elif grep -qiE 'connection timed out|could not connect|network is unreachable|failed to fetch' <<<"$tail_text"; then
    warn "Diagnóstico provável: falha de conectividade de saída (timeout ou rede inalcançável). Verifique firewall de saída, proxy, ou security group/regras de rede do provedor de nuvem."
  elif grep -qiE 'could not get lock|resource temporarily unavailable' <<<"$tail_text"; then
    warn "Diagnóstico provável: outro processo apt/dpkg está rodando ao mesmo tempo (ex.: atualizações automáticas do sistema). Espere terminar (\"ps aux | grep apt\") e rode de novo."
  elif grep -qiE 'no_pubkey|gpg error|is not signed|expkeysig' <<<"$tail_text"; then
    warn "Diagnóstico provável: problema com a chave GPG de um repositório de terceiros (provavelmente o do Caddy). Tente: sudo rm -f /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list — e rode a instalação de novo."
  fi
}

wait_for_apt_lock() {
  command -v fuser >/dev/null 2>&1 || return 0
  local waited=0
  while fuser /var/lib/dpkg/lock-frontend >/dev/null 2>&1 || fuser /var/lib/apt/lists/lock >/dev/null 2>&1; do
    (( waited == 0 )) && info "Outro processo apt/dpkg está em execução — aguardando ele liberar..."
    sleep 3
    waited=$((waited + 3))
    (( waited >= 120 )) && die "Outro processo apt/dpkg segue em execução há mais de 2 minutos. Verifique manualmente (\"ps aux | grep -E 'apt|dpkg'\") e rode a instalação de novo."
  done
}

apt_update_or_die() {
  local context="${1:-}"
  wait_for_apt_lock
  if ! retry 3 5 apt-get update -y >>"$LOG_FILE" 2>&1; then
    explain_apt_failure
    die "apt-get update falhou depois de 3 tentativas${context:+ ($context)}."
  fi
}

apt_install_or_die() {
  wait_for_apt_lock
  if ! retry 3 5 apt-get install -y "$@" >>"$LOG_FILE" 2>&1; then
    explain_apt_failure
    die "Falha instalando pacote(s) do sistema: $*"
  fi
}

check_disk_space() {
  local avail_kb
  avail_kb=$(df -Pk "$APP_DIR" 2>/dev/null | awk 'NR==2{print $4}')
  [[ -z "$avail_kb" ]] && avail_kb=$(df -Pk / 2>/dev/null | awk 'NR==2{print $4}')
  if [[ -n "$avail_kb" ]] && (( avail_kb < 1048576 )); then
    warn "Menos de 1GB livre em disco ($(( avail_kb / 1024 ))MB) — a instalação (pacotes do sistema, dependências Python/Node, assets compilados) pode falhar por falta de espaço."
    confirm "Continuar mesmo assim?" N || die "Instalação cancelada — libere espaço em disco primeiro."
  fi
}

# Ambientes de desenvolvimento efêmeros (Codespaces, Dev Containers, `docker
# run` sem systemd) são a causa mais comum de "funcionou até a metade e
# quebrou de um jeito confuso" com este instalador: ele assume systemd de
# verdade rodando como PID 1 (para o serviço da aplicação, Caddy, timers de
# backup/leaderboard) e um filesystem persistente entre reinícios — coisas
# que um container de dev tipicamente não garante. Detectar isso ANTES de
# mexer em qualquer pacote evita descobrir só depois de meia instalação
# feita (exatamente o que aconteceria sem esta checagem: apt-get funciona
# normalmente num container, então a primeira coisa a realmente quebrar
# costuma ser bem mais adiante, em install_systemd_units ou configure_caddy
# — bem mais confuso de diagnosticar do que um aviso logo no início).
detect_environment_warnings() {
  local warnings=()

  if [[ -n "${CODESPACES:-}" || -n "${REMOTE_CONTAINERS:-}" || -f /.dockerenv || -n "${DEVCONTAINER:-}" ]]; then
    warnings+=("Este ambiente parece ser um container de desenvolvimento (Codespaces / Dev Container / Docker), não um servidor de verdade. Este instalador é para uma VM/VPS Ubuntu ou Debian com systemd de verdade e disco persistente — num container de dev a instalação tende a falhar de formas confusas mais adiante (systemd, Caddy, firewall), mesmo que os passos iniciais (apt) funcionem normalmente. Para só rodar o jogo localmente, use \"python run.py\" (ver README.md) em vez deste instalador.")
  fi

  if [[ ! -d /run/systemd/system ]]; then
    warnings+=("systemd não parece estar rodando como PID 1 neste ambiente (checagem: /run/systemd/system ausente). Este instalador depende de \"systemctl\" para o serviço da aplicação, o Caddy e os timers de backup/leaderboard — sem systemd de verdade essas etapas vão falhar.")
  fi

  if (( ${#warnings[@]} > 0 )); then
    echo
    warn "AMBIENTE POTENCIALMENTE INCOMPATÍVEL:"
    local w
    for w in "${warnings[@]}"; do
      echo "$w" | fold -s -w 100 | sed 's/^/   /'
      echo
    done
    confirm "Mesmo assim, continuar?" N || die "Instalação cancelada — rode isto numa VM/VPS de verdade (Ubuntu/Debian, systemd)."
  fi
}

# Hosts efetivamente necessários em algum ponto da instalação — checados
# ANTES de começar a mexer em pacotes, para dar um diagnóstico específico
# ("sem acesso a X") em vez de deixar a instalação quebrar na metade com
# só um número de linha. Modo "report": só informa (usado por
# action_check_environment, uma ferramenta de diagnóstico isolada). Modo
# "strict" (padrão): pede confirmação antes de prosseguir se algo falhar.
check_network_reachability() {
  local mode="${1:-strict}"
  info "Verificando conectividade de rede com os serviços necessários..."
  local hosts=(
    "github.com:clonar o código-fonte"
    "deb.nodesource.com:repositório do Node.js"
    "registry.npmjs.org:dependências de frontend (npm)"
    "dl.cloudsmith.io:repositório do Caddy"
  )
  local failures=0 entry host desc
  for entry in "${hosts[@]}"; do
    host="${entry%%:*}"; desc="${entry#*:}"
    if curl -sS --max-time 5 -o /dev/null "https://$host" 2>/dev/null; then
      ok "  $host — OK ($desc)"
    else
      warn "  $host — SEM RESPOSTA ($desc)"
      failures=$((failures + 1))
    fi
  done

  if (( failures > 0 )); then
    warn "$failures de ${#hosts[@]} serviço(s) externo(s) inacessível(is) a partir deste servidor — as etapas que dependem deles provavelmente vão falhar. Verifique firewall de saída, proxy ou DNS."
    if [[ "$mode" == "strict" ]]; then
      confirm "Continuar mesmo assim?" N || die "Instalação cancelada — resolva a conectividade primeiro."
    fi
  else
    ok "Conectividade com todos os serviços necessários confirmada."
  fi
}

# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------
is_valid_domain() { [[ "$1" =~ ^([a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$ ]]; }
is_valid_email()  { [[ "$1" =~ ^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]]; }

detect_public_ip() {
  curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null \
    || curl -fsS --max-time 5 https://ifconfig.me 2>/dev/null \
    || hostname -I 2>/dev/null | awk '{print $1}'
}

check_dns_matches_server() {
  local domain="$1" server_ip="$2" resolved
  resolved=$(getent hosts "$domain" 2>/dev/null | awk '{print $1}' | head -n1)
  if [[ -z "$resolved" ]]; then
    warn "Não foi possível resolver $domain via DNS ainda."
    return 1
  fi
  if [[ "$resolved" != "$server_ip" ]]; then
    warn "$domain resolve para $resolved, mas o IP público deste servidor é $server_ip."
    return 1
  fi
  ok "$domain já aponta para este servidor ($server_ip)."
  return 0
}

require_root() { [[ $EUID -eq 0 ]] || die "Rode como root (sudo bash install.sh)."; }

check_os() {
  [[ -f /etc/os-release ]] || die "Não foi possível detectar o sistema operacional."
  # shellcheck disable=SC1091
  . /etc/os-release
  case "${ID:-}" in
    ubuntu|debian) ;;
    *) warn "Testado em Ubuntu/Debian. Detectado: ${PRETTY_NAME:-desconhecido}. Continuando por sua conta e risco." ;;
  esac
}

gen_secret_hex() { openssl rand -hex "${1:-32}"; }
gen_password()   { tr -dc 'A-Za-z0-9' </dev/urandom | head -c "${1:-32}"; echo; }

confirm() {
  local prompt="$1" default="${2:-N}" suffix reply
  [[ "${ASSUME_YES:-0}" == "1" ]] && return 0
  suffix="[s/N]"; [[ "$default" == "S" ]] && suffix="[S/n]"
  read -r -p "$prompt $suffix " reply || reply=""
  reply="${reply:-$default}"
  [[ "$reply" =~ ^[sSyY] ]]
}

ask() {
  local prompt="$1" default="${2:-}" reply
  if [[ -n "$default" ]]; then
    read -r -p "$prompt [$default]: " reply || reply=""
    echo "${reply:-$default}"
  else
    read -r -p "$prompt: " reply || reply=""
    echo "$reply"
  fi
}

# ---------------------------------------------------------------------------
# Parsing de argumentos
# ---------------------------------------------------------------------------
ACTION=""
DOMAIN=""
USE_IP=""
EMAIL=""
SSL_MODE=""      # letsencrypt|zerossl|selfsigned
DB_ENGINE=""     # postgres|sqlite
REPO_URL="$REPO_URL_DEFAULT"
BRANCH="main"
ASSUME_YES=0
MIGRATION_FILE=""

print_help() {
  sed -n '2,46p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --action=*) ACTION="${1#*=}" ;;
    --domain=*) DOMAIN="${1#*=}" ;;
    --ip) USE_IP=1 ;;
    --email=*) EMAIL="${1#*=}" ;;
    --ssl=*) SSL_MODE="${1#*=}" ;;
    --db=*) DB_ENGINE="${1#*=}" ;;
    --repo=*) REPO_URL="${1#*=}" ;;
    --branch=*) BRANCH="${1#*=}" ;;
    --file=*) MIGRATION_FILE="${1#*=}" ;;
    --yes|-y) ASSUME_YES=1 ;;
    -h|--help) print_help; exit 0 ;;
    *) die "Opção desconhecida: $1 (use --help)" ;;
  esac
  shift
done

load_installer_state() {
  [[ -f "$STATE_FILE" ]] || return 0
  local saved_domain saved_ssl saved_db
  saved_domain=$(grep -E '^DOMAIN=' "$STATE_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"')
  saved_ssl=$(grep -E '^SSL_MODE=' "$STATE_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"')
  saved_db=$(grep -E '^DB_ENGINE=' "$STATE_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"')
  [[ -z "$DOMAIN" ]] && DOMAIN="$saved_domain"
  [[ -z "$SSL_MODE" ]] && SSL_MODE="$saved_ssl"
  [[ -z "$DB_ENGINE" ]] && DB_ENGINE="$saved_db"
}

save_installer_state() {
  {
    echo "DOMAIN=\"$DOMAIN\""
    echo "SSL_MODE=\"$SSL_MODE\""
    echo "DB_ENGINE=\"$DB_ENGINE\""
  } >"$STATE_FILE"
  chmod 600 "$STATE_FILE"
}

# ---------------------------------------------------------------------------
# Ação: instalar
# ---------------------------------------------------------------------------
gather_install_inputs() {
  if [[ -z "$DOMAIN" && -z "$USE_IP" ]]; then
    local mode
    mode=$(ask "Instalar com domínio (d) ou apenas com o IP do servidor (i)?" "d")
    if [[ "$mode" =~ ^[dD] ]]; then
      DOMAIN=$(ask "Domínio (ex.: math.seusite.com)")
    else
      USE_IP=1
    fi
  fi

  if [[ -n "$DOMAIN" && -z "$SSL_MODE" ]]; then
    local choice
    choice=$(ask "Certificado SSL: Let's Encrypt (l, recomendado) ou ZeroSSL (z)?" "l")
    [[ "$choice" =~ ^[zZ] ]] && SSL_MODE="zerossl" || SSL_MODE="letsencrypt"
  elif [[ -n "$USE_IP" ]]; then
    SSL_MODE="selfsigned"
  fi

  if [[ "$SSL_MODE" != "selfsigned" && -z "$EMAIL" ]]; then
    EMAIL=$(ask "E-mail para avisos do certificado TLS")
  fi

  if [[ -z "$DB_ENGINE" ]]; then
    local dbchoice
    dbchoice=$(ask "Banco de dados: PostgreSQL (p, recomendado) ou SQLite (s, mais simples)?" "p")
    [[ "$dbchoice" =~ ^[sS] ]] && DB_ENGINE="sqlite" || DB_ENGINE="postgres"
  fi
}

validate_install_inputs() {
  if [[ -n "$DOMAIN" ]]; then
    is_valid_domain "$DOMAIN" || die "Domínio inválido: $DOMAIN"
  fi
  if [[ "$SSL_MODE" != "selfsigned" ]]; then
    is_valid_email "$EMAIL" || die "E-mail inválido: $EMAIL"
  fi
  case "$DB_ENGINE" in
    postgres|sqlite) ;;
    *) die "Motor de banco inválido: $DB_ENGINE (use postgres ou sqlite)" ;;
  esac

  PUBLIC_IP=$(detect_public_ip || true)
  [[ -n "$PUBLIC_IP" ]] || warn "Não foi possível detectar o IP público deste servidor."

  if [[ -n "$DOMAIN" ]]; then
    check_dns_matches_server "$DOMAIN" "$PUBLIC_IP" || {
      confirm "O DNS de $DOMAIN ainda não aponta para este servidor — a emissão do certificado vai falhar até isso ser corrigido. Continuar mesmo assim?" N \
        || die "Instalação cancelada — ajuste o DNS e rode novamente."
    }
  fi

  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -q ':80 '  && warn "Algo já está escutando na porta 80 (outro servidor web?). O Caddy pode falhar ao iniciar."
    ss -ltn 2>/dev/null | grep -q ':443 ' && warn "Algo já está escutando na porta 443."
  fi

  if [[ -d "$APP_DIR/.git" ]]; then
    warn "Já existe uma instalação em $APP_DIR."
    warn "Isso vai gerar uma SECRET_KEY e senha de banco NOVAS (sessões ativas serão encerradas) e reconfigurar os serviços. Os dados do banco são preservados."
    confirm "Continuar com a (re)instalação?" N || die "Instalação cancelada."
  fi
}

print_install_plan() {
  echo
  echo "==================== Plano de instalação ===================="
  if [[ -n "$DOMAIN" ]]; then
    echo " Endereço:   https://$DOMAIN"
    echo " TLS:        $SSL_MODE (e-mail: $EMAIL)"
  else
    echo " Endereço:   https://$PUBLIC_IP"
    echo " TLS:        certificado auto-assinado (Caddy 'tls internal')"
  fi
  echo " Banco:      $DB_ENGINE"
  echo " Diretório:  $APP_DIR"
  echo " Repositório: $REPO_URL (branch $BRANCH)"
  echo "================================================================"
  echo
}

install_system_packages() {
  info "Instalando pacotes do sistema (isso pode levar alguns minutos)..."
  export DEBIAN_FRONTEND=noninteractive

  apt_update_or_die
  apt_install_or_die python3-venv python3-pip python3-dev build-essential git curl gnupg ufw

  if [[ "$DB_ENGINE" == "postgres" ]]; then
    apt_install_or_die postgresql postgresql-contrib
  fi

  if ! command -v caddy >/dev/null 2>&1; then
    apt_install_or_die debian-keyring debian-archive-keyring apt-transport-https

    retry 3 5 bash -c "curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg >>'$LOG_FILE' 2>&1" \
      || die "Não foi possível baixar a chave GPG do repositório do Caddy (dl.cloudsmith.io) depois de 3 tentativas. Verifique a conectividade de saída deste servidor e rode a instalação de novo — veja $LOG_FILE."

    retry 3 5 bash -c "curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null 2>>'$LOG_FILE'" \
      || die "Não foi possível baixar a lista do repositório do Caddy (dl.cloudsmith.io) depois de 3 tentativas. Verifique a conectividade de saída deste servidor e rode a instalação de novo — veja $LOG_FILE."

    apt_update_or_die "depois de adicionar o repositório do Caddy — se o diagnóstico acima apontar para a chave GPG, rode: sudo rm -f /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list, e tente de novo"
    apt_install_or_die caddy
  fi

  # Node.js — needed once, at install/update time, to compile Tailwind CSS
  # and copy the local vendor copies of htmx/FontAwesome/fonts (see
  # build_frontend_assets below and README.md's "Assets locais" section).
  # Not needed at runtime: gunicorn serves the already-built files, so this
  # is a build-time-only dependency, same category as build-essential above.
  if ! command -v node >/dev/null 2>&1 || [[ "$(node -e 'console.log(process.versions.node.split(".")[0])' 2>/dev/null)" -lt 18 ]]; then
    retry 3 5 bash -c "curl -fsSL https://deb.nodesource.com/setup_20.x | bash - >>'$LOG_FILE' 2>&1" \
      || die "Não foi possível configurar o repositório do Node.js (deb.nodesource.com) depois de 3 tentativas. Verifique a conectividade de saída deste servidor e rode a instalação de novo — veja $LOG_FILE."
    apt_install_or_die nodejs
  fi

  ok "Pacotes do sistema instalados."
}

setup_database() {
  if [[ "$DB_ENGINE" != "postgres" ]]; then
    DATABASE_URL="sqlite:///${APP_DIR}/instance/dev.db"
    ok "Usando SQLite ($DATABASE_URL)."
    return
  fi

  info "Configurando PostgreSQL..."
  systemctl enable --now postgresql >>"$LOG_FILE" 2>&1

  DB_PASSWORD="$(gen_password 32)"

  if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" | grep -q 1; then
    sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASSWORD';" >/dev/null
  else
    sudo -u postgres createuser "$DB_USER"
    sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASSWORD';" >/dev/null
  fi

  if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
    sudo -u postgres createdb "$DB_NAME" --owner="$DB_USER"
  fi

  DATABASE_URL="postgresql://$DB_USER:$DB_PASSWORD@localhost:5432/$DB_NAME"
  ok "PostgreSQL pronto (banco=$DB_NAME, usuário=$DB_USER, senha gerada agora)."
}

create_system_user() {
  if id "$APP_USER" &>/dev/null; then
    info "Usuário de sistema $APP_USER já existe."
  else
    useradd --system --create-home --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
    ok "Usuário de sistema $APP_USER criado."
  fi
  mkdir -p "$APP_DIR"
  chown "$APP_USER":"$APP_USER" "$APP_DIR"
}

fetch_code() {
  info "Obtendo código-fonte..."
  if [[ -d "$APP_DIR/.git" ]]; then
    retry 3 5 sudo -u "$APP_USER" git -C "$APP_DIR" fetch origin \
      || die "Não foi possível buscar atualizações de $REPO_URL depois de 3 tentativas. Verifique a conectividade de saída deste servidor com o GitHub."
    sudo -u "$APP_USER" git -C "$APP_DIR" checkout "$BRANCH"
    sudo -u "$APP_USER" git -C "$APP_DIR" merge --ff-only "origin/$BRANCH"
    ok "Código atualizado (origin/$BRANCH)."
  else
    retry 3 5 sudo -u "$APP_USER" git clone --branch "$BRANCH" "$REPO_URL" "$APP_DIR" \
      || die "Não foi possível clonar $REPO_URL depois de 3 tentativas. Verifique a conectividade de saída deste servidor com o GitHub e se a URL/branch do repositório estão corretas (--repo/--branch)."
    ok "Código clonado em $APP_DIR."
  fi
  sudo -u "$APP_USER" mkdir -p "$APP_DIR/instance" "$APP_DIR/backups"
}

setup_python_venv() {
  info "Configurando ambiente virtual Python..."
  [[ -d "$APP_DIR/.venv" ]] || sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
  sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install --upgrade pip --quiet
  retry 3 5 sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt" --quiet \
    || die "Falha instalando dependências Python (pip) depois de 3 tentativas. Verifique a conectividade de saída deste servidor com o PyPI (pypi.org) e rode de novo."
  ok "Dependências Python instaladas."
}

build_frontend_assets() {
  # Compiles Tailwind CSS and copies the local vendor assets (htmx,
  # FontAwesome, fonts) into app/static/ — see package.json and
  # assets/copy-vendor-assets.js. Nothing here touches app/static/images/
  # (art) or app/static/js/ (hand-written game code), both already
  # committed to the repo; this only regenerates the *build output* the
  # app used to fetch from a CDN at runtime, which is why it's git-ignored
  # (see .gitignore) and has to run on every install/update instead of
  # being committed once.
  #
  # Returns non-zero on failure instead of dying directly — callers differ
  # in what should happen next (action_install just wants to abort;
  # action_update wants to roll back first; rollback_update itself is
  # already in a best-effort emergency path and shouldn't abort mid-rollback).
  info "Compilando assets do frontend (Tailwind CSS, fontes, ícones, htmx)..."
  if ! retry 3 5 sudo -u "$APP_USER" bash -c "cd '$APP_DIR' && npm ci --quiet" >>"$LOG_FILE" 2>&1; then
    err "Falha instalando dependências de frontend (npm ci) depois de 3 tentativas. Verifique a conectividade de saída deste servidor com o npm (registry.npmjs.org) — veja $LOG_FILE."
    return 1
  fi
  if ! sudo -u "$APP_USER" bash -c "cd '$APP_DIR' && npm run build --silent" >>"$LOG_FILE" 2>&1; then
    err "Falha compilando os assets do frontend (npm run build) — veja $LOG_FILE."
    return 1
  fi
  ok "Assets do frontend compilados (sem dependência de CDN em produção)."
}

generate_env_file() {
  info "Gerando .env com credenciais novas..."
  SECRET_KEY=$(gen_secret_hex 32)
  local env_file="$APP_DIR/.env"

  {
    echo "FLASK_ENV=production"
    echo "FLASK_APP=run.py"
    echo "SECRET_KEY=$SECRET_KEY"
    echo "DATABASE_URL=$DATABASE_URL"
    echo "SOCKETIO_ASYNC_MODE=eventlet"
  } >"$env_file"

  chown "$APP_USER":"$APP_USER" "$env_file"
  chmod 600 "$env_file"
  ok "Arquivo .env gerado (permissão 600, só o dono lê)."
}

run_flask_cmd() {
  # Runs a flask/python command as the app user with .env loaded, from
  # inside APP_DIR. Used by migrations, seed, backup and restore.
  sudo -u "$APP_USER" bash -c "cd '$APP_DIR' && set -a && source .env && set +a && $1"
}

run_migrations_and_seed() {
  info "Aplicando migrações do banco..."
  run_flask_cmd ".venv/bin/flask db upgrade"
  ok "Migrações aplicadas."

  if confirm "Popular o banco com o conteúdo inicial (tópicos, conquistas, itens)? Recomendado na primeira instalação." S; then
    run_flask_cmd ".venv/bin/python scripts/seed.py"
    ok "Conteúdo inicial (seed) aplicado."
  fi
}

install_systemd_units() {
  info "Instalando serviços systemd..."
  local src="$APP_DIR/deploy"
  install -m 644 "$src/math-rpg.service" /etc/systemd/system/math-rpg.service
  install -m 644 "$src/math-rpg-backup.service" /etc/systemd/system/math-rpg-backup.service
  install -m 644 "$src/math-rpg-backup.timer" /etc/systemd/system/math-rpg-backup.timer
  install -m 644 "$src/math-rpg-leaderboards@.service" "/etc/systemd/system/math-rpg-leaderboards@.service"
  install -m 644 "$src/math-rpg-leaderboards-weekly.timer" /etc/systemd/system/math-rpg-leaderboards-weekly.timer
  install -m 644 "$src/math-rpg-leaderboards-monthly.timer" /etc/systemd/system/math-rpg-leaderboards-monthly.timer
  systemctl daemon-reload
  ok "Unidades systemd instaladas."
}

configure_caddy() {
  info "Configurando Caddy (proxy reverso + TLS)..."
  mkdir -p /var/log/caddy
  local caddyfile=/etc/caddy/Caddyfile

  {
    if [[ -n "$DOMAIN" ]]; then
      echo "{"
      echo "	email $EMAIL"
      [[ "$SSL_MODE" == "zerossl" ]] && echo "	acme_ca https://acme.zerossl.com/v2/DV90"
      echo "}"
      echo
      echo "$DOMAIN {"
    else
      echo "$PUBLIC_IP {"
      echo "	tls internal"
    fi

    cat <<'INNER'
	handle_path /static/* {
		root * APP_DIR_PLACEHOLDER/app/static
		file_server
	}

	handle {
		reverse_proxy 127.0.0.1:8000 {
			header_up X-Real-IP {remote_host}
		}
	}

	encode gzip

	log {
		output file /var/log/caddy/math-rpg-access.log
		format json
	}
}
INNER
  } | sed "s#APP_DIR_PLACEHOLDER#$APP_DIR#" >"$caddyfile"

  caddy validate --config "$caddyfile" --adapter caddyfile || die "Caddyfile inválido — veja a saída acima."
  systemctl enable caddy >>"$LOG_FILE" 2>&1 || true
  systemctl reload caddy 2>/dev/null || systemctl restart caddy

  if [[ -n "$DOMAIN" ]]; then
    ok "Caddy configurado para https://$DOMAIN (TLS via $SSL_MODE)."
  else
    ok "Caddy configurado para https://$PUBLIC_IP (certificado auto-assinado — o navegador vai avisar na primeira visita, isso é esperado sem domínio)."
  fi
}

configure_firewall() {
  if ! command -v ufw >/dev/null 2>&1; then
    warn "ufw não disponível — pulando configuração de firewall."
    return
  fi
  info "Configurando firewall (ufw)..."

  local ssh_port
  ssh_port=$(awk '/^Port /{print $2; exit}' /etc/ssh/sshd_config 2>/dev/null)
  ssh_port="${ssh_port:-22}"

  ufw allow "${ssh_port}/tcp" comment 'SSH' >/dev/null
  ufw allow 80/tcp comment 'HTTP' >/dev/null
  ufw allow 443/tcp comment 'HTTPS' >/dev/null

  if ufw status | grep -q "Status: active"; then
    ok "Firewall já ativo — regras atualizadas (SSH $ssh_port, HTTP, HTTPS liberados)."
  else
    warn "Ativando o firewall. Porta SSH liberada antes de ativar: $ssh_port."
    ufw --force enable >/dev/null
    ok "Firewall ativado (SSH $ssh_port, HTTP 80, HTTPS 443 liberados; todo o resto bloqueado)."
  fi
}

install_timers() {
  info "Ativando rotinas agendadas (backup diário, leaderboards semanal/mensal)..."
  systemctl enable --now math-rpg-backup.timer >>"$LOG_FILE" 2>&1
  systemctl enable --now math-rpg-leaderboards-weekly.timer >>"$LOG_FILE" 2>&1
  systemctl enable --now math-rpg-leaderboards-monthly.timer >>"$LOG_FILE" 2>&1
  ok "Rotinas agendadas ativas."
}

start_app_service() {
  info "Iniciando a aplicação..."
  systemctl enable --now math-rpg >>"$LOG_FILE" 2>&1
  ok "Serviço math-rpg iniciado."
}

health_check_with_retries() {
  local tries=0
  until curl -fsS --max-time 3 "$HEALTH_URL_LOCAL" >/dev/null 2>&1; do
    tries=$((tries + 1))
    (( tries >= 15 )) && return 1
    sleep 2
  done
  return 0
}

final_health_check() {
  info "Verificando se a aplicação está no ar..."
  if health_check_with_retries; then
    ok "Aplicação respondendo em $HEALTH_URL_LOCAL."
  else
    warn "A aplicação não respondeu a tempo. Veja: journalctl -u math-rpg -n 50"
    return 1
  fi

  if [[ -n "$DOMAIN" ]]; then
    info "Testando HTTPS público (a primeira emissão do certificado pode levar até um minuto)..."
    if curl -fsS --max-time 25 "https://$DOMAIN/health" >/dev/null 2>&1; then
      ok "https://$DOMAIN/health respondendo."
    else
      warn "https://$DOMAIN ainda não respondeu — confira: journalctl -u caddy -n 50"
    fi
  fi
}

print_credentials_summary() {
  local url
  if [[ -n "$DOMAIN" ]]; then
    url="https://$DOMAIN"
  else
    url="https://$PUBLIC_IP (certificado auto-assinado — o navegador vai avisar, isso é esperado)"
  fi

  {
    echo "==============================================================="
    echo " Matematica RPG — credenciais geradas nesta instalação"
    echo " $(date '+%Y-%m-%d %H:%M:%S')"
    echo "==============================================================="
    echo " URL:            $url"
    echo " SECRET_KEY:     $SECRET_KEY"
    if [[ "$DB_ENGINE" == "postgres" ]]; then
      echo " Banco de dados: $DB_NAME"
      echo " Usuário do BD:  $DB_USER"
      echo " Senha do BD:    $DB_PASSWORD"
      echo " DATABASE_URL:   $DATABASE_URL"
    else
      echo " Banco de dados: SQLite ($APP_DIR/instance/dev.db)"
    fi
    echo "==============================================================="
    echo " Estas informações também foram salvas em:"
    echo "   $CRED_FILE  (permissão 600, só root lê)"
    echo " Recomendado: copie para um cofre de senhas e apague esse"
    echo " arquivo depois. Nada disto é enviado a lugar nenhum."
    echo "==============================================================="
  } | tee "$CRED_FILE"
  chmod 600 "$CRED_FILE"
}

action_install() {
  info "Iniciando instalação da Matematica RPG..."
  detect_environment_warnings
  check_disk_space
  check_network_reachability strict
  gather_install_inputs
  validate_install_inputs
  print_install_plan
  confirm "Confirmar e iniciar a instalação?" S || die "Instalação cancelada."

  install_system_packages
  setup_database
  create_system_user
  fetch_code
  setup_python_venv
  build_frontend_assets || die "Falha compilando os assets do frontend — veja $LOG_FILE."
  generate_env_file
  run_migrations_and_seed
  install_systemd_units
  configure_caddy
  configure_firewall
  install_timers
  start_app_service
  final_health_check || true
  save_installer_state
  print_credentials_summary
  ok "Instalação concluída."
}

# ---------------------------------------------------------------------------
# Ação: atualizar (com backup e rollback automáticos)
# ---------------------------------------------------------------------------
run_backup() {
  run_flask_cmd ".venv/bin/python scripts/backup_db.py --out '$APP_DIR/backups'"
}

rollback_update() {
  local target_commit="$1"
  warn "Revertendo código para $target_commit..."
  sudo -u "$APP_USER" git -C "$APP_DIR" checkout "$BRANCH"
  sudo -u "$APP_USER" git -C "$APP_DIR" reset --hard "$target_commit"
  sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt" --quiet
  build_frontend_assets || warn "Falha recompilando os assets do frontend durante o rollback — a aplicação pode subir com CSS/fontes desatualizados. Rode 'npm run build' manualmente em $APP_DIR depois."

  info "Restaurando o banco a partir do backup pré-atualização..."
  if ! run_flask_cmd ".venv/bin/python scripts/restore_db.py --latest --dir '$APP_DIR/backups' --yes"; then
    warn "A restauração automática do banco falhou — restaure manualmente com a opção 'Restaurar backup'."
  fi

  systemctl restart math-rpg
}

action_update() {
  [[ -d "$APP_DIR/.git" ]] || die "Nenhuma instalação encontrada em $APP_DIR. Rode 'Instalar' primeiro."

  check_network_reachability strict

  info "Verificando alterações locais não commitadas em $APP_DIR..."
  if ! sudo -u "$APP_USER" git -C "$APP_DIR" diff --quiet -- . \
     || ! sudo -u "$APP_USER" git -C "$APP_DIR" diff --cached --quiet -- .; then
    die "Há alterações não commitadas em $APP_DIR (git status). Resolva manualmente antes de atualizar — a atualização automática não sobrescreve isso sozinha."
  fi

  local old_commit new_commit
  old_commit=$(sudo -u "$APP_USER" git -C "$APP_DIR" rev-parse HEAD)
  info "Versão atual: $old_commit"

  info "Fazendo backup de segurança do banco antes de atualizar..."
  run_backup || die "O backup pré-atualização falhou — atualização abortada por segurança (nada foi alterado)."

  info "Buscando atualizações de origin/$BRANCH..."
  retry 3 5 sudo -u "$APP_USER" git -C "$APP_DIR" fetch origin \
    || die "Não foi possível buscar atualizações de origin/$BRANCH depois de 3 tentativas. Verifique a conectividade de saída deste servidor com o GitHub — nada foi alterado."
  if ! sudo -u "$APP_USER" git -C "$APP_DIR" merge --ff-only "origin/$BRANCH"; then
    die "Não foi possível avançar automaticamente (fast-forward) para origin/$BRANCH — histórico divergente. Nada foi alterado; resolva manualmente."
  fi
  new_commit=$(sudo -u "$APP_USER" git -C "$APP_DIR" rev-parse HEAD)

  if [[ "$new_commit" == "$old_commit" ]]; then
    ok "Já estava na versão mais recente ($old_commit). Nada para atualizar."
    return
  fi
  info "Atualizando código: $old_commit -> $new_commit"

  if ! retry 3 5 sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt" --quiet; then
    err "Falha instalando dependências Python (pip) depois de 3 tentativas."
    rollback_update "$old_commit"
    die "Atualização abortada e revertida com segurança (código e banco voltaram para $old_commit). Verifique a conectividade de saída deste servidor com o PyPI (pypi.org)."
  fi
  if ! build_frontend_assets; then
    err "Falha compilando os assets do frontend."
    rollback_update "$old_commit"
    die "Atualização abortada e revertida com segurança (código e banco voltaram para $old_commit)."
  fi

  info "Aplicando migrações do banco..."
  if ! run_flask_cmd ".venv/bin/flask db upgrade"; then
    err "Migração falhou."
    rollback_update "$old_commit"
    die "Atualização abortada e revertida com segurança (código e banco voltaram para $old_commit)."
  fi

  info "Reiniciando a aplicação..."
  systemctl restart math-rpg

  if health_check_with_retries; then
    ok "Atualização concluída com sucesso: $old_commit -> $new_commit."
  else
    err "A aplicação não respondeu após a atualização."
    rollback_update "$old_commit"
    if health_check_with_retries; then
      warn "Revertido com sucesso para $old_commit. A versão $new_commit precisa ser investigada antes de tentar de novo."
    else
      die "A aplicação continua fora do ar mesmo após reverter para $old_commit. Intervenção manual necessária — veja: journalctl -u math-rpg -n 80"
    fi
  fi
}

# ---------------------------------------------------------------------------
# Ação: status
# ---------------------------------------------------------------------------
action_status() {
  echo
  echo "==================== Serviços ===================="
  local svc active enabled
  for svc in math-rpg caddy postgresql math-rpg-backup.timer math-rpg-leaderboards-weekly.timer math-rpg-leaderboards-monthly.timer; do
    systemctl cat "$svc" &>/dev/null || continue
    active=$(systemctl is-active "$svc" 2>/dev/null || echo "?")
    enabled=$(systemctl is-enabled "$svc" 2>/dev/null || echo "?")
    printf ' %-40s ativo=%-10s habilitado=%s\n' "$svc" "$active" "$enabled"
  done
  echo "===================================================="

  if [[ -d "$APP_DIR/.git" ]]; then
    echo
    echo "Versão atual: $(sudo -u "$APP_USER" git -C "$APP_DIR" rev-parse --short HEAD 2>/dev/null) ($(sudo -u "$APP_USER" git -C "$APP_DIR" log -1 --format=%cd --date=short 2>/dev/null))"
  fi
  if [[ -n "$DOMAIN" ]]; then
    echo "Endereço:     https://$DOMAIN"
  elif [[ -f /etc/caddy/Caddyfile ]]; then
    echo "Endereço:     https://$(detect_public_ip || echo '?') (IP, certificado auto-assinado)"
  fi

  echo
  echo -n "Saúde da aplicação ($HEALTH_URL_LOCAL): "
  if curl -fsS --max-time 3 "$HEALTH_URL_LOCAL" 2>/dev/null; then
    echo " -> OK"
  else
    echo "-> SEM RESPOSTA"
  fi

  echo
  echo "Backups em $APP_DIR/backups:"
  if [[ -d "$APP_DIR/backups" ]]; then
    ls -lh "$APP_DIR/backups" 2>/dev/null | tail -n 5
  else
    echo "  (nenhum ainda)"
  fi

  echo
  echo "Próximas execuções agendadas:"
  systemctl list-timers 'math-rpg-*' --no-pager 2>/dev/null || echo "  (nenhum timer instalado)"
  echo
}

# ---------------------------------------------------------------------------
# Ação: reiniciar
# ---------------------------------------------------------------------------
action_restart() {
  [[ -d "$APP_DIR" ]] || die "Nenhuma instalação encontrada em $APP_DIR."
  info "Reiniciando a aplicação (systemctl restart math-rpg)..."
  systemctl restart math-rpg
  if health_check_with_retries; then
    ok "Aplicação reiniciada e respondendo normalmente."
  else
    die "A aplicação foi reiniciada mas não respondeu em $HEALTH_URL_LOCAL. Veja: journalctl -u math-rpg -n 50"
  fi
}

# ---------------------------------------------------------------------------
# Ações: backup / restaurar
# ---------------------------------------------------------------------------
action_backup() {
  [[ -d "$APP_DIR" ]] || die "Nenhuma instalação encontrada em $APP_DIR."
  info "Fazendo backup do banco de dados..."
  if run_backup; then
    ok "Backup concluído. Arquivos em $APP_DIR/backups"
  else
    die "Backup falhou — veja a saída acima."
  fi
}

action_restore() {
  [[ -d "$APP_DIR" ]] || die "Nenhuma instalação encontrada em $APP_DIR."
  echo "Backups disponíveis em $APP_DIR/backups:"
  ls -lh "$APP_DIR/backups" 2>/dev/null || warn "Nenhum backup encontrado."
  local choice
  choice=$(ask "Nome do arquivo de backup (dentro de $APP_DIR/backups) ou 'latest' para o mais recente" "latest")

  if [[ "$choice" == "latest" ]]; then
    run_flask_cmd ".venv/bin/python scripts/restore_db.py --latest --dir '$APP_DIR/backups'"
  else
    run_flask_cmd ".venv/bin/python scripts/restore_db.py '$APP_DIR/backups/$choice' --dir '$APP_DIR/backups'"
  fi
}

# ---------------------------------------------------------------------------
# Ação: verificar ambiente (diagnóstico isolado, não muda nada no servidor)
# ---------------------------------------------------------------------------
action_check_environment() {
  echo
  echo "==================== Verificação de ambiente ===================="
  echo

  echo "Sistema operacional:"
  if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    case "${ID:-}" in
      ubuntu|debian) ok "  ${PRETTY_NAME:-$ID} — suportado." ;;
      *) warn "  ${PRETTY_NAME:-desconhecido} — este instalador foi testado em Ubuntu/Debian." ;;
    esac
  else
    warn "  Não foi possível detectar (/etc/os-release ausente)."
  fi

  echo
  echo "Privilégios:"
  if [[ $EUID -eq 0 ]]; then
    ok "  Rodando como root."
  else
    warn "  NÃO está rodando como root — rode com 'sudo bash install.sh'."
  fi

  echo
  echo "Container / ambiente de desenvolvimento:"
  if [[ -n "${CODESPACES:-}" || -n "${REMOTE_CONTAINERS:-}" || -f /.dockerenv || -n "${DEVCONTAINER:-}" ]]; then
    warn "  Detectado ambiente de container de desenvolvimento (Codespaces/Dev Container/Docker) — não recomendado para produção. Use uma VM/VPS de verdade."
  else
    ok "  Nenhum sinal de container de desenvolvimento efêmero."
  fi

  echo
  echo "systemd (necessário para o serviço da aplicação, Caddy e timers):"
  if [[ -d /run/systemd/system ]]; then
    ok "  systemd rodando como PID 1."
  else
    warn "  systemd NÃO parece estar rodando como PID 1 (/run/systemd/system ausente) — o serviço da aplicação, Caddy e os timers de backup/leaderboard vão falhar."
  fi

  echo
  echo "Espaço em disco:"
  local avail_kb
  avail_kb=$(df -Pk "$APP_DIR" 2>/dev/null | awk 'NR==2{print $4}')
  [[ -z "$avail_kb" ]] && avail_kb=$(df -Pk / 2>/dev/null | awk 'NR==2{print $4}')
  if [[ -n "$avail_kb" ]]; then
    if (( avail_kb < 1048576 )); then
      warn "  $(( avail_kb / 1024 ))MB livres — menos de 1GB, pode ser insuficiente."
    else
      ok "  $(( avail_kb / 1024 / 1024 ))GB livres."
    fi
  else
    warn "  Não foi possível checar."
  fi

  echo
  check_network_reachability report

  echo
  echo "===================================================================="
  echo
}

# ---------------------------------------------------------------------------
# Ações: migrar o jogo para outro servidor
# ---------------------------------------------------------------------------
# Migração = mover os DADOS (o banco) para um servidor novo — não o .env
# (SECRET_KEY, senha do banco, TLS) nem a configuração do Caddy, que são
# sempre gerados frescos por uma instalação normal (--action=install) no
# servidor de destino, já corretos para o domínio/IP/banco DAQUELE
# servidor. Tentar copiar o .env de um servidor para o outro tende a criar
# mais problemas do que resolve (DATABASE_URL apontando pro host errado,
# SECRET_KEY compartilhada entre dois processos independentes) — os dados
# do jogo (usuários, progresso, itens, chat, etc.) estão todos no banco,
# então é só ele que realmente precisa viajar.
action_migrate_export() {
  [[ -d "$APP_DIR" ]] || die "Nenhuma instalação encontrada em $APP_DIR."
  info "Preparando pacote de migração..."

  local ts export_dir latest_backup tarball
  ts=$(date -u +%Y%m%dT%H%M%SZ)
  export_dir=$(mktemp -d)

  info "Gerando um backup fresco do banco de dados..."
  run_backup || { rm -rf "$export_dir"; die "O backup falhou — migração abortada (nada foi gerado)."; }

  latest_backup=$(ls -t "$APP_DIR/backups"/*.sql.gz "$APP_DIR/backups"/dev-*.db 2>/dev/null | head -n1 || true)
  [[ -n "$latest_backup" ]] || { rm -rf "$export_dir"; die "Não encontrei o backup recém-criado em $APP_DIR/backups — algo está errado."; }
  cp "$latest_backup" "$export_dir/"

  {
    echo "exported_at=$ts"
    echo "db_engine=$DB_ENGINE"
    echo "source_commit=$(sudo -u "$APP_USER" git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || echo desconhecido)"
    echo "backup_file=$(basename "$latest_backup")"
  } >"$export_dir/migration-info.txt"

  mkdir -p "$APP_DIR/backups/migrations"
  tarball="$APP_DIR/backups/migrations/math-rpg-migration-${ts}.tar.gz"
  tar -C "$export_dir" -czf "$tarball" .
  rm -rf "$export_dir"
  chown "$APP_USER":"$APP_USER" "$tarball"
  chmod 600 "$tarball"

  ok "Pacote de migração criado: $tarball"
  echo
  echo "==================== Próximos passos ===================="
  echo " 1) Copie o arquivo para o servidor novo, por exemplo:"
  echo "      scp $tarball usuario@servidor-novo:/tmp/"
  echo
  echo " 2) No servidor NOVO, instale a aplicação normalmente primeiro"
  echo "    (gera SECRET_KEY, banco e TLS próprios daquele servidor):"
  echo "      sudo bash install.sh --action=install"
  echo
  echo " 3) Ainda no servidor novo, importe os dados:"
  echo "      sudo bash install.sh --action=migrate-import --file=/tmp/$(basename "$tarball")"
  echo "============================================================"
}

action_migrate_import() {
  [[ -d "$APP_DIR/.git" ]] || die "Nenhuma instalação encontrada em $APP_DIR. Instale a aplicação neste servidor primeiro (--action=install) — a importação só troca os DADOS de uma instalação já funcionando."

  [[ -n "$MIGRATION_FILE" ]] || MIGRATION_FILE=$(ask "Caminho do arquivo .tar.gz de migração")
  [[ -f "$MIGRATION_FILE" ]] || die "Arquivo não encontrado: $MIGRATION_FILE"

  local extract_dir
  extract_dir=$(mktemp -d)

  tar -xzf "$MIGRATION_FILE" -C "$extract_dir" || { rm -rf "$extract_dir"; die "Não foi possível extrair $MIGRATION_FILE — arquivo corrompido ou não é um pacote de migração válido."; }
  [[ -f "$extract_dir/migration-info.txt" ]] || { rm -rf "$extract_dir"; die "Pacote de migração inválido: migration-info.txt ausente."; }

  local exported_at db_engine source_commit backup_file
  # shellcheck disable=SC1091
  . "$extract_dir/migration-info.txt"
  info "Pacote de migração: exportado em ${exported_at:-desconhecido}, banco=${db_engine:-desconhecido}, commit de origem=${source_commit:-desconhecido}."

  if [[ -n "${db_engine:-}" && "$db_engine" != "$DB_ENGINE" ]]; then
    warn "O pacote foi exportado de um banco '$db_engine', mas este servidor está configurado para '$DB_ENGINE'."
    confirm "Continuar mesmo assim? (a restauração provavelmente vai falhar)" N || { rm -rf "$extract_dir"; die "Importação cancelada."; }
  fi

  [[ -n "${backup_file:-}" ]] || { rm -rf "$extract_dir"; die "Pacote de migração inválido: referência ao arquivo de backup ausente."; }
  local backup_path="$extract_dir/$backup_file"
  [[ -f "$backup_path" ]] || { rm -rf "$extract_dir"; die "Arquivo de backup referenciado ($backup_file) não encontrado dentro do pacote."; }

  warn "Isso vai SOBRESCREVER o banco de dados atual deste servidor com os dados do pacote de migração."
  confirm "Continuar?" N || { rm -rf "$extract_dir"; die "Importação cancelada."; }

  info "Fazendo um backup de segurança do banco atual antes de importar..."
  run_backup || { rm -rf "$extract_dir"; die "O backup de segurança falhou — importação abortada por segurança (nada foi alterado)."; }

  cp "$backup_path" "$APP_DIR/backups/"
  chown "$APP_USER":"$APP_USER" "$APP_DIR/backups/$(basename "$backup_path")"
  rm -rf "$extract_dir"

  info "Restaurando os dados importados..."
  if ! run_flask_cmd ".venv/bin/python scripts/restore_db.py '$APP_DIR/backups/$(basename "$backup_path")' --dir '$APP_DIR/backups' --yes"; then
    die "A restauração falhou. O backup de segurança feito antes de importar continua disponível em $APP_DIR/backups (restaure com a opção 'Restaurar backup')."
  fi

  info "Aplicando migrações do banco (garantir que o esquema está atualizado)..."
  run_flask_cmd ".venv/bin/flask db upgrade" || warn "Falha ao aplicar migrações do banco depois de importar — verifique manualmente com 'flask db upgrade'."

  info "Reiniciando a aplicação..."
  systemctl restart math-rpg

  if health_check_with_retries; then
    ok "Migração importada com sucesso — aplicação respondendo normalmente."
  else
    warn "A aplicação não respondeu depois de importar. Veja: journalctl -u math-rpg -n 50"
  fi
}

# ---------------------------------------------------------------------------
# Menu / dispatcher
# ---------------------------------------------------------------------------
run_action() {
  case "$1" in
    install)         action_install ;;
    update)          action_update ;;
    status)          action_status ;;
    restart)         action_restart ;;
    backup)          action_backup ;;
    restore)         action_restore ;;
    check-env)       action_check_environment ;;
    migrate-export)  action_migrate_export ;;
    migrate-import)  action_migrate_import ;;
    *) die "Ação desconhecida: $1 (use install|update|status|restart|backup|restore|check-env|migrate-export|migrate-import)" ;;
  esac
}

main_menu() {
  while true; do
    echo
    echo "==================== Matematica RPG — instalador ===================="
    if [[ -d "$APP_DIR/.git" ]]; then
      echo " Instalação detectada em $APP_DIR"
    else
      echo " Nenhuma instalação detectada em $APP_DIR"
    fi
    echo "========================================================================"
    echo " 1) Instalar (ou reinstalar) a aplicação"
    echo " 2) Atualizar a aplicação  (backup + rollback automático se algo falhar)"
    echo " 3) Ver status dos serviços"
    echo " 4) Reiniciar a aplicação"
    echo " 5) Fazer backup do banco agora"
    echo " 6) Restaurar um backup"
    echo " 7) Verificar ambiente (rede, systemd, espaço em disco)"
    echo " 8) Migrar para outro servidor — exportar pacote de migração"
    echo " 9) Migrar para outro servidor — importar pacote de migração"
    echo " 0) Sair"
    echo
    local choice
    read -r -p "Escolha uma opção: " choice || { echo; exit 0; }
    case "$choice" in
      1) run_action install ;;
      2) run_action update ;;
      3) run_action status ;;
      4) run_action restart ;;
      5) run_action backup ;;
      6) run_action restore ;;
      7) run_action check-env ;;
      8) run_action migrate-export ;;
      9) run_action migrate-import ;;
      0) exit 0 ;;
      *) warn "Opção inválida." ;;
    esac
  done
}

main() {
  require_root
  check_os
  mkdir -p "$(dirname "$LOG_FILE")"
  touch "$LOG_FILE"
  chmod 600 "$LOG_FILE"

  load_installer_state

  if [[ -n "$ACTION" ]]; then
    run_action "$ACTION"
    exit 0
  fi

  if [[ ! -t 0 ]]; then
    die "Entrada não é um terminal interativo. Baixe o script e rode-o diretamente (não via 'curl | bash'), ou use --action=... com as flags necessárias (--help)."
  fi

  main_menu
}

main "$@"
