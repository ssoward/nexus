#!/usr/bin/env bash
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

fail=0
assert_eq() { # $1 expected $2 actual $3 msg
  if [[ "$1" != "$2" ]]; then echo "FAIL: $3 (expected '$1', got '$2')"; fail=1
  else echo "ok: $3"; fi
}

# Build a temp dir of fake tools we control via env-driven exit codes.
MOCKBIN="$(mktemp -d)"
trap 'rm -rf "$MOCKBIN"' EXIT

cat > "$MOCKBIN/colima" <<'EOF'
#!/usr/bin/env bash
[[ "$1" == "status" ]] && { echo "$COLIMA_OUT"; exit "${COLIMA_RC:-0}"; }
exit 0
EOF
cat > "$MOCKBIN/docker" <<'EOF'
#!/usr/bin/env bash
echo "$DOCKER_OUT"; exit "${DOCKER_RC:-0}"
EOF
cat > "$MOCKBIN/tailscale" <<'EOF'
#!/usr/bin/env bash
echo "$TS_OUT"; exit "${TS_RC:-0}"
EOF
chmod +x "$MOCKBIN"/*

# Source the lib with paths pointing at the mocks.
COLIMA_BIN="$MOCKBIN/colima"
DOCKER_BIN="$MOCKBIN/docker"
TAILSCALE_BIN="$MOCKBIN/tailscale"
CADDY_HOST_PORT="8443"
REPO_ROOT="$REPO_ROOT"
source "$REPO_ROOT/scripts/nexus-lib.sh"

# Export control vars so mock subprocesses can read them.
export COLIMA_OUT COLIMA_RC TS_OUT TS_RC

COLIMA_OUT="colima is running"; COLIMA_RC=0
colima_running; assert_eq "0" "$?" "colima_running true when running"

COLIMA_OUT="colima is not running"; COLIMA_RC=1
colima_running; assert_eq "1" "$?" "colima_running false when stopped"

# RC=0 but the text says "not running" — exercises the != *"not running"* branch.
COLIMA_OUT="colima is not running"; COLIMA_RC=0
colima_running; assert_eq "1" "$?" "colima_running false when RC=0 but text says not running"

TS_OUT="tcp://0.0.0.0:443 -> tcp://localhost:8443"; TS_RC=0
tailscale_route_present; assert_eq "0" "$?" "tailscale route present"

TS_OUT="No serve config"; TS_RC=0
tailscale_route_present; assert_eq "1" "$?" "tailscale route absent"

exit $fail
