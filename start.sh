#!/usr/bin/env bash
# Start the Nexus backend on the host and Caddy in Docker.
# Run from the repo root: ./start.sh
set -euo pipefail

# ── SECURITY NOTE (CRIT-3) ────────────────────────────────────────────────────
# The backend binds to 127.0.0.1:8000 (see the uvicorn invocation below). Caddy
# reaches it from its container via host.docker.internal, and the loopback bind
# keeps the port off every other interface. The rate limiter only trusts
# forwarded-IP headers from a loopback/private peer (see app/limiter.py), so do
# NOT change this to 0.0.0.0 without re-checking that assumption.
#
# Linux, if you must expose it beyond loopback, restrict access with:
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
# The Docker daemon has to be reachable before `docker compose` will do anything
# useful. On macOS the daemon lives in a colima VM that does not survive a
# reboot, so start it here rather than failing with a raw socket error.
if ! docker info >/dev/null 2>&1; then
  if command -v colima >/dev/null 2>&1 && [[ "$(colima status 2>&1)" == *"not running"* ]]; then
    echo "Docker daemon unreachable; starting colima..."
    colima start
  fi

  if ! docker info >/dev/null 2>&1; then
    echo "ERROR: cannot reach the Docker daemon — Caddy (TLS + proxy) cannot start." >&2
    echo "  Start it with 'colima start' (macOS) or by launching Docker Desktop," >&2
    echo "  then re-run ./start.sh. Check 'docker context ls' if the socket path looks wrong." >&2
    exit 1
  fi
fi

echo "Starting Caddy..."
docker compose up -d --remove-orphans

# ── 5. Start backend on host ─────────────────────────────────────────────────
# A backend from a previous run keeps port 8000, and uvicorn's bind error is easy
# to miss when it scrolls past. Say so plainly instead.
if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "ERROR: port 8000 is already in use — a Nexus backend is probably still running." >&2
  echo "  Inspect it with: lsof -nP -iTCP:8000 -sTCP:LISTEN" >&2
  echo "  Caddy is up, so if that process is healthy the app is already served." >&2
  exit 1
fi

echo "Starting Nexus backend on port 8000..."
cd "$BACKEND_DIR"
exec uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info
