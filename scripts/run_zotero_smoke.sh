#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
profile="$root/.runtime/zotero-smoke/profile"
if [[ ! -f "$profile/user.js" ]]; then
  echo "Run scripts/prepare_zotero_smoke.py first" >&2
  exit 2
fi
exec /Applications/Zotero.app/Contents/MacOS/zotero \
  -no-remote -profile "$profile" -ZoteroDebugText
