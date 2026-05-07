# /ship — Full Release Cycle

Run the complete ship-it pipeline for any pending changes. Do not stop early.

## Steps (execute in order)

1. **Typecheck + build frontend**
   ```bash
   cd frontend && npm run build
   ```
   Fix any TypeScript or build errors before continuing.

2. **Run backend tests** (if any backend files changed)
   ```bash
   cd backend && source .venv/bin/activate && python -m pytest -q
   ```

3. **Update README.md** if any behavior, config, env var, API endpoint, or setup step changed. Be specific — don't update if nothing user-facing changed.

4. **Deploy to M5 (local)**
   ```bash
   cp -r frontend/dist/* static/
   ```

5. **Deploy to M1 (remote)**
   ```bash
   ssh ssoward@ssowardm1.tail040188.ts.net "cd ~/sandbox/Workspace/nexus && git pull && export PATH=/opt/homebrew/bin:/opt/homebrew/Cellar/node/25.9.0_1/bin:\$PATH && cd frontend && npm run build && cp -r dist/* ../static/ && echo M1 OK"
   ```

6. **Commit** all staged and unstaged changes with a conventional commit message summarizing what changed and why.

7. **Push** to `origin main`.

8. **Report** — state: tests passed/skipped, files changed, both deploy targets confirmed, commit SHA.

## Notes

- If SAML/SSH blocks the push, output the exact manual command needed and stop.
- If M1 SSH fails, deploy locally and push — note that M1 needs a manual `git pull` when back online.
- Backend changes that require a restart: `pkill -f uvicorn && cd backend && source .venv/bin/activate && uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info &`
