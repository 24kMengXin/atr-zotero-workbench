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
REQUIRED_PACKAGED_FILES = REQUIRED_ROOT_FILES | {
    "locale/en-US/atr-mainWindow.ftl",
    "locale/zh-CN/atr-mainWindow.ftl",
}


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
    if "IOUtils.readUTF8" not in runtime:
        fail("plugin must load the registered ATR projection")
    if 'getElementById("zotero-pane-stack")' in runtime or "overlay_mounted" in runtime:
        fail("plugin must not mount an independent full-window overlay")
    for stage in (
        "startup_complete",
        "native_topic_menu_added",
        "native_item_pane_registered",
        "projection_loaded",
        "native_topic_synced",
        "native_note_tab_opened",
        "native_reader_tab_opened",
        "native_reader_annotation_opened",
        "process_note_created",
        "human_review_stance_selected",
        "review_queue_loaded",
    ):
        if stage not in runtime:
            fail(f"native projection must emit runtime stage {stage!r}")
    if "Zotero.File.createDirectoryIfMissingAsync" not in runtime or "Zotero.File.putContentsAsync" not in runtime:
        fail("workbench audit writes must use Zotero's file API")
    for native_contract in (
        "Zotero.ItemPaneManager.registerSection",
        "Zotero.Reader.open",
        "Zotero.Notes.open",
        "ensureTopicCollection",
        "ensureTopicNote",
        "ensureProcessNote",
        "ensureSourceReviewNote",
        "ensureProblemNote",
        "ensureClaimNote",
        "ensureReviewAssessmentNote",
        "ensureKnowledgeNote",
        "ensureKnowledgeProjection",
        "ensureResearchNodeNote",
        "ensureResearchProjection",
    ):
        if native_contract not in runtime:
            fail(f"plugin is missing native Zotero contract {native_contract!r}")
    if "human_note_modified" not in runtime or "human_annotation_modified" not in runtime:
        fail("plugin must relay both explicit notes and native Reader annotations")
    if "annotationID: annotation.key" not in runtime:
        fail("plugin must reopen a selected native annotation at its exact Reader location")
    if "zotero://open-pdf/" not in runtime or "getGroupIDFromLibraryID" not in runtime or "zotero_open_uri" not in runtime:
        fail("plugin must capture user/group-aware Codex-to-Reader annotation deep links at event time")
    if "review-queue.json" not in runtime or "pendingReviewItems" not in runtime:
        fail("plugin must display the Codex-derived pending review queue without mutating lifecycle")
    if ("ATR Topic Run:" not in runtime or "ATR Process Run:" not in runtime or "ATR Source ID:" not in runtime
            or "ATR Problem ID:" not in runtime or "ATR Graph Node:" not in runtime
            or "ATR Knowledge Node:" not in runtime or "ATR Tension Node:" not in runtime
            or "ATR Research Question Node:" not in runtime or "ATR Derived Question Node:" not in runtime):
        fail("plugin must scope human feedback with stable ATR markers")
    if "ATR Review Assessment:" not in runtime or "human_review_assessment" not in runtime:
        fail("plugin must project isolated human-review assessments as native Zotero Notes")
    for stance in ("SUPPORTS", "QUALIFIES", "CHALLENGES", "UNSURE", "NEW_QUESTION"):
        if stance not in runtime:
            fail(f"plugin must expose typed human review stance {stance!r}")
    if "本 Note 由实际落盘的 ATR timeline 生成" not in runtime:
        fail("process Note must distinguish recorded ATR events from inferred history")
    for collection_role in (
        "research_tensions", "research_frontier", "research_current", "research_claims", "research_reviews",
    ):
        if collection_role not in runtime:
            fail(f"plugin must materialize native research collection role {collection_role!r}")
    if '["add", "modify"].includes(event)' not in runtime or 'event === "modify" && item?.isNote?.()' not in runtime:
        fail("plugin must observe new/modified annotations without treating newly generated Notes as human input")
    if "loadRunRegistry" not in runtime or "打开 Topic" not in runtime:
        fail("plugin must expose registered topics through the Zotero Tools menu")
    if "EXPLICIT_ACTIVATION_ONLY" not in runtime or "NAVIGATION_ONLY" not in runtime:
        fail("plugin must distinguish explicit lifecycle authority from historical navigation")
    if "native-projection.json" not in runtime or "atr-zotero-native-map" not in runtime:
        fail("plugin must consume the explicit, testable native Zotero mapping")
    if "objectIDs.has(object.object_id)" not in runtime or "APPEND_ONLY_PRESERVE_OLD_NODES_AND_EDGES" not in runtime:
        fail("plugin must reject duplicate objects and lifecycle-unsafe native maps before rendering")
    if "actual[field] !== expected[field]" not in runtime:
        fail("versioned Note lookup must compare parsed ATR markers exactly, not by string prefix")
    if "entering degraded mode" not in runtime or "配置错误 · 查看详情" not in runtime:
        fail("plugin must expose registry failures in Zotero instead of disappearing at startup")
    if "registerChrome" in bootstrap or "chrome/content/workbench" in bootstrap:
        fail("bootstrap must not register the retired standalone workbench page")


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
