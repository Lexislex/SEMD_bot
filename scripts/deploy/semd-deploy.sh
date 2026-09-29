#!/usr/bin/env bash
# Production deploy of SEMD_bot.
#
# Installed on the server as ~/bin/semd-deploy.sh and bound to the GitHub
# Actions deploy key as a forced command in ~/.ssh/authorized_keys:
#
#   restrict,command="/home/botman/bin/semd-deploy.sh" ssh-ed25519 AAAA... github-actions-deploy@SEMD_bot
#
# The command sent by the client (SSH_ORIGINAL_COMMAND) is ignored, so a leaked
# deploy key can only trigger this deploy, not open a shell.
#
# The installed copy is NOT updated by git pull; after changing this file,
# reinstall it: install -m 755 scripts/deploy/semd-deploy.sh ~/bin/semd-deploy.sh

set -euo pipefail

REPO_DIR="$HOME/SEMD_bot"
SERVICE="semd-bot.service"
UV="$HOME/.local/bin/uv"

cd "$REPO_DIR"

echo "=== Pulling latest code ==="
git pull --ff-only origin master
git log --oneline -1

echo "=== Installing dependencies ==="
# venv управляется uv; ставим недостающее, ничего не удаляя
"$UV" sync --no-dev --no-install-project --inexact

echo "=== Restarting service ==="
# Требует правила в /etc/sudoers.d/semd-bot-deploy:
# botman ALL=(root) NOPASSWD: /usr/bin/systemctl restart semd-bot.service, /usr/bin/journalctl -u semd-bot.service -n 30 --no-pager
sudo -n /usr/bin/systemctl restart "$SERVICE"

echo "=== Waiting for service to start ==="
sleep 10

echo "=== Checking service status ==="
if systemctl is-active --quiet "$SERVICE"; then
  echo "✅ Service is running"
  systemctl status "$SERVICE" --no-pager
else
  echo "❌ Service failed to start"
  sudo -n /usr/bin/journalctl -u "$SERVICE" -n 30 --no-pager || true
  exit 1
fi
