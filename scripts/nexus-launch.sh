#!/usr/bin/env bash
# Ordered, idempotent bring-up of the Nexus stack, then exec uvicorn.
# Run by the com.nexus.stack LaunchAgent (KeepAlive). Safe to re-run.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$HERE/nexus-paths.sh"
# shellcheck source=/dev/null
source "$HERE/nexus-lib.sh"

cd "$REPO_ROOT" || { log "ERROR: cannot cd to $REPO_ROOT"; exit 1; }

# Load secrets / CADDY_HOST_PORT from .env if present.
# set -a: auto-export every var defined in .env into the process environment.
if [[ -f "$REPO_ROOT/.env" ]]; then set -a; source "$REPO_ROOT/.env"; set +a; fi
export CONFIG_PATH="$REPO_ROOT/config.yml"

VENV="$REPO_ROOT/backend/.venv"
if [[ ! -x "$VENV/bin/uvicorn" ]]; then
  log "ERROR: venv/uvicorn missing — run scripts/nexus-setup.sh first"
  exit 1
fi
if [[ ! -f "$REPO_ROOT/static/index.html" ]]; then
  log "ERROR: static/ not built — run scripts/nexus-setup.sh first"
  exit 1
fi

ensure_colima        || { log "colima not ready"; exit 1; }
ensure_caddy         || log "WARN: caddy up failed (continuing)"
ensure_tailscale_route || log "WARN: tailscale route failed (continuing)"

log "starting backend on 127.0.0.1:8000"
cd "$REPO_ROOT/backend" || { log "ERROR: cannot cd to $REPO_ROOT/backend"; exit 1; }
exec "$VENV/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000 --log-level info
