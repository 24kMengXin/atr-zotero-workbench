#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
python3 "$root/scripts/validate_zotero_plugin.py"
mkdir -p "$root/dist"
mkdir -p "$root/zotero-plugin/workbench"
# Snapshot the generated, self-contained dashboard into the XPI.  A page in
# the add-on's root URI can be opened by Zotero's content browser, unlike a
# local file:// URL from an arbitrary workspace.
cp "$root/output/multilingual/index.html" "$root/zotero-plugin/workbench/index.html"
rm -f "$root/dist/atr-zotero-workbench.xpi"
(cd "$root/zotero-plugin" && zip -q -r "$root/dist/atr-zotero-workbench.xpi" . -x '*.DS_Store')
unzip -t "$root/dist/atr-zotero-workbench.xpi" >/dev/null
python3 "$root/scripts/validate_zotero_plugin.py" "$root/dist/atr-zotero-workbench.xpi"
echo "$root/dist/atr-zotero-workbench.xpi"
