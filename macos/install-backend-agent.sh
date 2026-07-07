#!/usr/bin/env bash
# Install ONLY the backend supervisor LaunchAgent (com.nexus.backend).
#
# For hosts where Caddy already runs independently (e.g. the nexus-caddy-1
# Docker container) and colima/the full com.nexus.stack agent are not in use —
# so the sole unsupervised piece is the uvicorn backend. This gives the backend
# crash- and reboot-resilience via launchd KeepAlive.
#
# Idempotent: boots out any prior copy of the agent and kills a stray manually
# launched uvicorn before handing the port to the supervised process.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LA_DIR="$HOME/Library/LaunchAgents"
UID_NUM="$(id -u)"
mkdir -p "$LA_DIR" "$HOME/.nexus/logs"

# A backend-only PATH: just needs the venv + system bins. No docker/colima.
PATH_VALUE="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$REPO_ROOT/backend/.venv/bin"

sed -e "s#@REPO_ROOT@#$REPO_ROOT#g" \
    -e "s#@HOME@#$HOME#g" \
    -e "s#@PATH@#$PATH_VALUE#g" \
    "$REPO_ROOT/macos/com.nexus.backend.plist.template" \
    > "$LA_DIR/com.nexus.backend.plist"
plutil -lint "$LA_DIR/com.nexus.backend.plist"

# Stop any prior supervised copy, then any stray hand-launched uvicorn so the
# agent's process can bind :8000 cleanly.
launchctl bootout "gui/$UID_NUM/com.nexus.backend" 2>/dev/null || true
pkill -f "uvicorn app.main:app" 2>/dev/null || true
sleep 2

launchctl bootstrap "gui/$UID_NUM" "$LA_DIR/com.nexus.backend.plist"
launchctl enable "gui/$UID_NUM/com.nexus.backend"

echo "com.nexus.backend bootstrapped. Verify:"
echo "  launchctl print gui/$UID_NUM/com.nexus.backend | grep -i state"
echo "  curl -sS http://127.0.0.1:8000/api/health"
