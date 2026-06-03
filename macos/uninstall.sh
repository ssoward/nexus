#!/usr/bin/env bash
set -uo pipefail
UID_NUM="$(id -u)"
LA_DIR="$HOME/Library/LaunchAgents"
for label in stack menubar; do
  launchctl bootout "gui/$UID_NUM/com.nexus.$label" 2>/dev/null || true
  rm -f "$LA_DIR/com.nexus.$label.plist"
done
rm -rf /Applications/Nexus.app
echo "Uninstalled launch agents and app. ~/.nexus data left intact."
