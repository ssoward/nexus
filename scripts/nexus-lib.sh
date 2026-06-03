# Sourced helper functions for the Nexus launch scripts.
# Requires COLIMA_BIN, DOCKER_BIN, TAILSCALE_BIN, REPO_ROOT, CADDY_HOST_PORT in env
# (normally provided by nexus-paths.sh).

log() { echo "$(date '+%Y-%m-%dT%H:%M:%S') nexus: $*" >&2; }

colima_running() {
  local out
  out="$("$COLIMA_BIN" status 2>&1)" || return 1
  [[ "$out" == *"running"* && "$out" != *"not running"* ]]
}

caddy_running() {
  "$DOCKER_BIN" compose ps --format json 2>/dev/null \
    | grep -q '"State":"running"'
}

tailscale_route_present() {
  # -F: match the port as a fixed string, not a regex. Requires Tailscale >= 1.40
  # (the `serve status` subcommand); errors are suppressed so a missing subcommand
  # simply reports "absent" and ensure_tailscale_route re-applies the route.
  "$TAILSCALE_BIN" serve status 2>/dev/null | grep -qF "$CADDY_HOST_PORT"
}

backend_healthy() {
  curl -fsS --max-time 3 http://127.0.0.1:8000/api/health >/dev/null 2>&1
}

# Bring colima up and wait until the docker socket answers (bounded).
ensure_colima() {
  if colima_running; then return 0; fi
  log "starting colima"
  "$COLIMA_BIN" start || return 1
  for _ in $(seq 1 30); do
    "$DOCKER_BIN" info >/dev/null 2>&1 && return 0
    sleep 2
  done
  log "ERROR: docker did not become ready"
  return 1
}

ensure_caddy() {
  caddy_running && return 0
  log "starting Caddy"
  ( cd "$REPO_ROOT" && "$DOCKER_BIN" compose up -d caddy ) \
    || { log "ERROR: Caddy failed to start"; return 1; }
}

ensure_tailscale_route() {
  tailscale_route_present && return 0
  log "applying tailscale serve route :443 -> ${CADDY_HOST_PORT}"
  "$TAILSCALE_BIN" serve --bg --tcp=443 "tcp://localhost:${CADDY_HOST_PORT}"
}
