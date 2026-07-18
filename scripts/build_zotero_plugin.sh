#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
python3 "$root/scripts/validate_zotero_plugin.py"
mkdir -p "$root/dist"
rm -f "$root/dist/atr-zotero-workbench.xpi"
# update.json is the remotely fetched update catalogue. Keeping it outside the
# XPI avoids a self-referential archive hash and mirrors Zotero's update flow.
# A sorted file list plus `zip -X` makes repeated builds byte-for-byte stable,
# so the hash advertised to Zotero cannot drift without a source change.
(cd "$root/zotero-plugin" && find . -type f ! -name '*.DS_Store' ! -name 'update.json' -print \
  | LC_ALL=C sort | zip -X -q "$root/dist/atr-zotero-workbench.xpi" -@)
unzip -t "$root/dist/atr-zotero-workbench.xpi" >/dev/null
python3 "$root/scripts/validate_zotero_plugin.py" "$root/dist/atr-zotero-workbench.xpi"
echo "$root/dist/atr-zotero-workbench.xpi"
