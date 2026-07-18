#!/usr/bin/env python3
"""Compare a candidate XPI manifest with Zotero's registered add-on version.

Copying an XPI over an installed extension file does not cause Zotero to
reinstall it.  This read-only check makes that stale-registration state visible
before someone tries to diagnose old UI code as a new-plugin defect.
"""
from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path


def manifest_from_xpi(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        return json.loads(archive.read("manifest.json"))


def registered_addon(profile: Path, addon_id: str) -> dict | None:
    registry = json.loads((profile / "extensions.json").read_text(encoding="utf-8"))
    return next((item for item in registry.get("addons", []) if item.get("id") == addon_id), None)


def boolean_pref(profile: Path, name: str, default: bool) -> bool:
    prefs = profile / "prefs.js"
    if not prefs.exists():
        return default
    pattern = re.compile(rf'^user_pref\("{re.escape(name)}",\s*(true|false)\);$')
    for line in prefs.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line.strip())
        if match:
            return match.group(1) == "true"
    return default


def update_policy(addon: dict | None, global_default: bool) -> tuple[str | None, bool | None]:
    if not addon:
        return None, None
    # Mozilla AddonManager constants: 0=disable, 1=follow global default,
    # 2=enable. Zotero persists the value in extensions.json.
    value = addon.get("applyBackgroundUpdates", 1)
    labels = {0: "DISABLED", 1: "FOLLOW_GLOBAL", 2: "ENABLED"}
    effective = False if value == 0 else True if value == 2 else global_default
    return labels.get(value, f"UNKNOWN:{value}"), effective


def build_report(xpi: Path, profile: Path) -> dict:
    manifest = manifest_from_xpi(xpi)
    zotero_manifest = manifest["applications"]["zotero"]
    addon = registered_addon(profile, zotero_manifest["id"])
    global_updates = boolean_pref(profile, "extensions.update.autoUpdateDefault", True)
    policy, effective_updates = update_policy(addon, global_updates)
    report = {
        "candidate_id": zotero_manifest["id"],
        "candidate_version": manifest["version"],
        "candidate_update_url": zotero_manifest.get("update_url"),
        "registered": addon is not None,
        "registered_version": addon.get("version") if addon else None,
        "registered_update_url": addon.get("updateURL") if addon else None,
        "active": addon.get("active") if addon else False,
        "user_disabled": addon.get("userDisabled") if addon else None,
        "global_auto_update_default": global_updates,
        "addon_background_update_policy": policy,
        "effective_background_updates": effective_updates,
        "registered_source_uri": addon.get("sourceURI") if addon else None,
    }
    report["matches_candidate"] = bool(addon and addon.get("version") == manifest["version"])
    report["stale_reason"] = (
        "BACKGROUND_UPDATES_DISABLED_BY_PROFILE_DEFAULT"
        if addon and not report["matches_candidate"] and policy == "FOLLOW_GLOBAL" and not global_updates
        else None
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("xpi", type=Path)
    parser.add_argument("profile", type=Path)
    args = parser.parse_args()
    report = build_report(args.xpi, args.profile)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["matches_candidate"] and report["active"] and not report["user_disabled"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
