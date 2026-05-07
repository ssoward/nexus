# Nexus — Claude Code Project Guidelines

## Definition of Done

Every code change task MUST complete this full cycle without being prompted:

1. **Implement** the change
2. **Test** — run `cd frontend && npm run build` (typecheck + build); run backend tests if backend changed (`cd backend && python -m pytest -q`)
3. **README** — update `README.md` if any behavior, config, env var, API, or setup step changed
4. **Redeploy local (M5)** — copy `frontend/dist/*` to `static/` after a frontend build
5. **Redeploy M1** — `ssh ssoward@ssowardm1.tail040188.ts.net "cd ~/sandbox/Workspace/nexus && git pull && export PATH=/opt/homebrew/bin:/opt/homebrew/Cellar/node/25.9.0_1/bin:\$PATH && cd frontend && npm run build && cp -r dist/* ../static/ && echo M1 OK"`
6. **Commit** with a conventional commit message
7. **Push** to `origin main`

Do not stop after code changes. Do not wait to be asked. If a step is not applicable, state why explicitly.

## Deployment Targets

This project runs on TWO machines. Both must be updated after any frontend or backend change:

| Target | Method |
|--------|--------|
| M5 (local) | `cp -r frontend/dist/* static/` after build; backend reads files from disk, no restart needed |
| M1 (remote) | SSH via `ssoward@ssowardm1.tail040188.ts.net` using the npm path above |

Backend runs as a native process (not Docker). Frontend is served as static files from `static/`. Caddy (Docker) handles TLS and proxying — no restart needed for frontend changes.

## Project Structure

- `backend/` — FastAPI app, Python 3.11+, virtualenv at `backend/.venv`
- `frontend/` — React + Vite + TypeScript, build output → `frontend/dist/`
- `static/` — live-served frontend (copy of `dist/`)
- `config.yml` — non-secret runtime config
- `.env` — secrets (never commit)

## Shell Conventions

- Never run interactive commands (`ssh-copy-id`, `gh auth login`, `claude auth login`) as Bash calls — print the command for the user to run instead
- Use `ssoward@ssowardm1.tail040188.ts.net` for M1 SSH (not `192.168.1.66` — unreliable)
- Always set `PATH=/opt/homebrew/bin:/opt/homebrew/Cellar/node/25.9.0_1/bin:$PATH` when running npm/node on M1 via SSH

## Git Conventions

- Before adding any directory to `.gitignore`, list its contents and confirm it contains no tracked source code
- Commit messages follow Conventional Commits: `feat:`, `fix:`, `docs:`, `chore:`, `security:`
- Always include `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>` in commit messages

## Working Directory

Always check the current working directory (`pwd` + `ls`) before asking the user to provide files — the relevant files are almost always already in the repo.
