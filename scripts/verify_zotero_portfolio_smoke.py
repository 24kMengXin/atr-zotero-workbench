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
    connection = sqlite3.connect(f"file:{RUNTIME / 'data' / 'zotero.sqlite'}?mode=ro", uri=True)
    note_count = connection.execute(
        "SELECT COUNT(*) FROM itemNotes WHERE note LIKE '%ATR Research Program Node:%'"
    ).fetchone()[0]
    if note_count != 6:
        raise SystemExit(f"expected six native program navigation Notes, found {note_count}")
    print(json.dumps({
        "portfolio_programs": 6,
        "resolved_child_run_id": target["child_run_id"],
        "opened_child_topic_note": child_open["topic_note_key"],
        "opened_child_collision_review_note": dev_owner_review_open["collision_review_note_key"],
        "foldable_panels": probe["panel_count"],
        "portfolio_graphs": probe["portfolio_graph_count"],
        "authority_effect": "NONE_NAVIGATION_ONLY",
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
