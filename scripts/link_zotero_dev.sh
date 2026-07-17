#!/usr/bin/env bash
# Side-load this source tree into a dedicated Zotero development profile.
# Usage: ./scripts/link_zotero_dev.sh /absolute/path/to/Zotero/Profile
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /absolute/path/to/Zotero/Profile" >&2
  exit 2
fi

profile=$1
root=$(cd "$(dirname "$0")/.." && pwd)
addon_id='atr-zotero-workbench@24kmengxin.github.io'

if [[ ! -d "$profile" ]]; then
  echo "Zotero profile directory does not exist: $profile" >&2
  exit 2
fi

# The generated dashboard is part of the development add-on too. Building it
# first keeps the source proxy and release package on the same artifact.
bash "$root/scripts/build_zotero_plugin.sh" >/dev/null

mkdir -p "$profile/extensions"
proxy="$profile/extensions/$addon_id"
printf '%s\n' "$root/zotero-plugin" > "$proxy"

echo "Created Zotero development proxy: $proxy"
echo "Restart the Zotero instance using this development profile."
