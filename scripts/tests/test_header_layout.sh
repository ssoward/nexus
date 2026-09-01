#!/usr/bin/env bash
# Regression test: the TerminalPage header must never clip its trailing
# controls (Sign out worst of all) at high display zoom.
#
# jsdom has no layout engine, so this cannot live in the vitest suite — it
# needs a real browser. The header's class list is read straight out of
# TerminalPage.tsx, so reintroducing `overflow-x-hidden` (or dropping
# `flex-wrap`) fails this test.
#
# Skips cleanly when Chrome or a frontend build is unavailable.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
PAGE="$REPO_ROOT/frontend/src/pages/TerminalPage.tsx"

CHROME="${CHROME_BIN:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
if [[ ! -x "$CHROME" ]]; then
  echo "SKIP: Chrome not found at '$CHROME' (set CHROME_BIN to override)"
  exit 0
fi

CSS="$(ls -t "$REPO_ROOT"/frontend/dist/assets/*.css 2>/dev/null | head -1)"
if [[ -z "$CSS" ]]; then
  echo "SKIP: no built CSS in frontend/dist/assets — run 'npm run build' first"
  exit 0
fi

# Pull the live header class list out of the source.
HEADER_CLASS="$(grep -o '<header className="[^"]*"' "$PAGE" | head -1 | sed 's/.*className="//; s/"$//')"
if [[ -z "$HEADER_CLASS" ]]; then
  echo "FAIL: could not find the header className in ${PAGE#"$REPO_ROOT/"}"
  exit 1
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp "$CSS" "$WORK/app.css"

fail=0
# Worst realistic cases: max zoom (200%) on a small phone, and mid zoom.
for spec in "390 2.0" "390 1.5" "320 1.4" "768 2.0"; do
  set -- $spec
  width="$1"; scale="$2"
  root_px="$(awk -v s="$scale" 'BEGIN{print 16*s}')"

  cat > "$WORK/h.html" <<EOF
<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="app.css">
<style>html{font-size:${root_px}px}body{margin:0}</style></head><body>
<div id="wrap" style="width:${width}px">
  <header class="${HEADER_CLASS}">
    <button class="p-1.5 rounded">M</button>
    <div class="flex items-center gap-0.5 mr-2">
      <button class="p-1.5 rounded">G</button><button class="p-1.5 rounded">P</button>
    </div>
    <div class="flex items-center shrink-0">
      <button class="px-1.5 py-1 text-xs">A-</button>
      <button class="px-1 text-[0.625rem]">100%</button>
      <button class="px-1.5 py-1 text-base">A+</button>
    </div>
    <span class="font-mono text-sm flex-1 min-w-0 basis-0 truncate">Nexus &mdash; 3 running</span>
    <button class="p-1.5 rounded shrink-0">R</button>
    <button class="p-1.5 rounded shrink-0">H</button>
    <button class="p-1.5 rounded shrink-0">L</button>
    <button id="signout" class="text-xs font-mono px-2 py-1 rounded shrink-0">Sign out</button>
  </header>
</div>
<script>
  var b = document.getElementById('signout').getBoundingClientRect();
  var c = document.getElementById('wrap').getBoundingClientRect();
  var ok = b.width > 0 && b.height > 0 &&
           b.right <= c.right + 0.5 && b.left >= c.left - 0.5;
  document.title = (ok ? 'VISIBLE' : 'CLIPPED') +
                   ' right=' + Math.round(b.right) + ' limit=' + Math.round(c.right);
</script></body></html>
EOF

  out="$("$CHROME" --headless=new --disable-gpu --no-sandbox \
        --virtual-time-budget=3000 --window-size="${width},900" \
        --dump-dom "file://$WORK/h.html" 2>/dev/null \
        | grep -o '<title>[^<]*</title>' | sed 's/<[^>]*>//g')"

  if [[ "$out" == VISIBLE* ]]; then
    echo "ok: Sign out reachable at ${scale}x zoom, ${width}px viewport ($out)"
  else
    echo "FAIL: Sign out not reachable at ${scale}x zoom, ${width}px viewport ($out)"
    fail=1
  fi
done

exit "$fail"
