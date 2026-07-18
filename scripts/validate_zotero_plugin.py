#!/usr/bin/env python3
"""Fast contract checks for the Zotero bootstrapped-extension surface.

These checks intentionally cover the documented contracts that can be checked
without launching Zotero: manifest metadata, lifecycle hooks, update manifest,
and the current Zotero main-window menu ID. They complement (not replace) a
small smoke test in an isolated Zotero development profile.
"""
from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "zotero-plugin"
ADDON_ID = "atr-zotero-workbench@24kmengxin.github.io"
REQUIRED_ROOT_FILES = {"manifest.json", "bootstrap.js", "prefs.js", "atr-zotero-workbench.js", "update.json"}
REQUIRED_PACKAGED_FILES = REQUIRED_ROOT_FILES | {"chrome/content/workbench/index.html"}


def fail(message: str) -> None:
    raise ValueError(message)


def validate_source() -> None:
    manifest = json.loads((PLUGIN / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("manifest_version") != 2:
        fail("manifest_version must be 2")
    zotero = manifest.get("applications", {}).get("zotero", {})
    for field in ("id", "update_url", "strict_min_version", "strict_max_version"):
        if not zotero.get(field):
            fail(f"applications.zotero.{field} is required")
    if zotero["id"] != ADDON_ID:
        fail("manifest add-on ID differs from the canonical ID")

    update = json.loads((PLUGIN / "update.json").read_text(encoding="utf-8"))
    if not isinstance(update.get("addons", {}).get(ADDON_ID, {}).get("updates"), list):
        fail("update.json must provide an updates list for this add-on ID")

    bootstrap = (PLUGIN / "bootstrap.js").read_text(encoding="utf-8")
    for hook in ("startup", "shutdown", "install", "uninstall", "onMainWindowLoad", "onMainWindowUnload"):
        if f"function {hook}" not in bootstrap and f"function {hook}(" not in bootstrap and f"async function {hook}" not in bootstrap:
            fail(f"bootstrap.js is missing {hook}()")

    runtime = (PLUGIN / "atr-zotero-workbench.js").read_text(encoding="utf-8")
    if 'getElementById("menu_ToolsPopup")' not in runtime:
        fail("plugin must target Zotero 9's menu_ToolsPopup")
    if re.search(r'getElementById\(["\']menu_toolsPopup["\']\)', runtime):
        fail("legacy menu_toolsPopup must not be used")
    if "IOUtils.readUTF8" not in runtime or 'getElementById("zotero-pane-stack")' not in runtime:
        fail("workbench must render its projection in Zotero's main window")
    for stage in ("startup_complete", "overlay_mounted", "projection_loaded", "render_completed", "render_failed", "review_note_opened"):
        if stage not in runtime:
            fail(f"workbench must emit runtime stage {stage!r} for development verification")
    if "Zotero.File.createDirectoryIfMissingAsync" not in runtime or "Zotero.File.putContentsAsync" not in runtime:
        fail("workbench audit writes must use Zotero's file API")
    if "你的阅读反馈" not in runtime or "human_note_modified" not in runtime:
        fail("workbench must visibly connect captured human notes to the projection")
    if "知识体系：" not in runtime or "illustrated_by_question_anchor" not in runtime:
        fail("workbench must visibly distinguish concept-to-reading context links")
    if "建立 / 打开我的阅读笔记" not in runtime or 'event === "modify"' not in runtime:
        fail("workbench must provide an explicit human-review note entry point")
    if "现实世界启发（不是学术证据）" not in runtime or "inspired_by_context" not in runtime:
        fail("workbench must keep real-world inspiration separate from scholarly evidence")
    if "registerChrome" not in bootstrap:
        fail("bootstrap.js must register the workbench chrome content")


def validate_xpi(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        missing = REQUIRED_PACKAGED_FILES - names
        if missing:
            fail(f"XPI lacks required root files: {sorted(missing)}")
        packaged = json.loads(archive.read("manifest.json"))
        source = json.loads((PLUGIN / "manifest.json").read_text(encoding="utf-8"))
        if packaged != source:
            fail("XPI manifest differs from source manifest")


def main() -> None:
    validate_source()
    if len(sys.argv) == 2:
        validate_xpi(Path(sys.argv[1]))
    print("Zotero plugin contract checks passed")


if __name__ == "__main__":
    main()
