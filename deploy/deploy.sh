#!/usr/bin/env bash
#
# Memora — one-shot deploy for a server that already runs another project.
#
# It assumes nothing except Docker and git. It is idempotent: run it again to
# redeploy, and it will reuse the secrets and the Caddy block it wrote the first time.
#
#   curl -fsSL https://raw.githubusercontent.com/oktamov/memora/main/deploy/deploy.sh | bash
#
# What it does NOT do: publish any host port, restart the other project, or touch its
# containers. The only shared thing is the existing Caddy, which gains one site block.

set -Eeuo pipefail

REPO="${MEMORA_REPO:-https://github.com/oktamov/memora.git}"
BRANCH="${MEMORA_BRANCH:-main}"
APP_DIR="${MEMORA_DIR:-/opt/memora}"
DOMAIN="${MEMORA_DOMAIN:-memora.uz}"
CADDY_CONTAINER="${CADDY_CONTAINER:-dublyaj-caddy}"
EDGE_NETWORK="memora_edge"

BEGIN_MARK="# >>> memora begin >>>"
END_MARK="# <<< memora end <<<"

RED=$'\033[31m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; BLUE=$'\033[34m'; DIM=$'\033[2m'; OFF=$'\033[0m'
step()  { printf '\n%s==>%s %s\n' "$BLUE" "$OFF" "$*"; }
ok()    { printf '%s  ✓%s %s\n' "$GREEN" "$OFF" "$*"; }
warn()  { printf '%s  !%s %s\n' "$YELLOW" "$OFF" "$*"; }
die()   { printf '\n%s  ✗ %s%s\n\n' "$RED" "$*" "$OFF" >&2; exit 1; }

trap 'die "Failed on line $LINENO. Nothing else was changed."' ERR

# ---------------------------------------------------------------- preflight ----

step "Checking the host"

command -v docker >/dev/null || die "Docker is not installed."
docker info >/dev/null 2>&1 || die "Cannot talk to the Docker daemon. Try with sudo."

# Root is the usual case, but a rootless-docker host with a writable target is fine
# too, so the requirement is stated as what actually has to be true.
parent_dir="$(dirname "$APP_DIR")"
mkdir -p "$parent_dir" 2>/dev/null || true
[[ -w "$parent_dir" || -w "$APP_DIR" ]] || die "Cannot write to $APP_DIR. Re-run with sudo."
docker compose version >/dev/null 2>&1 || die "The docker compose plugin is missing."
command -v git >/dev/null || die "git is not installed."
ok "docker $(docker version --format '{{.Server.Version}}') · compose $(docker compose version --short)"

# The whole point of this layout: never fight the other project for a port.
for port in 80 443 8000; do
  if ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN; then
    ok "port $port is in use — Memora will not touch it"
  fi
done

if ! docker ps --format '{{.Names}}' | grep -qx "$CADDY_CONTAINER"; then
  die "Caddy container '$CADDY_CONTAINER' is not running.
     Set CADDY_CONTAINER=<name> and re-run, e.g.
       CADDY_CONTAINER=my-caddy bash deploy.sh"
fi
ok "found the reverse proxy: $CADDY_CONTAINER"

# DNS is a warning, not a failure: Caddy will simply retry the certificate later.
server_ip="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || echo '')"
domain_ip="$(getent hosts "$DOMAIN" 2>/dev/null | awk 'NR==1{print $1}' || echo '')"
if [[ -n "$server_ip" && -n "$domain_ip" && "$server_ip" != "$domain_ip" ]]; then
  warn "$DOMAIN resolves to $domain_ip but this server is $server_ip."
  warn "TLS will keep failing until the A record points here."
elif [[ -n "$domain_ip" ]]; then
  ok "$DOMAIN → $domain_ip"
else
  warn "$DOMAIN does not resolve yet. Point its A record at $server_ip."
fi

# ------------------------------------------------------------------- source ----

step "Fetching the code"

if [[ -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" fetch --quiet origin "$BRANCH"
  git -C "$APP_DIR" reset --hard --quiet "origin/$BRANCH"
  ok "updated $APP_DIR to $(git -C "$APP_DIR" rev-parse --short HEAD)"
else
  mkdir -p "$(dirname "$APP_DIR")"
  git clone --quiet --branch "$BRANCH" "$REPO" "$APP_DIR"
  ok "cloned into $APP_DIR"
fi
cd "$APP_DIR"

# ------------------------------------------------------------------ secrets ----

step "Preparing secrets"

ENV_FILE="$APP_DIR/.env"

# Keep whatever is already there; only fill in what is missing. This is what makes a
# second run safe — rotating JWT_SECRET would sign every user out.
read_env() { [[ -f "$ENV_FILE" ]] && sed -n "s/^$1=\(.*\)$/\1/p" "$ENV_FILE" | tail -1 || true; }
gen() { openssl rand -hex 32; }

POSTGRES_PASSWORD="$(read_env POSTGRES_PASSWORD)"; POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$(gen)}"
JWT_SECRET="$(read_env JWT_SECRET)";               JWT_SECRET="${JWT_SECRET:-$(gen)}"
WEBHOOK_SECRET="$(read_env TELEGRAM_WEBHOOK_SECRET)"; WEBHOOK_SECRET="${WEBHOOK_SECRET:-$(gen)}"
WEBHOOK_PATH="$(read_env TELEGRAM_WEBHOOK_PATH_SECRET)"; WEBHOOK_PATH="${WEBHOOK_PATH:-$(openssl rand -hex 16)}"

# Provider credentials come from the environment, else from the existing file, else
# empty — the app boots either way and falls back to fixture providers.
BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-$(read_env TELEGRAM_BOT_TOKEN)}"
GEMINI_KEY="${GEMINI_API_KEY:-$(read_env GEMINI_API_KEY)}"
AZURE_KEY="${AZURE_TRANSLATOR_KEY:-$(read_env AZURE_TRANSLATOR_KEY)}"
AZURE_REGION="${AZURE_TRANSLATOR_REGION:-$(read_env AZURE_TRANSLATOR_REGION)}"

umask 077
cat > "$ENV_FILE" <<ENVFILE
# Written by deploy/deploy.sh. Secrets are generated once and preserved on redeploy.
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
JWT_SECRET=$JWT_SECRET

TELEGRAM_BOT_TOKEN=$BOT_TOKEN
TELEGRAM_WEBHOOK_SECRET=$WEBHOOK_SECRET
TELEGRAM_WEBHOOK_PATH_SECRET=$WEBHOOK_PATH
MINI_APP_URL=https://$DOMAIN

GEMINI_API_KEY=$GEMINI_KEY
AZURE_TRANSLATOR_KEY=$AZURE_KEY
AZURE_TRANSLATOR_REGION=$AZURE_REGION

UZ_PREFER_LLM=true
DAILY_PROVIDER_BUDGET=5000
ENV=prod
LOG_LEVEL=INFO
CORS_ORIGINS=["https://$DOMAIN"]
ENVFILE
umask 022
ok "secrets in $ENV_FILE (0600)"

[[ -n "$BOT_TOKEN" ]] || warn "TELEGRAM_BOT_TOKEN is empty — the bot stays off, the Mini App still works."
[[ -n "$GEMINI_KEY$AZURE_KEY" ]] || warn "No provider key — lookups fall back to fixture data."

# -------------------------------------------------------------------- build ----

step "Building and starting Memora"

docker network inspect "$EDGE_NETWORK" >/dev/null 2>&1 || {
  docker network create "$EDGE_NETWORK" >/dev/null
  ok "created network $EDGE_NETWORK"
}

docker compose -f docker-compose.prod.yml build --quiet
docker compose -f docker-compose.prod.yml up -d --remove-orphans
ok "containers up"

# ------------------------------------------------------------------- caddy -----

step "Wiring the existing Caddy"

if docker network inspect "$EDGE_NETWORK" --format '{{range .Containers}}{{.Name}} {{end}}' \
   | grep -qw "$CADDY_CONTAINER"; then
  ok "$CADDY_CONTAINER is already on $EDGE_NETWORK"
else
  docker network connect "$EDGE_NETWORK" "$CADDY_CONTAINER"
  ok "connected $CADDY_CONTAINER to $EDGE_NETWORK"
fi

# Find the Caddyfile the running container actually uses, then its host path.
# Docker's Go templates have no arithmetic, so the argument after --config is picked
# out in bash rather than in the template.
caddy_cfg="$(docker inspect "$CADDY_CONTAINER" --format '{{json .Config.Cmd}}' 2>/dev/null \
  | tr ',' '\n' | grep -A1 -- '--config' | tail -1 | tr -d '[]" ' || true)"
[[ "$caddy_cfg" == /* ]] || caddy_cfg="/etc/caddy/Caddyfile"
ok "Caddy config: $caddy_cfg"

host_cfg="$(docker inspect "$CADDY_CONTAINER" --format \
  "{{range .Mounts}}{{if eq .Destination \"$caddy_cfg\"}}{{.Source}}{{end}}{{end}}")"

if [[ -z "$host_cfg" ]]; then
  # The file is not bind-mounted on its own; try the directory containing it.
  caddy_dir="$(dirname "$caddy_cfg")"
  mount_dir="$(docker inspect "$CADDY_CONTAINER" --format \
    "{{range .Mounts}}{{if eq .Destination \"$caddy_dir\"}}{{.Source}}{{end}}{{end}}")"
  [[ -n "$mount_dir" ]] && host_cfg="$mount_dir/$(basename "$caddy_cfg")"
fi

append_block() {
  local target="$1"
  {
    printf '\n%s\n' "$BEGIN_MARK"
    cat "$APP_DIR/deploy/Caddyfile.memora"
    printf '%s\n' "$END_MARK"
  } >> "$target"
}

if [[ -n "$host_cfg" ]]; then
  # Appending Caddyfile syntax to a JSON config would corrupt it. Refuse instead.
  if head -c 1 "$host_cfg" | grep -q '{' && grep -q '"apps"' "$host_cfg"; then
    warn "$caddy_cfg is a JSON config, not a Caddyfile — refusing to append to it."
    host_cfg=""
  fi
fi

if [[ -n "$host_cfg" && -w "$host_cfg" ]]; then
  backup="$host_cfg.memora-backup.$(date +%Y%m%d%H%M%S)"
  cp "$host_cfg" "$backup"

  # Strip any previous managed block so a redeploy replaces it instead of stacking a
  # second copy. awk, not sed: the markers contain regex metacharacters, and
  # hand-escaping them is how another project's config quietly gets mangled.
  if grep -qF "$BEGIN_MARK" "$host_cfg"; then
    awk -v b="$BEGIN_MARK" -v e="$END_MARK" '
      $0 == b { skip = 1; next }
      $0 == e { skip = 0; next }
      !skip   { print }
    ' "$backup" > "$host_cfg"
  fi
  append_block "$host_cfg"

  # Validate before reloading: a broken Caddyfile would take the OTHER project down.
  if docker exec "$CADDY_CONTAINER" caddy validate --adapter caddyfile --config "$caddy_cfg" >/dev/null 2>&1 \
     || docker exec "$CADDY_CONTAINER" caddy validate --config "$caddy_cfg" >/dev/null 2>&1; then
    docker exec "$CADDY_CONTAINER" caddy reload --config "$caddy_cfg" >/dev/null
    ok "Caddy reloaded — no restart, the other project never dropped a request"
    ok "backup: $backup"
  else
    cp "$backup" "$host_cfg"
    die "The Caddyfile did not validate. Restored $backup; the other project is untouched."
  fi
else
  warn "Could not write to the Caddyfile automatically."
  warn "Add this block to $caddy_cfg yourself, then: docker exec $CADDY_CONTAINER caddy reload --config $caddy_cfg"
  printf '%s\n' "$DIM"
  cat "$APP_DIR/deploy/Caddyfile.memora"
  printf '%s\n' "$OFF"
fi

# ------------------------------------------------------------------- verify ----

step "Verifying"

for attempt in $(seq 1 30); do
  if docker exec memora-api python -c \
     "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)" 2>/dev/null; then
    ok "API is healthy"
    break
  fi
  [[ $attempt -eq 30 ]] && die "API did not become healthy. Logs:
     docker compose -f $APP_DIR/docker-compose.prod.yml logs api --tail=80"
  sleep 3
done

if curl -fsS --max-time 20 "https://$DOMAIN/health" >/dev/null 2>&1; then
  ok "https://$DOMAIN/health responds"
  https_ready=1
else
  warn "https://$DOMAIN is not answering yet — Caddy may still be issuing the certificate."
  warn "Give it a minute, then: curl -sS https://$DOMAIN/health"
  https_ready=0
fi

if docker compose -f docker-compose.prod.yml logs api --tail=200 2>&1 | grep -q '"level": "ERROR"'; then
  warn "There are ERROR lines in the API log — check them:"
  warn "  docker compose -f $APP_DIR/docker-compose.prod.yml logs api | grep ERROR"
else
  ok "no ERROR lines in the API log"
fi

# -------------------------------------------------------------------- done -----

printf '\n%s══ Memora is deployed ══%s\n\n' "$GREEN" "$OFF"
printf '  Mini App   https://%s\n' "$DOMAIN"
printf '  API docs   https://%s/docs\n' "$DOMAIN"
printf '  Webhook    https://%s/telegram/webhook/%s\n' "$DOMAIN" "$WEBHOOK_PATH"
printf '  Directory  %s\n' "$APP_DIR"
printf '\n  Logs       docker compose -f %s/docker-compose.prod.yml logs -f api\n' "$APP_DIR"
printf '  Redeploy   bash %s/deploy/deploy.sh\n' "$APP_DIR"

if [[ -z "$BOT_TOKEN" ]]; then
  printf '\n%sNext:%s add the bot token, then redeploy:\n' "$YELLOW" "$OFF"
  printf '  TELEGRAM_BOT_TOKEN=... bash %s/deploy/deploy.sh\n' "$APP_DIR"
else
  printf '\n%sIn BotFather:%s /setmenubutton → https://%s\n' "$YELLOW" "$OFF" "$DOMAIN"
  [[ $https_ready -eq 1 ]] && printf '  The webhook registers itself on startup.\n'
fi
printf '\n'
