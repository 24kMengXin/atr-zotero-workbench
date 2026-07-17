#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$root/dist"
rm -f "$root/dist/atr-zotero-workbench.xpi"
(cd "$root/zotero-plugin" && zip -q -r "$root/dist/atr-zotero-workbench.xpi" . -x '*.DS_Store')
unzip -t "$root/dist/atr-zotero-workbench.xpi" >/dev/null
echo "$root/dist/atr-zotero-workbench.xpi"
