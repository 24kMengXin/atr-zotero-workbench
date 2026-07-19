#!/usr/bin/env python3
"""Fast contract checks for the Zotero bootstrapped-extension surface.

These checks intentionally cover the documented contracts that can be checked
without launching Zotero: manifest metadata, lifecycle hooks, update manifest,
and the current Zotero main-window menu ID. They complement (not replace) a
small smoke test in an isolated Zotero development profile.
"""
from __future__ import annotations

import json
import hashlib
import re
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "zotero-plugin"
ADDON_ID = "atr-zotero-workbench@24kmengxin.github.io"
REQUIRED_ROOT_FILES = {
    "manifest.json", "bootstrap.js", "prefs.js", "atr-zotero-workbench.js",
    "update.json", "companion.xhtml",
}
REQUIRED_PACKAGED_FILES = (REQUIRED_ROOT_FILES - {"update.json"}) | {
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
    updates = update.get("addons", {}).get(ADDON_ID, {}).get("updates")
    if not isinstance(updates, list):
        fail("update.json must provide an updates list for this add-on ID")
    matching = [entry for entry in updates if entry.get("version") == manifest.get("version")]
    if len(matching) != 1:
        fail("update.json must provide exactly one entry for the current manifest version")
    entry = matching[0]
    if not re.fullmatch(r"https://[^\s]+\.xpi", entry.get("update_link", "")):
        fail("current update entry must use an HTTPS .xpi update_link")
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", entry.get("update_hash", "")):
        fail("current update entry must provide a lowercase sha256 update_hash")
    update_zotero = entry.get("applications", {}).get("zotero", {})
    for field in ("strict_min_version", "strict_max_version"):
        if update_zotero.get(field) != zotero.get(field):
            fail(f"update entry applications.zotero.{field} must match manifest.json")

    bootstrap = (PLUGIN / "bootstrap.js").read_text(encoding="utf-8")
    for hook in ("startup", "shutdown", "install", "uninstall", "onMainWindowLoad", "onMainWindowUnload"):
        if f"function {hook}" not in bootstrap and f"function {hook}(" not in bootstrap and f"async function {hook}" not in bootstrap:
            fail(f"bootstrap.js is missing {hook}()")
    if ("aomStartup.registerChrome" not in bootstrap
            or '["content", "atr-zotero-workbench", rootURI]' not in bootstrap
            or "chromeHandle.destruct()" not in bootstrap):
        fail("plugin must register and release its packaged companion-window content URL")

    runtime = (PLUGIN / "atr-zotero-workbench.js").read_text(encoding="utf-8")
    projection_source = (ROOT / "src" / "atr_zotero_workbench" / "zotero.py").read_text(encoding="utf-8")
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
        "native_reader_note_section_registered",
        "native_reader_note_section_ready",
        "reading_visual_context_rendered",
        "native_reader_note_section_fallback",
        "dev_smoke_reader_note_section_ready",
        "native_reader_tab_opened",
        "native_reader_annotation_opened",
        "process_note_created",
        "human_review_stance_selected",
        "human_owner_route_input_selected",
        "dev_smoke_owner_route_input_saved",
        "review_queue_loaded",
        "co_reading_dock_rendered",
        "co_reading_dock_probe_passed",
        "co_reading_companion_opened",
        "three_surface_coreading_ready",
        "dev_smoke_three_surface_coreading_ready",
        "dev_smoke_three_surface_probe",
        "portfolio_program_opened",
        "dev_smoke_portfolio_program_target_resolved",
        "dev_smoke_portfolio_program_opened",
        "portfolio_program_owner_review_opened",
        "dev_smoke_portfolio_owner_review_opened",
        "dev_smoke_portfolio_returned",
        "portfolio_registry_materialized",
        "portfolio_child_materialized",
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
    for dock_contract in (
        "appendCoReadingDock", "appendDockDisclosure", "nearestGraphNodes", "appendMiniGraph",
        '"项目历史 / 过程"', '"知识定位"', '"现实问题 / 研究问题"', '"当前对象"',
        "extensions.atr-zotero-workbench.dock.", 'aria-label", "ATR 当前对象局部关系图',
        "mini_graph_count", "appendPortfolioGraph",
        'aria-label", "ATR portfolio 到 program 与历史分支总览图', "portfolio_graph_count",
        "runForProgramNode", "openProgramNode", 'interaction: "PORTFOLIO_TO_NATIVE_TOPIC_TAB"',
        "materializePortfolioRegistry", '"同步当前研究组合（1 portfolio + 6 child）"',
        'lifecycle_effect: "NONE_PROJECTION_ONLY"',
        '"逐项历史消费映射"', "LEGACY_MAPPED×", "mappedArtifacts",
        '"Zotero 本地来源对账"', '"Zotero 来源对账 · 只读"',
        '"Repo PDF → Zotero 显式导入交接"', '"Repo PDF → Zotero · 待显式打开"',
        "openProgramReviewNode", 'interaction: "PORTFOLIO_TO_CHILD_COLLISION_REVIEW_NOTE"',
        "待我的 owner review · ${pending.length}", '"进入 child 并开始 owner review"',
    ):
        if dock_contract not in runtime:
            fail(f"Reader/Item Pane co-reading dock is missing {dock_contract!r}")
    for co_reading_contract in (
        "openNoteBesideReader", "coReadingNote", "openSourceForCoReading", 'context.mode = "item"',
        "openCurrentReadingNote", 'type: "openReadingNote"', 'l10nID: "atr-item-pane-open-reading-note"',
        "registerReadingNoteSection", 'bodyXHTML:', 'class="atr-reading-note-editor"',
        'class="atr-reading-visual-context"', "appendReadingVisualContext",
        '"与原文同时核对"', '"现实问题 → 研究问题"',
        '"NATIVE_NOTE_EDITOR_WITH_INLINE_FOLDABLE_RESEARCH_GRAPHS"',
        'interaction: "READER_WITH_FOLDABLE_NOTE_AND_ATR_SECTIONS"',
        '"阅读原文并记录我的理解"', '"在新标签深度编辑这份来源笔记"',
        '"便携显示 ATR 定位"', '"记录我的判断（进入待复审队列）"',
        '"worker 全文检查："', '"人的阅读：当前投影尚无 Note / annotation 复审记录"',
        '"知识核验状态："', '"<h2>知识核验状态</h2><p>"',
        '"<h2>原文核验跨度</h2><ul>"', "evidence_spans",
        '"知识状态：绿色=受限原文支撑；紫色=部分支撑；橙色=被碰撞复核挑战；灰色=等待更多来源。"',
        "BOUNDED_SOURCE_REVIEWED", "PARTIALLY_SOURCE_REVIEWED",
        "CHALLENGED_BY_COLLISION_REVIEW", "PENDING_ADDITIONAL_SOURCE_REVIEW",
        "ATR Collision Review:", "marker.collisionReview", "atr_collision_review_id",
        "ATR Reality Signal Gap:", "marker.realitySignalGap", "atr_reality_signal_gap_node_id",
        '"现实证据缺口"', '"为什么不能形成张力："', '"缺失的来源功能："',
        '"完成我的 owner route review"', "setOwnerRouteInput",
        '"ACCEPT_REFRAME"', '"REQUEST_MORE_EVIDENCE"', '"PARK_TOPIC"', '"RETIRE_CANDIDATE"',
        'lifecycle_effect: "REVIEW_INPUT_ONLY"',
    ):
        if co_reading_contract not in runtime:
            fail(f"Reader-centered native note interaction is missing {co_reading_contract!r}")
    for companion_contract in (
        "openCompanionWindow", "renderCompanionWindow", "openThreePaneCoReading",
        "companion.xhtml", "alwaysRaised=yes", "companion.keepTop",
        '"ZOTERO_READER", "ZOTERO_NATIVE_NOTE_EDITOR", "ATR_PORTABLE_CONTEXT"',
    ):
        if companion_contract not in runtime:
            fail(f"portable co-reading companion is missing {companion_contract!r}")
    for locale in ("en-US", "zh-CN"):
        locale_text = (PLUGIN / "locale" / locale / "atr-mainWindow.ftl").read_text(encoding="utf-8")
        if "atr-item-pane-open-reading-note" not in locale_text:
            fail(f"{locale} locale must label the native reading-note section action")
    if "human_note_modified" not in runtime or "human_annotation_modified" not in runtime:
        fail("plugin must relay both explicit notes and native Reader annotations")
    if 'input_origin: "ZOTERO_NOTIFIER"' not in runtime or "ignored non-cognitive Note metadata change" not in runtime:
        fail("plugin must identify Zotero feedback provenance and reject collection-only Note metadata changes")
    if "annotationID: annotation.key" not in runtime:
        fail("plugin must reopen a selected native annotation at its exact Reader location")
    if "zotero://open-pdf/" not in runtime or "getGroupIDFromLibraryID" not in runtime or "zotero_open_uri" not in runtime:
        fail("plugin must capture user/group-aware Codex-to-Reader annotation deep links at event time")
    if "ensureReadableAttachment" not in runtime or "Zotero.Attachments.importFromURL" not in runtime or "source_pdf_imported" not in runtime:
        fail("plugin must import an explicitly mapped open PDF on first read instead of leaving a metadata-only item")
    if ("Zotero.Attachments.importFromFile" not in runtime
            or "source_local_pdf_imported" not in runtime
            or "source_local_pdf_digest_mismatch" not in runtime
            or "ALLOW_ZOTERO_STORED_COPY_ON_EXPLICIT_READ" not in projection_source):
        fail("plugin must import only identity-verified, digest-stable repository PDFs into Zotero on explicit read")
    if ("Zotero.Attachments.addAvailableFile" not in runtime
            or "Zotero.Attachments.canFindFileForItem" not in runtime
            or "source_available_file_attached" not in runtime
            or "source_available_file_lookup_failed" not in runtime
            or 'fulltext_state: "FULLTEXT_ATTACHED"' not in runtime
            or "让 Zotero 查找全文并记录理解" not in runtime):
        fail("plugin must use Zotero's native available-file resolver and expose unresolved full-text state")
    if "review-queue.json" not in runtime or "pendingReviewItems" not in runtime:
        fail("plugin must display the Codex-derived pending review queue without mutating lifecycle")
    if ("ATR Topic Run:" not in runtime or "ATR Process Run:" not in runtime or "ATR Source ID:" not in runtime
            or "ATR Problem ID:" not in runtime or "ATR Graph Node:" not in runtime
            or "ATR Knowledge Node:" not in runtime or "ATR Tension Node:" not in runtime
            or "ATR Research Question Node:" not in runtime or "ATR Derived Question Node:" not in runtime):
        fail("plugin must scope human feedback with stable ATR markers")
    for marker in ("ATR Portfolio Node:", "ATR Research Program Node:", "ATR Legacy Run Node:", "ATR Alignment Audit Node:"):
        if marker not in runtime:
            fail(f"plugin must preserve portfolio migration marker {marker!r}")
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
    if "chrome/content/workbench" in bootstrap:
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
    update = json.loads((PLUGIN / "update.json").read_text(encoding="utf-8"))
    current = next(entry for entry in update["addons"][ADDON_ID]["updates"]
                   if entry["version"] == source["version"])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if current["update_hash"] != f"sha256:{digest}":
        fail("update.json hash differs from the built XPI")


def main() -> None:
    validate_source()
    if len(sys.argv) == 2:
        validate_xpi(Path(sys.argv[1]))
    print("Zotero plugin contract checks passed")


if __name__ == "__main__":
    main()
