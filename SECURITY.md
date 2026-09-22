# Security

Nexus turns a browser tab into a shell on the host it runs on. Its security
boundary is **authentication and network reach**, not process isolation: every
terminal session runs as the same OS user as the backend. Read the threat model
below before exposing an instance to anything wider than your own tailnet.

## Reporting a vulnerability

Open a GitHub issue titled `security:` **without** exploit details, or e-mail
the repository owner directly. Include the commit hash and, if possible, a
minimal reproduction. Please allow time for a fix before publishing details.

## Threat model in one paragraph

An instance is meant to be reachable only over a private Tailscale network,
served by Caddy bound to loopback and exposed through `tailscale serve`. Every
request needs a password **and** a second factor (passkey, authenticator app,
or opt-in e-mail codes); changing how the account signs in requires a second
factor verified within the last five minutes. Anything a signed-in user can do,
a process inside one of their sessions can also do to the host — that is the
product, so protect the account and the host equally.

## What is enforced

| Area | Control |
|------|---------|
| Passwords | bcrypt(12) over a SHA-256 digest; 16+ chars with complexity; 5 failures lock the credential endpoints for 15 min (not already-issued sessions, not passkeys) |
| Second factor | Passkeys with user verification, TOTP with replay guard, or explicitly enrolled e-mail codes. `/switch-mfa` only selects enrolled factors and is audited + e-mailed |
| Step-up | Password/e-mail change, account deletion, authenticator enrolment, passkey add/remove and the e-mail-code toggle require `mfa_time` within 300 s (`403 step_up_required` otherwise) |
| Session cookie | `__Host-access_token`: HttpOnly, Secure, SameSite=Strict, Path=/; 30-day TTL slid on refresh; hard 30-day ceiling from the original login; revocation on logout and on credential change |
| CSRF / WS hijack | SameSite=Strict **and** `OriginCheckMiddleware` (`Sec-Fetch-Site` / `Origin`) on every state-changing request and on the WebSocket handshake; WS tokens are single-use, 60 s, carried in the subprotocol header |
| Secrets at rest | TOTP secrets AES-GCM under a PBKDF2 (600k) key; recovery scrollback encrypted; `.env` and the SQLite DB expected at mode 0600 (startup warns otherwise) |
| Session environment | Allowlist (`PATH`, `HOME`, `SHELL`, `LANG`, `LC_*`, `XDG_*`, `TMPDIR`, `TZ`, `SSH_AUTH_SOCK`) plus `config.yml` → `session.pass_env`; the app's own secrets are never forwarded |
| Network | Backend on `127.0.0.1:8000`; Caddy on `127.0.0.1:8443`; tailnet access via `tailscale serve`; forwarded-IP headers trusted only from loopback / RFC 1918 proxies |
| Headers | Strict CSP (no inline script), HSTS preload, `frame-ancestors 'none'`, `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff` |
| Supply chain | `pip-audit`, `npm audit` and `bandit` run in CI on every push |

## Operator responsibilities

- Keep `.env` (all secrets) and `~/.nexus/nexus.db` at mode `0600`.
- Set `NEXUS_HOST`, `RP_ID`, `WEBAUTHN_ORIGIN` per machine in `.env`; never in tracked files.
- Keep `CADDY_BIND=127.0.0.1` and confirm `tailscale funnel` is off.
- Set `NEXUS_SETUP_TOKEN` before first start on a network you do not fully control; remove it after the owner account exists.
- Keep SMTP configured so security notifications and recovery e-mails work.
- Treat anything listed in `session.pass_env` as readable by every session.
- Rotate `JWT_SECRET` (forces re-login everywhere) if you suspect cookie theft.

## Out of scope

- Isolating one session from another, or from the host: all sessions run as the Nexus user.
- Multi-tenant use: an instance has exactly one owner account.
- Protecting against a compromised host, browser, or Tailscale account.
