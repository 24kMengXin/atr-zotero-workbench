#!/usr/bin/env python3
"""Verify portfolio navigation in the stopped repository-local Zotero profile."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime" / "zotero-smoke"
WORKSPACE = RUNTIME / "workspace"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    runtime = rows(WORKSPACE / "plugin-runtime.jsonl")
    stages = {row.get("stage") for row in runtime}
    required = {
        "startup_complete", "native_topic_menu_added", "native_item_pane_registered",
        "projection_loaded", "native_topic_synced", "native_note_tab_opened",
        "co_reading_dock_rendered", "co_reading_dock_probe_passed",
        "dev_smoke_portfolio_program_target_resolved",
        "dev_smoke_portfolio_returned",
        "portfolio_registry_materialized",
    }
    missing = sorted(required - stages)
    if missing:
        raise SystemExit(f"missing portfolio runtime stages: {missing}")
    target = next(row for row in runtime if row.get("stage") == "dev_smoke_portfolio_program_target_resolved")
    if target.get("view_role") != "REGISTERED_V2_RUN" or not target.get("child_run_id"):
        raise SystemExit(f"portfolio node did not resolve a registered child authority: {target}")
    child_runtime_path = RUNTIME / "child-workspaces" / "multilingual-agent-action-attribution-v2-intake" / "plugin-runtime.jsonl"
    child_runtime = rows(child_runtime_path)
    child_open = next((row for row in child_runtime if row.get("stage") == "dev_smoke_portfolio_program_opened"), None)
    actual_open = next((row for row in child_runtime if row.get("stage") == "portfolio_program_opened"), None)
    owner_review_open = next((row for row in child_runtime if row.get("stage") == "portfolio_program_owner_review_opened"), None)
    dev_owner_review_open = next((row for row in child_runtime if row.get("stage") == "dev_smoke_portfolio_owner_review_opened"), None)
    if (not child_open or not actual_open
            or child_open.get("child_run_id") != target.get("child_run_id")
            or actual_open.get("interaction") != "PORTFOLIO_TO_NATIVE_TOPIC_TAB"):
        raise SystemExit(f"portfolio click path did not open the child topic and native Note: {child_open}, {actual_open}")
    if (not owner_review_open or not dev_owner_review_open
            or owner_review_open.get("interaction") != "PORTFOLIO_TO_CHILD_COLLISION_REVIEW_NOTE"
            or owner_review_open.get("collision_review_node_id") != "collision_review:ARH-MULTILINGUAL-ACTION-ATTRIBUTION-R0-COL-001.v1"
            or not dev_owner_review_open.get("collision_review_note_key")):
        raise SystemExit(f"portfolio did not enter the exact child owner-review Note: {owner_review_open}, {dev_owner_review_open}")
    probe = next(row for row in runtime if row.get("stage") == "co_reading_dock_probe_passed")
    if probe.get("panel_count") != 4 or probe.get("portfolio_graph_count") != 1:
        raise SystemExit(f"portfolio did not render four foldable panels and one global graph: {probe}")
    registry = json.loads((RUNTIME / "registry.json").read_text(encoding="utf-8"))
    registered = {row.get("run_id") for row in registry.get("runs", [])}
    graph = json.loads((WORKSPACE / "graph.json").read_text(encoding="utf-8"))
    child_ids = {
        node.get("data", {}).get("child_run_id")
        for node in graph.get("nodes", []) if node.get("kind") == "research_program"
    } - {None}
    if len(child_ids) != 6 or not child_ids.issubset(registered):
        raise SystemExit(f"portfolio registry does not preserve all six child targets: {child_ids - registered}")
    materialized = next(row for row in runtime if row.get("stage") == "portfolio_registry_materialized")
    if (materialized.get("topic_count") != 7 or materialized.get("child_count") != 6
            or materialized.get("history_branch_count") != 28
            or materialized.get("mapped_artifact_count") != 164
            or materialized.get("lifecycle_effect") != "NONE_PROJECTION_ONLY"):
        raise SystemExit(f"portfolio bulk materialization did not preserve the 1→6→28→164 contract: {materialized}")
    for row in registry.get("runs", []):
        if row.get("view_role") != "REGISTERED_V2_RUN":
            continue
        child_log = Path(row["workspace"]) / "plugin-runtime.jsonl"
        child_events = rows(child_log)
        if not any(event.get("stage") == "portfolio_child_materialized"
                   and event.get("run_id") == row.get("run_id") for event in child_events):
            raise SystemExit(f"child was not bulk-materialized into Zotero: {row.get('run_id')}")
    expected_source_ids = set()
    for row in registry.get("runs", []):
        if row.get("view_role") != "REGISTERED_V2_RUN":
            continue
        child_graph = json.loads((Path(row["workspace"]) / "graph.json").read_text(encoding="utf-8"))
        expected_source_ids.update(
            str(node.get("data", {}).get("source_id"))
            for node in child_graph.get("nodes", [])
            if node.get("kind") == "paper" and node.get("data", {}).get("source_id")
        )
    connection = sqlite3.connect(f"file:{RUNTIME / 'data' / 'zotero.sqlite'}?mode=ro", uri=True)
    note_count = connection.execute(
        "SELECT COUNT(*) FROM itemNotes WHERE note LIKE '%ATR Research Program Node:%'"
    ).fetchone()[0]
    if note_count != 6:
        raise SystemExit(f"expected six native program navigation Notes, found {note_count}")
    topic_note_count = connection.execute(
        "SELECT COUNT(*) FROM itemNotes WHERE note LIKE '%ATR Topic Run:%'"
    ).fetchone()[0]
    legacy_note_count = connection.execute(
        "SELECT COUNT(*) FROM itemNotes WHERE note LIKE '%ATR Legacy Run Node:%'"
    ).fetchone()[0]
    root_collection_count = connection.execute(
        "SELECT COUNT(*) FROM collections WHERE parentCollectionID IS NULL AND collectionName LIKE 'ATR · %'"
    ).fetchone()[0]
    if (topic_note_count != 7 or legacy_note_count != 28 or root_collection_count != 7):
        raise SystemExit(
            "bulk materialization did not create exactly seven native topic roots and 28 historical Notes: "
            f"topics={topic_note_count}, history={legacy_note_count}, roots={root_collection_count}"
        )
    materialized_source_ids = {
        name.removeprefix("atr-source-id:")
        for (name,) in connection.execute("SELECT name FROM tags WHERE name LIKE 'atr-source-id:%'")
    }
    if materialized_source_ids != expected_source_ids:
        raise SystemExit(
            "bulk materialization did not close over the exact six-child source set: "
            f"missing={sorted(expected_source_ids - materialized_source_ids)}, "
            f"extra={sorted(materialized_source_ids - expected_source_ids)}"
        )
    print(json.dumps({
        "portfolio_programs": 6,
        "resolved_child_run_id": target["child_run_id"],
        "opened_child_topic_note": child_open["topic_note_key"],
        "opened_child_collision_review_note": dev_owner_review_open["collision_review_note_key"],
        "foldable_panels": probe["panel_count"],
        "portfolio_graphs": probe["portfolio_graph_count"],
        "materialized_topic_roots": root_collection_count,
        "materialized_child_authorities": materialized["child_count"],
        "materialized_history_branches": legacy_note_count,
        "mapped_legacy_artifacts": materialized["mapped_artifact_count"],
        "materialized_canonical_sources": len(materialized_source_ids),
        "authority_effect": "NONE_NAVIGATION_ONLY",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
