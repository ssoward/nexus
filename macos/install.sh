#!/usr/bin/env bash
# Install the Nexus stack LaunchAgent + menu bar app on M5.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOME_DIR="$HOME"
LA_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$LA_DIR" "$HOME/.nexus/logs"

# 1. Detect tool paths (tailscale only exists at the app bundle path).
COLIMA_BIN="$(command -v colima || echo /opt/homebrew/bin/colima)"
DOCKER_BIN="$(command -v docker || echo /Applications/Docker.app/Contents/Resources/bin/docker)"
TAILSCALE_BIN="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
[[ -x "$TAILSCALE_BIN" ]] || TAILSCALE_BIN="$(command -v tailscale || true)"
[[ -n "$TAILSCALE_BIN" ]] || echo "WARNING: tailscale not found; TAILSCALE_BIN will be empty in nexus-paths.sh" >&2

# 2. Heavy setup (venv, deps, frontend build, static copy).
bash "$REPO_ROOT/scripts/nexus-setup.sh"

# 3. Render scripts/nexus-paths.sh.
sed -e "s#@COLIMA_BIN@#$COLIMA_BIN#g" \
    -e "s#@DOCKER_BIN@#$DOCKER_BIN#g" \
    -e "s#@TAILSCALE_BIN@#$TAILSCALE_BIN#g" \
    -e "s#@REPO_ROOT@#$REPO_ROOT#g" \
    "$REPO_ROOT/scripts/nexus-paths.sh.template" > "$REPO_ROOT/scripts/nexus-paths.sh"

# 4. Build + assemble + ad-hoc-sign Nexus.app.
( cd "$REPO_ROOT/macos/Nexus" && swift build -c release )
BIN="$REPO_ROOT/macos/Nexus/.build/release/Nexus"
APP="/Applications/Nexus.app"
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"
cp "$BIN" "$APP/Contents/MacOS/Nexus"
cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Nexus</string>
  <key>CFBundleIdentifier</key><string>net.ts.nexus.menubar</string>
  <key>CFBundleExecutable</key><string>Nexus</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0.0</string>
  <key>LSUIElement</key><true/>
  <key>LSMinimumSystemVersion</key><string>13.0</string>
</dict></plist>
PLIST
codesign --force --deep -s - "$APP"

# 5. Render + install plists.
PATH_VALUE="/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin:$REPO_ROOT/backend/.venv/bin"
for label in stack menubar; do
  sed -e "s#@REPO_ROOT@#$REPO_ROOT#g" \
      -e "s#@HOME@#$HOME_DIR#g" \
      -e "s#@PATH@#$PATH_VALUE#g" \
      "$REPO_ROOT/macos/com.nexus.$label.plist.template" \
      > "$LA_DIR/com.nexus.$label.plist"
  plutil -lint "$LA_DIR/com.nexus.$label.plist"
done

# 6. Write menu bar config.
ORIGIN="$(grep -E '^[[:space:]]*origin:' "$REPO_ROOT/config.yml" | head -1 | sed 's/.*origin:[[:space:]]*//')"
[[ -n "$ORIGIN" ]] || { echo "ERROR: 'origin:' not found in config.yml" >&2; exit 1; }
cat > "$HOME/.nexus/menubar.json" <<JSON
{"hostUrl":"$ORIGIN","repoPath":"$REPO_ROOT","caddyHostPort":"${CADDY_HOST_PORT:-8443}"}
JSON

# 7. (Re)bootstrap the stack agent.
UID_NUM="$(id -u)"
launchctl bootout "gui/$UID_NUM/com.nexus.stack" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$LA_DIR/com.nexus.stack.plist"

echo "Installed. Open /Applications/Nexus.app, then enable 'Launch at Login' from its menu."
echo "Stack agent loaded; check: launchctl print gui/$UID_NUM/com.nexus.stack"
