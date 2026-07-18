#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
python3 "$root/scripts/validate_zotero_plugin.py"
mkdir -p "$root/dist"
rm -f "$root/dist/atr-zotero-workbench.xpi"
# update.json is the remotely fetched update catalogue. Keeping it outside the
# XPI avoids a self-referential archive hash and mirrors Zotero's update flow.
(cd "$root/zotero-plugin" && zip -q -r "$root/dist/atr-zotero-workbench.xpi" . -x '*.DS_Store' 'update.json')
unzip -t "$root/dist/atr-zotero-workbench.xpi" >/dev/null
python3 "$root/scripts/validate_zotero_plugin.py" "$root/dist/atr-zotero-workbench.xpi"
echo "$root/dist/atr-zotero-workbench.xpi"
