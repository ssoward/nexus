# Nexus macOS Menu Bar App + Launch-at-Login Stack — Design

**Date:** 2026-06-03
**Status:** Approved for planning
**Scope:** M5 (local) only for the first iteration. M1 added later.

---

## 1. Problem

Nexus today starts 100% manually. The runtime is a four-part dependency chain, not a
single process:

| Layer | Process | Starts today | Survives reboot alone? |
|---|---|---|---|
| Docker runtime | colima VM | manual `colima start` | No |
| TLS / static / proxy | Caddy container | `docker compose up -d` (`restart: unless-stopped`) | Only after colima is up |
| Private HTTPS ingress | `tailscale serve` `:443→8443` | manual `tailscale serve --bg` | Yes (persisted by tailscaled) |
| App backend | `uvicorn app.main:app` :8000 | `./start.sh` → `exec uvicorn` (foreground) | No |

The backend must run as a **native host process in the user's session** (not Docker)
because it spawns PTYs with the user's environment, dotfiles, and ssh-agent — this is the
documented reason it is not containerized. There is no launchd or login-item integration
anywhere in the repo today.

**Goal:** a macOS menu bar app that controls the full stack and a launchd-backed mechanism
that brings the stack up automatically at login and keeps it alive.

---

## 2. Decisions (from brainstorming)

- **Form factor:** native macOS **menu bar app** (Swift / AppKit `NSStatusItem`).
- **Tech:** **Swift native** app (no Python runtime to bundle).
- **Scope:** **full stack** — colima → Caddy → tailscale serve → backend.
- **Supervision:** **launchd-backed.** A `LaunchAgent` (RunAtLoad + KeepAlive) runs and
  supervises the stack. The Swift app is a thin controller; quitting it never stops the stack.
- **Boot timing:** **at login** (user-session LaunchAgent), not a pre-login root LaunchDaemon —
  required because PTYs need the user environment.
- **Signing:** **ad-hoc local signing** (personal machine, no Developer ID / notarization).
- **Targets:** **M5 only** for this iteration.

---

## 3. Architecture

```
LOGIN (user session)
  └─ LaunchAgent  com.nexus.stack   (RunAtLoad=true, KeepAlive=true)
        └─ scripts/nexus-launch.sh          ← idempotent, ordered bring-up
              1. ensure colima running       (colima start if down; wait for ready)
              2. docker compose up -d caddy   (also recovers via restart policy)
              3. ensure tailscale serve --tcp=443 → tcp://localhost:8443
              4. exec uvicorn app.main:app    (DB migrations run inside FastAPI lifespan)
        ↑ if uvicorn or the script exits, launchd re-runs it (throttled ≥10s)

MENU BAR  (Nexus.app — Swift/AppKit NSStatusItem; itself a Login Item)
        = controller over the agent + live status dashboard
        • Start All / Stop All / Restart  → launchctl kickstart / bootout / bootstrap
        • Open in browser                 → opens https://<host>.ts.net
        • ✓ Launch at login (this app)     → SMAppService.mainApp register/unregister
        • per-component status dots, polled on a timer
```

### Why this split
- The **LaunchAgent** provides the real "starts at boot" guarantee and crash-restart, even
  before or without the GUI app running.
- The **Swift app** is purely a controller and dashboard. Quitting it does not touch the
  running stack; the stack's lifecycle belongs to launchd.

---

## 4. Components

### 4.1 LaunchAgent — `macos/com.nexus.stack.plist`

A template plist (placeholders filled by `install.sh`):

- `Label`: `com.nexus.stack`
- `ProgramArguments`: `["/bin/bash", "<REPO>/scripts/nexus-launch.sh"]`
- `RunAtLoad`: `true`
- `KeepAlive`: `true` (restart on any exit; launchd throttles to ≥10s)
- `WorkingDirectory`: `<REPO>`
- `EnvironmentVariables`: minimal `PATH` that includes Homebrew + node, colima, docker,
  tailscale, and the venv. (Mirrors the PATH conventions already used for M1 in CLAUDE.md.)
- `StandardOutPath` / `StandardErrorPath`: `~/.nexus/logs/stack.out.log` / `stack.err.log`

Installed to `~/Library/LaunchAgents/com.nexus.stack.plist` and loaded with
`launchctl bootstrap gui/$UID <plist>`.

### 4.2 Launch script — `scripts/nexus-launch.sh`

New idempotent script the agent runs. Reuses the env/venv logic from `start.sh` but is
**safe to re-run on every KeepAlive restart**:

- Resolves `REPO_ROOT`, sources `.env`, exports `CONFIG_PATH`.
- Does **not** `pip install` or `npm build` on the hot path — those move to a separate
  one-time `scripts/nexus-setup.sh`. If the venv or `frontend/dist` is missing, it logs a
  clear error and exits (so launchd retries) rather than doing slow work in the supervision loop.
- Ordered bring-up, each step idempotent and with a bounded wait:
  1. `colima status` → if not running, `colima start`; wait until Docker socket responds.
  2. `docker compose up -d caddy`.
  3. Check `tailscale serve status`; if the `:443→8443` route is absent, apply it
     (`tailscale serve --bg --tcp=443 tcp://localhost:8443`). Honors `CADDY_HOST_PORT`.
  4. `exec uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info` from `backend/`.

`start.sh` is unchanged and remains the manual/dev entry point.

### 4.3 One-time setup script — `scripts/nexus-setup.sh`

Extracted from `start.sh`'s heavy steps: create venv, `pip install -r requirements.txt`,
`npm install && npm run build`, copy `dist/* → static/`. Run by `install.sh` and re-runnable
by hand after dependency changes. Keeps the agent's hot path fast.

### 4.4 Swift menu bar app — `macos/Nexus/`

AppKit, `LSUIElement = true` (no Dock icon), single `NSStatusItem`.

**Menu:**
- Header line per component with a colored dot: `colima`, `Caddy`, `tailscale`, `backend`.
- Separator.
- `Start All`, `Stop All`, `Restart` — operate on the agent via `launchctl`.
- `Open in browser` — opens `https://<host>` read from config.
- `Launch at login` (checkable) — `SMAppService.mainApp` register/unregister.
- `View Logs` — opens `~/.nexus/logs/` in Finder / Console.
- `Quit` (quits the controller only; stack keeps running).

**Status polling (timer, every ~3–5s), each probe with a short timeout:**

| Component | Probe | green / amber / red |
|---|---|---|
| colima | `colima status` exit code | running / starting / stopped |
| Caddy | `docker compose ps --format json` (or `docker inspect`) | running / restarting / down |
| tailscale | `tailscale serve status` contains `:443→…8443` | present / partial / absent |
| backend | `GET http://127.0.0.1:8000/api/health` | 200 / slow / unreachable |

Overall menu bar icon reflects the worst component state.

**Control actions (`launchctl`):**
- Start All → `launchctl kickstart -k gui/$UID/com.nexus.stack` (or `bootstrap` if not loaded).
- Stop All → `launchctl bootout gui/$UID/com.nexus.stack` (then explicitly `docker compose stop caddy`; colima and tailscale are left running by default — see Open Questions).
- Restart → `launchctl kickstart -k`.

Config the app needs (host URL, repo path) is read from a small JSON written by `install.sh`
to `~/.nexus/menubar.json`.

### 4.5 Install / uninstall — `macos/install.sh`, `macos/uninstall.sh`

`install.sh` (M5):
1. Run `scripts/nexus-setup.sh` (venv, deps, frontend build, static copy).
2. Build the Swift app (`swift build` or `xcodebuild`), produce `Nexus.app`.
3. Ad-hoc codesign (`codesign -s - --deep Nexus.app`); copy to `/Applications`.
4. Render `com.nexus.stack.plist` with real repo path + PATH → `~/Library/LaunchAgents/`.
5. `launchctl bootstrap gui/$UID <plist>`.
6. Write `~/.nexus/menubar.json` (host URL from `config.yml`, repo path).
7. Print next steps (open the app, toggle Launch at login).

`uninstall.sh`: `launchctl bootout` the agent, remove plist, remove `/Applications/Nexus.app`,
unregister the Login Item. Leaves `~/.nexus/` data intact.

---

## 5. Files added

```
macos/
  Nexus/                       # Swift AppKit menu bar app (SPM or Xcode project)
  com.nexus.stack.plist        # LaunchAgent template
  install.sh
  uninstall.sh
scripts/
  nexus-launch.sh              # ordered idempotent bring-up (agent runs this)
  nexus-setup.sh               # one-time heavy setup (venv, deps, build)
```

No changes to backend Python or existing frontend. `start.sh` unchanged.

---

## 6. Error handling

- **colima not ready:** `nexus-launch.sh` bounds the wait (e.g. 60s); on timeout it exits
  non-zero, launchd retries after throttle. Errors land in `~/.nexus/logs/stack.err.log`.
- **Missing venv / dist:** script logs an actionable message ("run nexus-setup.sh") and exits;
  it does not attempt slow installs inside the supervision loop.
- **tailscale route apply fails:** logged; backend still starts (reachable locally on :8000),
  menu bar shows tailscale amber/red so the user sees the gap.
- **Swift probe timeouts:** each probe is async with a short timeout so a hung `docker`/`colima`
  call cannot freeze the menu; a timed-out probe renders amber.
- **launchctl bootstrap "already loaded":** install.sh is idempotent (bootout-then-bootstrap).

---

## 7. Testing

- **`nexus-launch.sh`:** run directly; verify idempotency (run twice, second is a no-op for
  already-up components); kill uvicorn and confirm launchd restarts it; reboot/re-login and
  confirm the stack comes up; `curl -ks https://<host>/api/health` returns 200.
- **Swift app:** manual — dots reflect each component as it is stopped/started; Start/Stop/Restart
  drive the agent; Launch-at-login toggle reflected in System Settings → Login Items; quitting the
  app leaves the stack running.
- **install/uninstall:** clean install on M5, then uninstall, then confirm no residual agent
  (`launchctl print gui/$UID/com.nexus.stack` absent) and the app removed.
- Backend Python test suite is untouched but run once (`cd backend && python -m pytest -q`) to
  confirm no regressions, per Definition of Done.

---

## 8. Definition of Done (per CLAUDE.md)

- Frontend build only if frontend changed (it is not here) — n/a, state explicitly.
- README updated with a new "Run as a macOS menu bar app (launch at login)" section.
- M5 redeploy: `nexus-setup.sh` copies `dist/* → static/` as part of install.
- M1 redeploy: **deferred** — M1 install is out of scope this iteration (state explicitly in the PR).
- Conventional commit; push to `origin main`.

---

## 9. Open questions / deferred

- **Stop All semantics:** should "Stop All" also stop colima and reset `tailscale serve`, or
  only stop the backend + Caddy and leave the VM/route up (faster restarts, colima shared with
  other work)? Default proposed: leave colima and tailscale up. Revisit during implementation.
- **M1 rollout:** parameterize `install.sh` for M1 (SSH + git pull + Homebrew/node PATH) in a
  follow-up.
- **Pre-login operation:** explicitly out of scope; would require a root LaunchDaemon and a
  different PTY/user-env model.
