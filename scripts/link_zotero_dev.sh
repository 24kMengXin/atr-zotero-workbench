#!/usr/bin/env bash
# Side-load this source tree into a dedicated Zotero development profile.
# Usage: ./scripts/link_zotero_dev.sh /absolute/path/to/Zotero/Profile /absolute/path/to/dev-data-dir
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 /absolute/path/to/Zotero/Profile /absolute/path/to/dev-data-dir" >&2
  exit 2
fi

profile=$1
data_dir=$2
root=$(cd "$(dirname "$0")/.." && pwd)
addon_id='atr-zotero-workbench@24kmengxin.github.io'

if [[ ! -d "$profile" ]]; then
  echo "Zotero profile directory does not exist: $profile" >&2
  exit 2
fi
mkdir -p "$data_dir"

# Validate and package once before linking so the source tree and candidate XPI
# are checked against the same native-Zotero contracts.
bash "$root/scripts/build_zotero_plugin.sh" >/dev/null

mkdir -p "$profile/extensions"
proxy="$profile/extensions/$addon_id"
printf '%s\n' "$root/zotero-plugin" > "$proxy"

# A Firefox profile alone does not isolate Zotero's library: Zotero can retain
# the normal data-directory preference. user.js is deliberately used here so
# this development-only profile always selects an empty, separate database.
printf '%s\n' \
  '// Managed by atr-zotero-workbench/scripts/link_zotero_dev.sh' \
  '// This profile is disposable and dedicated to source-side-loaded extensions.' \
  'user_pref("extensions.autoDisableScopes", 0);' \
  'user_pref("extensions.zotero.useDataDir", true);' \
  "user_pref(\"extensions.zotero.dataDir\", \"$data_dir\");" \
  > "$profile/user.js"

echo "Created Zotero development proxy: $proxy"
echo "Configured isolated Zotero data directory: $data_dir"
echo "Restart the Zotero instance using this development profile."
