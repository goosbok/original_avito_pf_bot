#!/usr/bin/env bash
# deploy.sh — полный редеплой на production
#
# Использование:
#   ./deploy.sh            — pull + rebuild api+bot + up + copy landing
#   ./deploy.sh --landing  — только обновить лендинг (без ребилда)
#   ./deploy.sh --api      — pull + rebuild api + up (без bot)
#
# Запускать на сервере: ssh root@167.233.52.85 "cd /root/projects/original_avito_pf_bot && ./deploy.sh"

set -euo pipefail

LANDING_SRC_DIR="web/landing"
LANDING_DST_DIR="/var/www/pf-bot-landing"
# index.html + PWA-ассеты (favicon, apple-touch-icon, манифест и иконки для
# «Добавить на экран Домой»). Все файлы лежат рядом в web/landing/.
LANDING_ASSETS=(
  index.html
  manifest.json
  favicon-32.png
  apple-touch-icon.png
  icon-192.png
  icon-512.png
  icon-192-maskable.png
  icon-512-maskable.png
)
SERVER="root@167.233.52.85"
PROD_HOSTNAME="ubuntu-4gb-fsn1-1-igor"
PROJECT_DIR="/root/projects/original_avito_pf_bot"
# Ветка, с которой раскатывается прод.
DEPLOY_BRANCH="main"

# Подтягивает $DEPLOY_BRANCH. Явный checkout нужен потому, что сервер
# исторически стоял на dev: без него `git pull origin main` влил бы main
# в dev и оставил рабочую копию на ветке с чужим именем. --ff-only —
# чтобы деплой падал громко, если на сервере кто-то накоммитил руками.
pull_code() {
  git fetch origin "$DEPLOY_BRANCH"
  git checkout "$DEPLOY_BRANCH"
  git merge --ff-only "origin/$DEPLOY_BRANCH"
}

# Копирует лендинг (index.html + PWA-ассеты) в каталог, который раздаёт nginx
# и пред-сжимает текстовые ассеты в .gz/.br (gzip_static + brotli_static в nginx).
# Без пред-сжатия nginx жёг бы CPU на каждый запрос ИЛИ отдавал 636KB сырой
# index.html (≈30% сжимается даже на base64-набитом HTML, шейпленным RU-каналам
# критично).
copy_landing() {
  mkdir -p "$LANDING_DST_DIR"
  for asset in "${LANDING_ASSETS[@]}"; do
    cp "$LANDING_SRC_DIR/$asset" "$LANDING_DST_DIR/$asset"
  done

  # Пред-сжимаем только текстовые форматы. PNG уже сжаты deflate — повторный
  # gzip их раздувает, а .png.br/.png.gz для nginx_static не нужны.
  for asset in "${LANDING_ASSETS[@]}"; do
    case "$asset" in
      *.html|*.json|*.css|*.js|*.svg|*.xml|*.txt)
        gzip   -k -9 -f "$LANDING_DST_DIR/$asset"
        if command -v brotli >/dev/null 2>&1; then
          brotli -k -q 11 -f "$LANDING_DST_DIR/$asset"
        fi
        ;;
    esac
  done
}

# ──────────────────────────────────────────
# Если запущен локально — прокидываем на сервер
# ──────────────────────────────────────────
if [[ "$(hostname)" != "$PROD_HOSTNAME" ]] && ! [[ -f /.dockerenv ]]; then
  echo "→ Connecting to $SERVER..."
  ssh "$SERVER" "cd $PROJECT_DIR && bash deploy.sh $*"
  exit $?
fi

# ──────────────────────────────────────────
# Дальше — на сервере
# ──────────────────────────────────────────
MODE="${1:-full}"

step() { echo ""; echo "▶ $*"; }

# --- Только лендинг ---
if [[ "$MODE" == "--landing" ]]; then
  step "Pulling latest code..."
  pull_code
  step "Copying landing HTML..."
  copy_landing
  echo "✅ Landing updated."
  exit 0
fi

# --- Только api ---
if [[ "$MODE" == "--api" ]]; then
  step "Pulling latest code..."
  pull_code
  step "Building api..."
  docker compose build api
  step "Restarting api..."
  docker compose up -d api
  step "Copying landing HTML..."
  copy_landing
  echo ""
  docker compose ps api
  echo "✅ API redeployed."
  exit 0
fi

# --- Full deploy (default) ---
step "Pulling latest code..."
pull_code

step "Building images (api + bot)..."
docker compose build api bot

step "Restarting containers..."
docker compose up -d

step "Copying landing HTML..."
copy_landing

step "Waiting for api to start..."
sleep 4

step "Status:"
docker compose ps

step "Smoke check (api health)..."
HEALTH=$(curl -sf http://127.0.0.1:8000/api/health || echo "FAILED")
if [[ "$HEALTH" == *"ok"* ]]; then
  echo "✅ API healthy: $HEALTH"
else
  echo "❌ API health check failed: $HEALTH"
  echo "   → Check logs: docker compose logs --tail=30 api"
  exit 1
fi

echo ""
echo "✅ Deploy complete."
