#!/usr/bin/env bash
#
# Ship the working tree straight to the server over SSH — no GitHub involved.
#
# Use this when the repository is private, or when you want to deploy local changes
# that are not pushed yet. It copies the code, then runs deploy.sh there.
#
#   ./deploy/ship.sh root@your-server
#   TELEGRAM_BOT_TOKEN=... ./deploy/ship.sh root@your-server

set -Eeuo pipefail

TARGET="${1:-}"
APP_DIR="${MEMORA_DIR:-/opt/memora}"
DOMAIN="${MEMORA_DOMAIN:-memora.uz}"
CADDY_CONTAINER="${CADDY_CONTAINER:-dublyaj-caddy}"

[[ -n "$TARGET" ]] || {
  echo "usage: $0 user@host" >&2
  exit 1
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Copying $repo_root → $TARGET:$APP_DIR"
ssh "$TARGET" "mkdir -p '$APP_DIR'"

# --delete keeps the server a mirror of the working tree, but .env holds the
# generated secrets and the volumes hold the database, so both are protected.
rsync -az --delete \
  --exclude '.git' \
  --exclude '.env' \
  --exclude 'node_modules' \
  --exclude 'dist' \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '.mypy_cache' \
  --exclude '.ruff_cache' \
  --exclude '.pytest_cache' \
  "$repo_root/" "$TARGET:$APP_DIR/"

echo "==> Running the deploy on $TARGET"
ssh -t "$TARGET" "
  cd '$APP_DIR' &&
  MEMORA_SKIP_FETCH=1 \
  MEMORA_DIR='$APP_DIR' \
  MEMORA_DOMAIN='$DOMAIN' \
  CADDY_CONTAINER='$CADDY_CONTAINER' \
  TELEGRAM_BOT_TOKEN='${TELEGRAM_BOT_TOKEN:-}' \
  GEMINI_API_KEY='${GEMINI_API_KEY:-}' \
  AZURE_TRANSLATOR_KEY='${AZURE_TRANSLATOR_KEY:-}' \
  AZURE_TRANSLATOR_REGION='${AZURE_TRANSLATOR_REGION:-}' \
  bash deploy/deploy.sh
"
