#!/usr/bin/env bash
# Start the Nexus backend on the host and Caddy in Docker.
# Run from the repo root: ./start.sh
set -euo pipefail

# ── SECURITY NOTE (CRIT-3) ────────────────────────────────────────────────────
# The backend binds to 0.0.0.0:8000 so Docker (Caddy) can reach it via
# host.docker.internal. This port must NOT be reachable from the internet.
#
# macOS: Docker bridge is not externally routable — no action needed.
# Linux: Restrict access with:
#   sudo ufw deny 8000
#   sudo ufw allow from 172.16.0.0/12 to any port 8000  # Docker bridge range
# ─────────────────────────────────────────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$REPO_ROOT/backend"
VENV_DIR="$BACKEND_DIR/.venv"

# ── 1. Python virtual environment ────────────────────────────────────────────
if [[ ! -d "$VENV_DIR" ]]; then
  echo "Creating Python virtual environment..."
  python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "Installing/updating Python dependencies..."
pip install -q --upgrade pip
pip install -q -r "$BACKEND_DIR/requirements.txt"

# ── 2. Load environment variables ────────────────────────────────────────────
if [[ -f "$REPO_ROOT/.env" ]]; then
  set -a
  source "$REPO_ROOT/.env"
  set +a
fi

export CONFIG_PATH="$REPO_ROOT/config.yml"

# ── 3. Build frontend (if dist is missing or source changed) ─────────────────
FRONTEND_DIR="$REPO_ROOT/frontend"
if [[ ! -d "$FRONTEND_DIR/dist" ]]; then
  echo "Building frontend..."
  cd "$FRONTEND_DIR"
  npm install --silent
  npm run build --silent
  cd "$REPO_ROOT"
fi

# ── 4. Start Caddy (static + proxy) ──────────────────────────────────────────
echo "Starting Caddy..."
docker compose up -d --remove-orphans

# ── 5. Start backend on host ─────────────────────────────────────────────────
echo "Starting Nexus backend on port 8000..."
cd "$BACKEND_DIR"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level info
