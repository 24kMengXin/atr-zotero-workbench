#!/usr/bin/env bash
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
run_dir=${ATR_RUN_DIR:-/Users/zone/Documents/multilingual-aaai/research-runs/2026-07-17-controlled-multilingual-discovery}
output_dir=${ATR_WORKBENCH_OUT:-$root/output/multilingual}
registry_path=${ATR_RUN_REGISTRY:-$root/output/runs.json}
if [[ ! -d "$run_dir" ]]; then
  echo "ATR run directory does not exist: $run_dir" >&2
  echo "Set ATR_RUN_DIR to the run that should be projected into the plugin." >&2
  exit 2
fi
PYTHONPATH="$root/src${PYTHONPATH:+:$PYTHONPATH}" python3 -m atr_zotero_workbench.app build "$run_dir" --out "$output_dir" --registry "$registry_path" --run-key "$(basename "$output_dir")" >/dev/null
python3 "$root/scripts/validate_zotero_plugin.py"
mkdir -p "$root/dist"
mkdir -p "$root/zotero-plugin/chrome/content/workbench"
# Snapshot the generated, self-contained dashboard into the XPI. Zotero's
# native content browser opens this through the add-on's registered chrome://
# namespace, rather than an arbitrary file:// workspace URL.
cp "$output_dir/index.html" "$root/zotero-plugin/chrome/content/workbench/index.html"
rm -f "$root/dist/atr-zotero-workbench.xpi"
(cd "$root/zotero-plugin" && zip -q -r "$root/dist/atr-zotero-workbench.xpi" . -x '*.DS_Store')
unzip -t "$root/dist/atr-zotero-workbench.xpi" >/dev/null
python3 "$root/scripts/validate_zotero_plugin.py" "$root/dist/atr-zotero-workbench.xpi"
echo "$root/dist/atr-zotero-workbench.xpi"
