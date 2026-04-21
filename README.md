# Nexus — Secure Web Terminal Gateway

A self-hosted, browser-based terminal multiplexer. Open up to six native PTY sessions (bash, zsh, Python REPL, Claude Code, or any command) in a browser, accessible over HTTPS from any device on your Tailscale network — including mobile.

---

## Features

- **Native PTY sessions** — real OS processes on the host, not containers; full color, resize, Unicode
- **Multi-tab support** — open the same session in multiple browser tabs simultaneously; all tabs share one PTY reader
- **Self-registration** — anyone can create an account; username is an email address
- **Flexible MFA** — choose Authenticator App (TOTP) or Email Code (OTP via SMTP) during setup; switch between methods at any time from the login verification screen ("Use email code instead" / "Use authenticator instead")
- **Email OTP** — 6-digit codes sent via SMTP, bcrypt-hashed, 10-minute TTL, replay-protected; "Resend code" button on login
- **TOTP two-factor authentication** — authenticator-app code (Google Authenticator, Authy, 1Password); QR setup built into login flow
- **Strong password enforcement** — 16+ chars, upper/lower/digit/special required at account creation
- **Account lockout** — 5 failed attempts triggers a 15-minute lockout; active tokens also blocked during lockout
- **JWT revocation** — logout immediately invalidates the token server-side
- **Sliding session** — frontend silently refreshes the JWT every 30 minutes; active users are never evicted by the 24-hour TTL; visibility-based refresh catches missed intervals when the tab is backgrounded
- **Rate limiting** — 10 login attempts per minute per IP via slowapi
- **Idle timeout** — sessions idle longer than 24 hours are stopped automatically
- **Mobile-friendly** — overlay sidebar, dot navigation, soft keyboard support (tested on iOS Safari / Chrome Android); quick-access keybar with Tab, ^C, Paste, arrows, and common Ctrl combos
- **Inactivity detection** — amber pulsing border and sidebar badge when a terminal has no output for 60 seconds; helps identify which session needs attention
- **Priority Queue layout** — 80/20 split: one session gets most of the viewport, others are thumbnails; auto-promotes the most recently active session when the primary goes idle; toggle between Grid and Priority modes in the header
- **Mastermind orchestration** — HTTP API (`/api/orchestration/*`) to read terminal buffers, send keystrokes, and classify terminal state (WORKING/WAITING/ASKING/BUSY); sidebar Orchestrator panel with batch send; `wctl.py` CLI for programmatic control of parallel Claude Code agents
- **Health check** — `GET /api/health` returns database, watchdog, and PTY service status with uptime
- **Prometheus metrics** — `GET /api/metrics` exposes sessions_active, ws_connections, pty_bytes_read, uptime counters
- **Structured logging** — JSON log format via `log_format: json` in config; includes user_id, session_id, IP context
- **Graceful shutdown** — ordered teardown: broadcast session_dead → close WebSockets → cancel watchdog → SIGTERM/SIGKILL PTYs → close DB
- **Auto TLS renewal** — background task checks Tailscale cert age every 6h; renews and reloads Caddy when >60 days old
- **Session recovery** — on graceful shutdown, ring buffers are serialized to `~/.nexus/recovery.json`; on restart, sessions marked RECOVERY_PENDING are re-spawned with buffer replay on first WS connect
- **Visibility-triggered reconnect** — when a backgrounded tab returns after 5+ seconds, the frontend proactively refreshes the JWT and reconnects the WebSocket with ring buffer replay; PTY output accumulated while the tab was hidden is replayed into the terminal, so returning users see current state without manual refresh
- **Workspace grouping** — named, color-coded workspace groups; sessions can be assigned to workspaces; CRUD via `/api/workspaces`
- **Web page embedding** — embed HTTPS pages as sandboxed iframes in a split-view panel alongside terminals; CRUD via `/api/pages`
- **Mastermind monitor** — `/mastermind` Claude Code slash command for autonomous multi-agent orchestration with CronCreate
- **Secure by default** — httpOnly/Secure/SameSite=Strict cookies; strict CSP; HSTS; no Swagger/ReDoc in prod
- **Audit log** — every login, logout, WS connect/disconnect, and TOTP setup written to SQLite

---

## Architecture

```
Browser (HTTPS / WSS)
  └─ Caddy 2 in Docker  (TLS termination · static files · reverse proxy)
       └─ FastAPI on host:8000  (auth · sessions · WebSocket)
            ├─ SQLite  (~/.nexus/nexus.db)
            └─ PTY processes on host  (bash, zsh, python3, claude, …)
```

### Why the backend runs on the host (not in Docker)

Sessions are native PTY processes (`os.openpty()` + `subprocess.Popen`). The backend must run directly on the host to be able to spawn processes with the user's environment, dotfiles, ssh-agent, etc. Caddy stays in Docker and proxies to `host.docker.internal:8000`.

### PTY broadcaster

One asyncio reader task per session fans PTY output to N subscriber queues (one per WebSocket tab). This eliminates the race condition where two `os.read()` calls on the same fd would each steal half the output.

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.11+ | Backend |
| Node.js | 18+ | Frontend build |
| Docker + Compose | any recent | Caddy only — [Colima](https://github.com/abiosoft/colima) (free) recommended over Docker Desktop |
| Tailscale | any | For HTTPS via `.ts.net` cert |
| `openssl` | system | Secret generation |

---

## Quick Start

### 1. Clone

```bash
git clone https://github.com/YOUR_USERNAME/nexus
cd nexus
```

### 2. Generate secrets

```bash
echo "APP_SECRET=$(openssl rand -hex 32)" > .env
echo "JWT_SECRET=$(openssl rand -hex 32)" >> .env
echo "CRYPTO_SALT=$(openssl rand -hex 16)" >> .env
```

### 2b. Configure Email OTP (optional)

If you want users to authenticate via email code instead of an authenticator app, add SMTP credentials:

```bash
cat >> .env <<'EOF'
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-specific-password
SMTP_FROM=Nexus <your-email@gmail.com>
EOF
```

> **Gmail users:** Create an [App Password](https://myaccount.google.com/apppasswords) (requires 2FA enabled on your Google account). Use the 16-character app password as `SMTP_PASSWORD`.

Without SMTP configured, users can still register and use TOTP (authenticator app) for MFA. The "Email Code" option is always visible on the login screen; switching to it when SMTP is not configured returns a descriptive error rather than a generic failure.

### 3. Configure Tailscale HTTPS (recommended)

Nexus is designed to be accessed over your Tailscale private network. Tailscale provides
automatic HTTPS via Let's Encrypt for every machine on your tailnet.

> **Why HTTPS is required:** `.ts.net` domains are on Chrome's and Firefox's HSTS preload
> list. Browsers unconditionally upgrade all requests to HTTPS, so plain HTTP will never
> load — you must have a valid TLS cert.

#### a. Install Tailscale and log in

```bash
# macOS
brew install tailscale
sudo tailscale up

# Linux
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Confirm the machine is visible in your tailnet:

```bash
tailscale status        # should show your machine as online
tailscale ip -4         # e.g. 100.x.x.x
```

#### b. Provision a TLS certificate

```bash
# The hostname is shown in the Tailscale admin console or via `tailscale status`
sudo tailscale cert <your-machine>.tail<id>.ts.net
```

Default cert output locations:

| OS | Location |
|----|----------|
| macOS | `/var/root/Library/Containers/io.tailscale.ipn.macsys/Data/<hostname>.*` or current directory |
| Linux | Current working directory or `/etc/ssl/` depending on distribution |

Copy the cert and key into the repo's `certs/` directory (which is gitignored):

```bash
# macOS — tailscale cert writes to the current directory
sudo tailscale cert <hostname>.tail<id>.ts.net
cp <hostname>.tail<id>.ts.net.crt /path/to/nexus/certs/
cp <hostname>.tail<id>.ts.net.key /path/to/nexus/certs/
```

#### c. Update the Caddyfile

Replace the hostname and cert paths in `Caddyfile`:

```caddy
your-machine.tail12345.ts.net {
  tls /certs/your-machine.tail12345.ts.net.crt \
      /certs/your-machine.tail12345.ts.net.key
  ...
}
```

The `certs/` directory is mounted into the Caddy container as `/certs` (read-only) via `docker-compose.yml`.

Caddy binds both ports via `docker-compose.yml`:

| Port | Purpose |
|------|---------|
| 80 | HTTP — Caddy automatically redirects to HTTPS |
| 443 | HTTPS — TLS terminated using your Tailscale cert |

Access the app at `https://<your-hostname>.tail<id>.ts.net` (port 443). Port 80 redirects there automatically.

#### d. Renew certificates

Tailscale certificates expire every ~90 days. Renew with the same command:

```bash
sudo tailscale cert <hostname>.tail<id>.ts.net
# Then copy the new files into certs/ and restart Caddy:
docker compose restart caddy
```

### 4. Build frontend

```bash
cd frontend
npm install
npm run build
cd ..
```

### 5. Start Caddy

Docker is only used to run Caddy. [Colima](https://github.com/abiosoft/colima) is a free,
open-source alternative to Docker Desktop and works with `docker compose` out of the box:

```bash
# Install Colima (macOS)
brew install colima docker docker-compose
colima start

# Start Caddy
docker compose up -d
```

### 6. Start backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Exports .env and config.yml path, then starts uvicorn:
cd ..
source .env
export CONFIG_PATH="$PWD/config.yml"
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or just run `./start.sh` from the repo root (handles venv, frontend build, Docker, and backend).

#### Running without Caddy (development)

If you don't have Docker/Caddy running, the backend can serve the frontend directly. Set the `STATIC_DIR` environment variable to the frontend build directory:

```bash
export STATIC_DIR="$PWD/frontend/dist"
# Then start the backend as above — the app is accessible at http://localhost:8000
```

This enables SPA routing (client-side routes like `/login` serve `index.html`) and static asset serving. For production use, Caddy is recommended for TLS termination and security headers.

### 7. Create your account

```bash
curl -X POST http://localhost:8000/api/auth/create-user \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"YourStr0ng@Password!"}'
```

This endpoint is permanently disabled once any user exists.

### 8. Set up the authenticator app

On your first login, the app will automatically display a QR code — scan it with Google Authenticator, Authy, 1Password, or any TOTP app, then enter the 6-digit code to activate. Login is blocked until this step is complete. All subsequent logins require the code.

---

## Configuration

### `.env` — secrets (never commit)

| Variable | Required | Description |
|----------|----------|-------------|
| `APP_SECRET` | Yes | Master key for AES-256-GCM TOTP secret encryption (≥ 32 chars) |
| `JWT_SECRET` | Yes | HMAC-SHA256 JWT signing key (≥ 32 chars) |
| `CRYPTO_SALT` | Yes | PBKDF2 salt for key derivation (≥ 16 chars) |

### `config.yml` — non-secret runtime config

```yaml
app:
  max_panes: 6               # Maximum concurrent sessions
  log_level: INFO
  db_path: ~/.nexus/nexus.db   # SQLite database path (~ is expanded)

session:
  idle_timeout_seconds: 86400  # Auto-stop sessions idle longer than this
  jwt_expire_minutes: 1440    # JWT token lifetime (24 hours)

presets:                       # Commands available when creating a session
  - name: bash
    command: ["/bin/bash", "-l"]
    description: Login shell
  - name: zsh
    command: ["/bin/zsh", "-l"]
    description: Zsh login shell
  - name: claude
    command: ["claude"]
    description: Claude Code CLI
  - name: python
    command: ["python3"]
    description: Python 3 REPL
```

Secrets must **never** appear in `config.yml`. The config loader rejects any key whose name contains `secret`, `password`, `token`, or `apikey` and raises an error at startup.

### Caddyfile

```caddy
{
  admin off
  auto_https off
}

your-hostname.tail12345.ts.net {
  tls /certs/your-hostname.tail12345.ts.net.crt \
      /certs/your-hostname.tail12345.ts.net.key

  handle /api/* {
    reverse_proxy host.docker.internal:8000 {
      flush_interval -1
    }
  }

  handle /ws/* {
    reverse_proxy host.docker.internal:8000 {
      flush_interval -1
      transport http { read_timeout 0; write_timeout 0 }
    }
  }

  handle {
    root * /srv
    encode gzip
    try_files {path} /index.html
    file_server
    header {
      Content-Security-Policy "default-src 'self'; connect-src 'self'; ..."
      Strict-Transport-Security "max-age=63072000; includeSubDomains"
    }
  }
}
```

---

## API Reference

All API routes are under `/api/`.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| **Auth** | | | |
| POST | `/api/auth/login` | — | Form: `username`, `password`, `totp_code` (optional first step) |
| POST | `/api/auth/logout` | Cookie | Revokes JWT, clears cookie |
| GET | `/api/auth/me` | Cookie | Returns `{id, username, mfa_method, has_totp}` |
| POST | `/api/auth/create-user` | — | Self-registration (email + password) |
| POST | `/api/auth/setup-mfa` | Form password | Choose TOTP or email_otp; returns QR or sends code |
| POST | `/api/auth/switch-mfa` | Form password | Switch between TOTP and email OTP from login screen |
| POST | `/api/auth/resend-otp` | Form password | Resend email OTP code (3/min rate limit) |
| POST | `/api/auth/refresh` | Cookie | Re-issue JWT cookie (called every 30 min by frontend) |
| GET | `/api/auth/ws-token` | Cookie | Single-use 60-second WS token for a session |
| POST | `/api/auth/setup-totp` | Cookie | Regenerate TOTP secret; returns QR code |
| POST | `/api/auth/bootstrap-totp` | Form password | Legacy one-time TOTP setup |
| **Sessions** | | | |
| GET | `/api/sessions` | Cookie | List all sessions for the authenticated user |
| POST | `/api/sessions` | Cookie | Create a new session (spawns PTY process) |
| DELETE | `/api/sessions/{id}` | Cookie | Stop and delete a session |
| POST | `/api/sessions/{id}/restart` | Cookie | Restart a stopped session |
| PATCH | `/api/sessions/{id}/resize` | Cookie | Resize session terminal |
| WS | `/ws/session/{id}?token=…` | WS token | Bidirectional PTY I/O |
| **Orchestration** | | | |
| GET | `/api/orchestration/sessions/states` | Cookie | Classified state for all running sessions |
| GET | `/api/orchestration/sessions/{id}/state` | Cookie | State + idle seconds for one session |
| GET | `/api/orchestration/sessions/{id}/buffer` | Cookie | Last N lines of terminal output (default 100) |
| POST | `/api/orchestration/sessions/{id}/input` | Cookie | Send keystrokes to a session |
| **Workspaces** | | | |
| GET | `/api/workspaces` | Cookie | List workspaces |
| POST | `/api/workspaces` | Cookie | Create workspace (name, color) |
| PATCH | `/api/workspaces/{id}` | Cookie | Update workspace |
| DELETE | `/api/workspaces/{id}` | Cookie | Delete workspace |
| **Pages** | | | |
| GET | `/api/pages` | Cookie | List embedded pages |
| POST | `/api/pages` | Cookie | Create page (name, HTTPS URL) |
| PATCH | `/api/pages/{id}` | Cookie | Update page |
| DELETE | `/api/pages/{id}` | Cookie | Delete page |
| **Monitoring** | | | |
| GET | `/api/health` | — | Database, watchdog, PTY service status + uptime |
| GET | `/api/metrics` | — | Prometheus-format counters and gauges |

### WebSocket frames (JSON)

**Client → server:**

| Type | Fields | Description |
|------|--------|-------------|
| `input` | `data: string` | Raw keystrokes to write to PTY |
| `resize` | `cols: number, rows: number` | Terminal resize (clamped 20–500 / 5–200) |
| `ping` | — | Keepalive; server replies with `pong` |

**Server → client:**

| Type | Fields | Description |
|------|--------|-------------|
| `output` | `data: string` | Base64-encoded PTY bytes |
| `pong` | — | Reply to ping |
| `session_dead` | `reason: string` | Process exited; session is stopped |
| `error` | `message: string` | Protocol error |

---

## wctl.py — Orchestration CLI

`wctl.py` is a zero-dependency Python CLI for programmatic control of sessions. It wraps the `/api/orchestration/*` endpoints and adds `wait` (poll until a state is reached) and `broadcast` (send to all WAITING sessions at once).

### Authentication

Every command requires two flags:

```bash
python3 wctl.py --url https://your-host.ts.net --cookie <access_token_value> <subcommand>
```

Get the cookie value from your browser's DevTools → Application → Cookies → `access_token`, or capture it after a `curl` login.

### Commands

| Command | Example | Description |
|---------|---------|-------------|
| `sessions` | `wctl.py ... sessions` | List all sessions with id, name, status, preset |
| `states` | `wctl.py ... states` | Classify state of all running sessions |
| `state SESSION_ID` | `wctl.py ... state abc123` | State + idle seconds for one session |
| `buffer SESSION_ID` | `wctl.py ... buffer abc123 --lines 50` | Print last N lines of terminal output (default 100, max 1000) |
| `send SESSION_ID TEXT` | `wctl.py ... send abc123 "ls -la\n"` | Send keystrokes — include `\n` for Enter |
| `wait SESSION_ID STATE` | `wctl.py ... wait abc123 WAITING --timeout 60` | Poll every 2 s until session reaches target state; exits 1 on timeout |
| `broadcast TEXT` | `wctl.py ... broadcast "y\n"` | Send text to every session currently in WAITING state |

Valid states for `wait`: `WORKING`, `WAITING`, `ASKING`, `BUSY`.

### Example — unblock all WAITING agents

```bash
URL="https://nexus.tail12345.ts.net"
COOKIE="eyJhbGci..."

# Check what each session is doing
python3 wctl.py --url $URL --cookie $COOKIE states

# Send "y\n" to every session sitting at a confirmation prompt
python3 wctl.py --url $URL --cookie $COOKIE broadcast "y\n"
```

### Example — scripted pipeline

```bash
SESSION_ID="abc123"

# Wait for Claude to finish, then send the next prompt
python3 wctl.py --url $URL --cookie $COOKIE wait $SESSION_ID WAITING --timeout 300
python3 wctl.py --url $URL --cookie $COOKIE send $SESSION_ID "Run the tests and report\n"

# Read the output buffer when done
python3 wctl.py --url $URL --cookie $COOKIE wait $SESSION_ID WAITING --timeout 120
python3 wctl.py --url $URL --cookie $COOKIE buffer $SESSION_ID --lines 200
```

---

## Workflows

### Running parallel Claude Code agents (Mastermind)

The most powerful use case for Nexus is running multiple Claude Code sessions in parallel and letting an autonomous agent coordinate them.

**1. Open multiple Claude Code sessions**

In the Sessions sidebar, create 2–6 sessions using the `Claude Code` preset. Give them descriptive names (e.g. `agent-api`, `agent-tests`, `agent-docs`).

**2. Assign work to each agent**

Click each session's terminal and type a prompt for Claude to start working on:

```
implement the /users endpoint with pagination, tests, and OpenAPI annotations
```

**3. Watch the Orchestrator panel**

Switch to the Orchestrator sidebar tab. It auto-refreshes every 5 seconds and shows each session's state:
- **WORKING** — Claude is actively generating output
- **WAITING** — Claude finished and is back at the shell prompt
- **ASKING** — Claude is asking a yes/no question before proceeding

**4. Unblock agents automatically**

When agents hit a confirmation prompt (ASKING), use "Send to all WAITING" or `wctl.py broadcast` to answer all of them at once:

```bash
python3 wctl.py --url $URL --cookie $COOKIE broadcast "y\n"
```

**5. Activate Mastermind for fully autonomous coordination**

Click "Copy /mastermind Command" in the Orchestrator panel and paste it into a Claude Code terminal session. This activates the Mastermind autonomous agent, which:

1. Reads the state and output buffer of every session
2. Decides what to type into each WAITING or ASKING session
3. Sends the appropriate input
4. Schedules itself to repeat every 3 minutes via `CronCreate`

Mastermind will handle agent coordination without further manual input.

**6. Monitor with Priority layout**

Switch to Priority layout (the priority icon in the header) and enable auto-promote (▶). The most recently active session automatically gets the large primary pane, so you can see which agent is currently producing output without manually switching.

---

## Troubleshooting

### App won't start

**`APP_SECRET / JWT_SECRET / CRYPTO_SALT` not set**
```
KeyError: 'APP_SECRET'
```
Make sure `.env` exists and is sourced before starting the backend: `source .env`

**Port 8000 already in use**
```bash
lsof -ti:8000 | xargs kill
```

**Database migration error**
```bash
cd backend
DB_PATH=~/.nexus/nexus.db alembic upgrade head
```

---

### Can't log in

**"Account locked"** — 5 failed attempts trigger a 15-minute lockout. Wait and try again.

**"TOTP code invalid"** — Check your device clock is synced (`date` on the server vs. your phone). TOTP requires clocks to be within ~30 seconds.

**Email code not arriving** — Check your spam folder. Verify SMTP is configured in `.env` (`SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`). Click "Resend code" on the login page (rate-limited to 3/minute). The code is valid for 10 minutes.

**Email code "invalid" after resending** — When you click "Resend code", the previous code is invalidated. Always use the most recent email. If you retry the sign-in form without clicking resend, the original code stays valid.

**Lost authenticator app** — Re-run the bootstrap TOTP setup from the CLI:
```bash
curl -X POST http://localhost:8000/api/auth/bootstrap-totp \
  -d "username=your-email@example.com&password=YourPassword"
```
This is only available when the account has no TOTP secret configured.

**Switch MFA method** — To switch from TOTP to Email OTP (or vice versa), reset the `mfa_method` column in the database:
```bash
sqlite3 ~/.nexus/nexus.db "UPDATE users SET mfa_method = NULL, encrypted_totp_secret = NULL WHERE username = 'your-email@example.com';"
```
On next login you'll be prompted to choose a new MFA method.

**"Email Code" switch returns 503** — SMTP is not configured. Add `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD`, and `SMTP_FROM` to `.env` and restart the backend. See Quick Start step 2b.

**`setup-totp` returns 500 after changing secrets** — The TOTP secret in the database was encrypted with a different `APP_SECRET`/`CRYPTO_SALT` and can no longer be decrypted. Clear it so the user can re-enroll:
```bash
sqlite3 ~/.nexus/nexus.db "UPDATE users SET encrypted_totp_secret = NULL WHERE username = 'your-email@example.com';"
```
The TOTP Setup modal will then generate a fresh QR code without asking for the old code. **Note:** changing `APP_SECRET` or `CRYPTO_SALT` invalidates all encrypted TOTP secrets — plan secret rotation accordingly (see Pre-production checklist).

---

### Session issues

**Session shows "stopped" immediately after creating** — The preset command failed to spawn. Check `config.yml` — the command must exist on the host. For `claude`, run `which claude` to confirm it's in PATH.

**Terminal output jumbled / lines garbled** — This happens when the PTY column width doesn't match the browser viewport. Nexus sends the correct size on connect (with retries at 100ms and 500ms) and sends SIGWINCH to force TUI apps to redraw. If it persists: resize your browser window slightly to trigger a fresh resize, or delete and recreate the session.

**Terminal output freezes / WebSocket disconnects** — Caddy's `flush_interval -1` and `read_timeout 0` must be set for WebSocket routes in the Caddyfile. Check your Caddyfile matches the template in this README. If the disconnect happened because the tab was backgrounded, the terminal will automatically reconnect and replay buffered output when you return.

**"Maximum sessions reached"** — The default cap is 6 (configurable via `max_panes` in `config.yml`). Delete a stopped session to free a slot.

**Session buffer empty after browser refresh** — The ring buffer survives browser reconnects (including backgrounded-tab reconnects with `?replay=1`) but not server restarts (unless the shutdown was graceful). Check `~/.nexus/recovery.json` — if it exists, sessions marked `recovery_pending` will replay their buffer on next connect.

---

### Orchestrator / wctl.py

**`wctl.py` returns 401** — Your `access_token` cookie expired (24-hour TTL). Log in again to get a fresh token.

**`wait` command times out** — The session may be in an unexpected state. Run `buffer SESSION_ID` to read the last output and check what the terminal is showing.

**Mastermind keeps typing into the wrong session** — Check that session names are descriptive enough for Claude to infer intent from the buffer. Mastermind reads the buffer and the session name to decide what to type.

---

### TLS / HTTPS

**Browser shows "not secure" or refuses to connect** — Tailscale `.ts.net` domains are HSTS-preloaded; the browser requires HTTPS. Run `tailscale cert` and copy the cert + key into `certs/` as described in Quick Start step 3.

**Certificate expired** — Tailscale certs expire every ~90 days. Renew with `sudo tailscale cert <hostname>`, copy the new files to `certs/`, then `docker compose restart caddy`. Nexus's background TLS renewal task also checks automatically every 6 hours.

---

## Database Schema

Managed by Alembic (6 migrations in `backend/alembic/versions/`).

| Table | Purpose |
|-------|---------|
| `users` | Credentials, encrypted TOTP secret (AES-GCM), `mfa_method` (totp/email_otp), lockout state, TOTP replay fields |
| `sessions` | Session metadata: name, preset, status, cols/rows, workspace_id, timestamps |
| `ws_tokens` | Single-use WS auth tokens with JTI + expiry |
| `revoked_tokens` | Logout-revoked JWT JTIs; pruned when TTL expires |
| `audit_log` | Append-only log of auth and session events |
| `email_otp_codes` | Pending email OTP codes: bcrypt-hashed, 10-min TTL, single-use |
| `workspaces` | Named, color-coded workspace groups for organizing sessions |
| `pages` | Embedded HTTPS web pages (iframe tabs) |

---

## Security

### Authentication flow

1. User registers with email + password via `/api/auth/create-user`
2. User chooses MFA method (TOTP or Email OTP) via `/api/auth/setup-mfa`
3. On subsequent logins, POST email + password to `/api/auth/login`
4. Server returns `{needs_totp: true}` or `{needs_email_otp: true}` based on configured method
5. User can switch methods via "Use email code instead" / "Use authenticator instead" links
6. On success, an httpOnly/Secure/SameSite=Strict JWT cookie is set
7. WebSocket connections require a separate single-use token obtained via `/api/auth/ws-token`

### Hardening applied

| Category | Detail |
|----------|--------|
| Password hashing | bcrypt (12 rounds) on SHA-256 → base64 digest (avoids 72-byte truncation) |
| TOTP encryption | AES-256-GCM; key derived via PBKDF2-HMAC-SHA256 (600,000 rounds); nonce + AAD (user_id) per record |
| Timing attacks | Unknown usernames always run bcrypt to prevent user enumeration via response time |
| Rate limiting | slowapi: 10 login/min, 5/min bootstrap-totp & create-user, 30/min refresh, 20/min ws-token; Caddy pins `X-Real-IP`/`X-Forwarded-For` to the actual peer so header spoofing cannot bypass throttling |
| Account lockout | 5 failures → 15-minute lockout stored in DB; enforced at login and on every authenticated request |
| JWT revocation | Logout inserts JTI into `revoked_tokens`; `get_current_user` rejects revoked tokens |
| Sliding session | `POST /api/auth/refresh` re-issues the cookie; frontend calls it every 30 min so active tabs never hit the 24-hour hard TTL |
| WS token security | Tokens are single-use (atomic `UPDATE...WHERE used=0` prevents race conditions), expire in 60 s, and are bound to a specific session ID |
| TOTP replay protection | Successfully used codes are recorded (`last_totp_code` + `last_totp_at`); the same code is rejected for 90 s (the full `valid_window=1` window) |
| Security headers | CSP (`frame-ancestors 'none'`, `connect-src 'self'`), HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, Permissions-Policy |
| Log sanitization | Caddy strips query strings from access logs (WS tokens are query params) |
| Process cleanup | PTY kill sends SIGTERM then SIGKILL after 3 s in a background thread; zombie reap via `waitpid` |
| Subscriber cap | Max 5 concurrent WebSocket viewers per session |
| Session liveness | Only the background watchdog marks sessions stopped (every 5 s); the `list_sessions` endpoint never mutates status, preventing a frontend-poll race that killed healthy PTYs |
| Idle timeout | Sessions inactive for > 1 hour are stopped by the background watchdog |
| WebLinks filtering | xterm.js `WebLinksAddon` only opens `http://` or `https://` URLs |
| TOTP re-setup | Replacing an existing TOTP secret requires the current valid code — prevents session-hijack lockout. The Setup Authenticator modal auto-attempts setup; the "enter current code" prompt only appears when a secret already exists (HTTP 403). |
| Email OTP | 6-digit codes bcrypt-hashed in `email_otp_codes` table, 10-min TTL, single-use, previous codes invalidated on resend; `resend-otp` rate-limited at 3/min |
| Self-registration | Open registration with email validation; duplicate emails return 409; rate-limited at 5/min; MFA setup mandatory before first session access |
| Input validation | Session preset names validated at Pydantic level (alphanumeric, max 64 chars); error messages never echo raw user input |
| DB permissions | Database directory created with `0o700` — other local users cannot read hashed passwords or encrypted TOTP secrets |
| PTY input limiter | Per-session char/sec rate limiter rejects negative or oversized payloads |
| Orchestration API | `/api/orchestration/*` endpoints require auth + session ownership; input rate-limited; buffer capped at 1000 chunks via `deque(maxlen)` |
| Terminal classifier | Prompt/question pattern matching on ANSI-stripped output; conservative (false-positive safe) — never auto-types into a terminal without explicit user command |
| Dependencies | `python-jose` (CVEs) replaced with `PyJWT 2.8.0`; Docker client removed |

### Threat model

| Threat | Mitigation |
|--------|-----------|
| Stolen cookie | httpOnly (no JS access) + SameSite=Strict + short TTL + revocation on logout |
| Brute force | Rate limiting (429) on login, bootstrap-totp, and create-user + account lockout |
| Credential stuffing | Same as above; TOTP is a second factor |
| TOTP code replay | Accepted codes recorded with timestamp; reuse within 90 s rejected |
| TOTP secret theft | Encrypted at rest; key never stored beside data |
| JWT forgery | HS256 with ≥ 32-byte secret; PyJWT validates `exp`, `iat` |
| WS session hijack | Single-use tokens bound to session ID; expire in 60 s; atomic consume prevents race-condition reuse |
| TOTP lockout via hijacked session | Replacing TOTP secret requires entering current valid code |
| User enumeration via bootstrap-totp | All auth failures return identical 401 response |
| CSRF | SameSite=Strict cookie; API accepts form POST only from same origin |
| Clickjacking | `frame-ancestors 'none'` in CSP + `X-Frame-Options: DENY` |
| XSS via terminal output | xterm.js renders ANSI escape sequences, not HTML; strict CSP blocks inline scripts |
| Direct port 8000 exposure | Backend binds `0.0.0.0:8000` for Docker bridge; see firewall note in `start.sh` |

### Pre-production checklist

- [ ] Generate unique `APP_SECRET`, `JWT_SECRET`, `CRYPTO_SALT` — never reuse across installs
- [ ] Confirm `.env` is in `.gitignore` and never committed
- [ ] Access via Tailscale or VPN only — ensure port 8000 is firewalled from the internet
- [ ] Provision a TLS cert (`tailscale cert`) and configure Caddy for HTTPS
- [ ] Create your user account and set up the authenticator app
- [ ] On Linux: add `ufw deny 8000` to block direct backend access (see note in `start.sh`)
- [ ] Rotate secrets every 90 days (requires re-encrypting TOTP secrets with new key)
- [ ] Back up `~/.nexus/nexus.db` regularly (contains encrypted TOTP secrets and audit log)

---

## Development

### Backend

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Set required env vars for local dev
export APP_SECRET="dev-secret-at-least-32-characters-long"
export JWT_SECRET="dev-jwt-secret-at-least-32-chars-long"
export CRYPTO_SALT="dev-salt-16chars"
export CONFIG_PATH="../config.yml"

uvicorn app.main:app --reload --port 8000
```

Migrations run automatically on startup. To run manually:

```bash
DB_PATH=~/.nexus/nexus.db alembic upgrade head
```

### Frontend

```bash
cd frontend
npm install
npm run dev       # Vite dev server on :5173, proxies /api and /ws to :8000
npm run build     # Production build → dist/
```

### Testing

#### Backend (pytest)

```bash
cd backend
source .venv/bin/activate
pip install -r requirements-dev.txt   # pytest, pytest-asyncio, pytest-cov

pytest                          # run all tests
pytest -q                       # quiet output
pytest --cov=app --cov-report=term-missing   # with coverage
```

Tests use a temporary SQLite file per test (no `.env` required — fixtures inject test secrets). The full app lifespan is bypassed; real routers run against an in-memory schema.

| Suite | What's tested |
|---|---|
| `test_token_service.py` | JWT create/decode, expiry, tamper detection, WS token type guard |
| `test_auth.py` | Login (TOTP flow, lockout, timing-safe rejection), logout + revocation, `/me`, user creation, bootstrap TOTP |
| `test_sessions.py` | List (ownership isolation), create (PTY mocked), delete (ownership, 404) |

#### Frontend (vitest)

```bash
cd frontend
npm test                  # run once
npm run test:watch        # watch mode
npm run test:coverage     # with v8 coverage report
```

| Suite | What's tested |
|---|---|
| `store/authStore.test.ts` | Zustand state transitions |
| `hooks/useAuth.test.ts` | getMe success/failure, loading state, logout |
| `components/auth/LoginForm.test.tsx` | Render, empty-field error, TOTP step, redirect, 401/429 errors |

#### CI

Both suites run automatically via GitHub Actions (`.github/workflows/test.yml`) on every push and pull request.

### Project layout

```
nexus/
├── Caddyfile                  # Caddy reverse proxy config
├── config.yml                 # Non-secret runtime config
├── docker-compose.yml         # Caddy service
├── start.sh                   # One-command start script
├── .env                       # Secrets (gitignored)
├── certs/                     # TLS certificates (gitignored)
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app, lifespan, middleware wiring
│   │   ├── config.py          # Pydantic settings (YAML + env)
│   │   ├── crypto.py          # bcrypt, AES-GCM, PBKDF2
│   │   ├── database.py        # aiosqlite wrapper
│   │   ├── dependencies.py    # get_current_user (JWT + revocation + lockout)
│   │   ├── limiter.py         # slowapi rate limiter instance
│   │   ├── middleware/
│   │   │   └── security_headers.py
│   │   ├── models/
│   │   │   ├── audit.py       # AuditAction enum
│   │   │   ├── page.py        # Page model (embedded web pages)
│   │   │   ├── session.py     # Session dataclass + Pydantic models
│   │   │   ├── user.py
│   │   │   └── workspace.py   # Workspace model (color-coded groups)
│   │   ├── routers/
│   │   │   ├── auth.py        # Login, registration, MFA setup/switch, TOTP, email OTP
│   │   │   ├── health.py      # GET /api/health
│   │   │   ├── metrics.py     # GET /api/metrics (Prometheus format)
│   │   │   ├── orchestration.py # Buffer, input, state classification
│   │   │   ├── pages.py       # Embedded page CRUD
│   │   │   ├── sessions.py    # Session CRUD + restart/resize
│   │   │   ├── workspaces.py  # Workspace CRUD
│   │   │   └── ws.py          # WebSocket PTY proxy
│   │   └── services/
│   │       ├── auth_service.py      # authenticate_user (lockout, TOTP, email OTP)
│   │       ├── email_service.py     # SMTP email sender (smtplib)
│   │       ├── metrics.py           # In-process counters and gauges
│   │       ├── otp_service.py       # Email OTP generate/verify/cleanup
│   │       ├── process_watchdog.py  # Background: liveness, idle timeout, token cleanup
│   │       ├── pty_broadcaster.py   # Single PTY reader → N subscriber queues + ring buffer
│   │       ├── pty_service.py       # os.openpty + subprocess.Popen management
│   │       ├── rate_limiter.py      # Per-session input rate limiter
│   │       ├── recovery.py          # Session recovery (ring buffer serialization)
│   │       ├── session_service.py   # Session CRUD helpers
│   │       ├── terminal_classifier.py # WORKING/WAITING/ASKING/BUSY state detection
│   │       ├── tls_renewal.py       # Auto Tailscale cert renewal
│   │       └── token_service.py     # JWT create/decode (PyJWT)
│   └── alembic/
│       └── versions/
│           ├── 0001_initial_schema.py
│           ├── 0002_security_hardening.py  # revoked_tokens table
│           ├── 0003_totp_replay_protection.py
│           ├── 0004_workspaces.py
│           ├── 0005_pages.py
│           └── 0006_email_otp.py
└── frontend/
    └── src/
        ├── api/               # axios client, auth.ts, sessions.ts, orchestration.ts, workspaces.ts, pages.ts
        ├── components/
        │   ├── auth/          # LoginForm (7-step MFA), TotpForm, TotpSetupModal
        │   ├── terminal/      # TerminalPane, TerminalGrid, PriorityLayout, MobileKeybar
        │   └── ui/            # SessionList, OrchestratorPanel, PageList, HelpModal, HelpTooltip
        ├── hooks/             # useAuth, useSession, useTerminalSocket, useVisibilityReconnect, useInactivityDetector, useAutoPromote, …
        ├── pages/             # LoginPage, TerminalPage
        ├── store/             # Zustand: authStore, sessionStore, toastStore
        └── types/             # auth.ts, session.ts, ws.ts, workspace.ts, page.ts
```

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend framework | FastAPI 0.111 |
| Async database | aiosqlite 0.20 + Alembic 1.13 |
| Auth | PyJWT 2.8 · bcrypt 4.2 · pyotp 2.9 |
| Encryption | cryptography 43 (AES-256-GCM) |
| Rate limiting | slowapi 0.1.9 |
| PTY | `os.openpty` + `subprocess.Popen` (stdlib) |
| Frontend framework | React 18 + Vite 5 |
| Terminal emulator | xterm.js v5 |
| Styling | Tailwind CSS 3 |
| State management | Zustand |
| Reverse proxy | Caddy 2.8 |
| HTTPS | Tailscale cert (Let's Encrypt via `.ts.net`) |

---

## License

[MIT](LICENSE) — Copyright (c) 2026 Scott Soward
