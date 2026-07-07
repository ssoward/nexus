#!/usr/bin/env bash
# Backend-only launcher for the com.nexus.backend LaunchAgent (KeepAlive).
#
# Unlike scripts/nexus-launch.sh (the full colima+caddy+tailscale stack), this
# supervises ONLY the uvicorn backend. Use it on hosts where Caddy already runs
# independently (e.g. plain Docker, `nexus-caddy-1`) and the only unsupervised
# piece is the Python backend. Safe to re-run; execs uvicorn as PID 1 of the job
# so launchd's KeepAlive restarts it on crash or reboot.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"

cd "$REPO_ROOT" || { echo "ERROR: cannot cd to $REPO_ROOT" >&2; exit 1; }

# Load secrets (.env) — set -a auto-exports every var defined there.
if [[ -f "$REPO_ROOT/.env" ]]; then set -a; source "$REPO_ROOT/.env"; set +a; fi
export CONFIG_PATH="$REPO_ROOT/config.yml"

VENV="$REPO_ROOT/backend/.venv"
if [[ ! -x "$VENV/bin/uvicorn" ]]; then
  echo "ERROR: $VENV/bin/uvicorn missing — run scripts/nexus-setup.sh first" >&2
  exit 1
fi

cd "$REPO_ROOT/backend" || { echo "ERROR: cannot cd to backend" >&2; exit 1; }
exec "$VENV/bin/uvicorn" app.main:app --host 127.0.0.1 --port 8000 --log-level info
