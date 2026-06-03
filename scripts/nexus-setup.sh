#!/usr/bin/env bash
# One-time / on-demand heavy setup: venv, python deps, frontend build, static copy.
# NOT run by the LaunchAgent. Run by install.sh and manually after dep changes.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$REPO_ROOT/backend"
FRONTEND="$REPO_ROOT/frontend"

if [[ ! -d "$BACKEND/.venv" ]]; then
  echo "Creating venv..."; python3 -m venv "$BACKEND/.venv"
fi
# shellcheck source=/dev/null
source "$BACKEND/.venv/bin/activate"
pip install -q --upgrade pip
pip install -q -r "$BACKEND/requirements.txt"

echo "Building frontend..."
( cd "$FRONTEND" && npm install --silent && npm run build --silent )

echo "Copying dist -> static..."
# Clear first: Vite emits content-hashed filenames, so a plain copy would leave
# stale bundles from previous builds piling up in the live-served directory.
rm -rf "$REPO_ROOT/static"
mkdir -p "$REPO_ROOT/static"
cp -r "$FRONTEND/dist/." "$REPO_ROOT/static/"
echo "Setup complete."
