#!/usr/bin/env python3
"""Compare a candidate XPI manifest with Zotero's registered add-on version.

Copying an XPI over an installed extension file does not cause Zotero to
reinstall it.  This read-only check makes that stale-registration state visible
before someone tries to diagnose old UI code as a new-plugin defect.
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path


def manifest_from_xpi(path: Path) -> dict:
    with zipfile.ZipFile(path) as archive:
        return json.loads(archive.read("manifest.json"))


def registered_addon(profile: Path, addon_id: str) -> dict | None:
    registry = json.loads((profile / "extensions.json").read_text(encoding="utf-8"))
    return next((item for item in registry.get("addons", []) if item.get("id") == addon_id), None)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("xpi", type=Path)
    parser.add_argument("profile", type=Path)
    args = parser.parse_args()
    manifest = manifest_from_xpi(args.xpi)
    addon = registered_addon(args.profile, manifest["applications"]["zotero"]["id"])
    report = {
        "candidate_id": manifest["applications"]["zotero"]["id"],
        "candidate_version": manifest["version"],
        "registered": addon is not None,
        "registered_version": addon.get("version") if addon else None,
        "active": addon.get("active") if addon else False,
        "user_disabled": addon.get("userDisabled") if addon else None,
    }
    report["matches_candidate"] = bool(addon and addon.get("version") == manifest["version"])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["matches_candidate"] and report["active"] and not report["user_disabled"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
