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

# How long to wait for a just-launched Docker daemon to accept connections.
DOCKER_WAIT_SECS="${DOCKER_WAIT_SECS:-90}"

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

# Hostname Caddy serves; mirrors the default in docker-compose.yml.
NEXUS_HOST="${NEXUS_HOST:-ssowardm1.tail040188.ts.net}"

# ── 3. Build frontend (if dist is missing or source changed) ─────────────────
# Caddy serves frontend/dist directly (see the volume mount in
# docker-compose.yml), so a stale dist means a stale UI with no other symptom.
# Rebuild whenever a build input is newer than the last build's index.html.
FRONTEND_DIR="$REPO_ROOT/frontend"
DIST_DIR="$FRONTEND_DIR/dist"

BUILD_INPUTS=(
  "$FRONTEND_DIR/src"
  "$FRONTEND_DIR/index.html"
  "$FRONTEND_DIR/package.json"
  "$FRONTEND_DIR/package-lock.json"
  "$FRONTEND_DIR/vite.config.ts"
  "$FRONTEND_DIR/tsconfig.json"
  "$FRONTEND_DIR/tailwind.config.ts"
  "$FRONTEND_DIR/postcss.config.js"
)

needs_build=""
if [[ ! -f "$DIST_DIR/index.html" ]]; then
  needs_build="no previous build found"
else
  existing_inputs=()
  for input in "${BUILD_INPUTS[@]}"; do
    [[ -e "$input" ]] && existing_inputs+=("$input")
  done
  # -print -quit stops at the first newer file; empty output means dist is current.
  changed="$(find "${existing_inputs[@]}" -newer "$DIST_DIR/index.html" -print -quit 2>/dev/null || true)"
  [[ -n "$changed" ]] && needs_build="source changed (${changed#"$FRONTEND_DIR/"})"
fi

if [[ -n "$needs_build" ]]; then
  echo "Building frontend — $needs_build..."
  cd "$FRONTEND_DIR"
  npm install --silent
  npm run --silent build
  cd "$REPO_ROOT"
else
  echo "Frontend build is up to date."
fi

# ── 4. Start Caddy (static + proxy) ──────────────────────────────────────────
# The Docker daemon has to be reachable before `docker compose` will do anything
# useful, and on macOS it does not survive a reboot — colima runs it in a VM,
# Docker Desktop in a background app. Launch whichever is installed, then wait:
# `open -a Docker` returns immediately, long before the socket is accepting.
wait_for_docker() {
  local deadline=$(( SECONDS + $1 ))
  while (( SECONDS < deadline )); do
    docker info >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

if ! docker info >/dev/null 2>&1; then
  launched=""
  if command -v colima >/dev/null 2>&1 && [[ "$(colima status 2>&1)" == *"not running"* ]]; then
    echo "Docker daemon unreachable; starting colima..."
    colima start && launched="colima"
  elif [[ "$(uname -s)" == "Darwin" && -d /Applications/Docker.app ]]; then
    echo "Docker daemon unreachable; starting Docker Desktop..."
    open -a Docker && launched="Docker Desktop"
  fi

  if [[ -n "$launched" ]]; then
    echo "Waiting up to ${DOCKER_WAIT_SECS}s for $launched to accept connections..."
    wait_for_docker "$DOCKER_WAIT_SECS" \
      || echo "WARNING: $launched did not come up within ${DOCKER_WAIT_SECS}s." >&2
  fi

  if ! docker info >/dev/null 2>&1; then
    echo "ERROR: cannot reach the Docker daemon — Caddy (TLS + proxy) cannot start." >&2
    echo "  macOS: 'colima start', or launch Docker Desktop (/Applications/Docker.app)." >&2
    echo "  Linux: 'sudo systemctl start docker'." >&2
    echo "  Then re-run ./start.sh. Check 'docker context ls' if the socket path looks wrong." >&2
    echo "  Set DOCKER_WAIT_SECS to allow a slower daemon more time to start." >&2
    exit 1
  fi
fi

echo "Starting Caddy..."
docker compose up -d --remove-orphans

# ── 5. Start backend on host ─────────────────────────────────────────────────
# A backend from a previous run keeps port 8000, and uvicorn's bind error is easy
# to miss when it scrolls past. Distinguish the two cases that look identical
# from the outside: a healthy Nexus already serving (re-running start.sh is a
# no-op, and Caddy above is now up) versus a foreign or wedged process squatting
# on the port, which needs a human.
if lsof -nP -iTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
  if curl -fsS --max-time 5 http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
    echo "Nexus backend is already running on port 8000 and healthy — leaving it alone."
    echo "  Caddy is up, so the app is served at https://${NEXUS_HOST}/"
    exit 0
  fi
  echo "ERROR: port 8000 is in use but /api/health did not respond." >&2
  echo "  Something other than a healthy Nexus backend holds the port." >&2
  echo "  Inspect it with: lsof -nP -iTCP:8000 -sTCP:LISTEN" >&2
  exit 1
fi

echo "Starting Nexus backend on port 8000..."
cd "$BACKEND_DIR"
exec uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info
