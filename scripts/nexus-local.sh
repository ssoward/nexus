#!/usr/bin/env bash
# Run Nexus entirely on this machine over plain http://localhost:8000 —
# no Docker, no Caddy, no Tailscale.
#
# Unlike ./start.sh (backend + Caddy-in-Docker, served on a tailnet hostname),
# this suits hosts where Docker and the Tailscale system extension cannot be
# installed (e.g. an MDM/Jamf-managed Mac). Two differences make that possible:
#
#   1. STATIC_DIR — uvicorn serves static/ itself (see the mount at the bottom
#      of app/main.py), so Caddy is not needed to put the UI on an origin.
#   2. RP_ID / WEBAUTHN_ORIGIN in .env override config.yml's tailnet hostname,
#      so WebAuthn and TLS renewal never reach for the `tailscale` CLI.
#
# Everything stays same-origin on :8000, so the frontend's relative `/api` calls
# and its ws:// upgrade both work under the app's `connect-src 'self'` CSP.
#
# NOTE: browsers only accept the app's Secure session cookie over plain HTTP on
# localhost if they treat localhost as a trustworthy origin. Chrome and Firefox
# do; Safari does not, and login will appear to succeed but not persist. Use
# Chrome or Firefox, or front this with a real HTTPS cert.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"

HOST="${NEXUS_BIND_HOST:-127.0.0.1}"
PORT="${NEXUS_BIND_PORT:-8000}"

cd "$REPO_ROOT" || { echo "ERROR: cannot cd to $REPO_ROOT" >&2; exit 1; }

# Load secrets + machine-local overrides. set -a auto-exports each assignment.
if [[ -f "$REPO_ROOT/.env" ]]; then set -a; source "$REPO_ROOT/.env"; set +a; fi
export CONFIG_PATH="$REPO_ROOT/config.yml"

# Tells app/main.py to serve the built UI itself instead of leaving it to Caddy.
export STATIC_DIR="$REPO_ROOT/static"

VENV="$REPO_ROOT/backend/.venv"
if [[ ! -x "$VENV/bin/uvicorn" ]]; then
  echo "ERROR: $VENV/bin/uvicorn missing." >&2
  echo "  Create it with a Python 3.11+ interpreter, then install deps:" >&2
  echo "    python3 -m venv backend/.venv" >&2
  echo "    backend/.venv/bin/pip install -r backend/requirements.txt" >&2
  exit 1
fi

if [[ ! -f "$STATIC_DIR/index.html" ]]; then
  echo "ERROR: $STATIC_DIR/index.html missing — the UI has not been built." >&2
  echo "  cd frontend && npm install && npm run build && cp -r dist/* ../static/" >&2
  exit 1
fi

# A previous backend still holding the port looks identical from the outside to
# a foreign process squatting on it. Distinguish them: a healthy Nexus means
# re-running this script is a no-op, anything else needs a human.
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  if curl -fsS --max-time 5 "http://$HOST:$PORT/api/health" >/dev/null 2>&1; then
    echo "Nexus is already running and healthy at http://$HOST:$PORT/ — leaving it alone."
    exit 0
  fi
  echo "ERROR: port $PORT is in use but /api/health did not respond." >&2
  echo "  Inspect it with: lsof -nP -iTCP:$PORT -sTCP:LISTEN" >&2
  exit 1
fi

echo "Starting Nexus at http://$HOST:$PORT/ (no Docker/Caddy/Tailscale)"
cd "$REPO_ROOT/backend" || { echo "ERROR: cannot cd to backend" >&2; exit 1; }
exec "$VENV/bin/uvicorn" app.main:app --host "$HOST" --port "$PORT" --log-level info
