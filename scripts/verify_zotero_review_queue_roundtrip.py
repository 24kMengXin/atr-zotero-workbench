#!/usr/bin/env python3
"""Verify the second-phase Zotero display of a Codex-derived review queue.

Run after `verify_zotero_smoke.py` has materialized the queue and the same
repository-local profile has been started once more.  This never reads a daily
Zotero profile.
"""
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
    loaded = [row for row in runtime if row.get("stage") == "review_queue_loaded"]
    if not loaded or loaded[-1].get("pending_count") != 2:
        raise SystemExit(f"plugin did not load the two pending review items: {loaded[-3:]}")
    if not any(row.get("stage") == "process_note_refreshed" for row in runtime):
        raise SystemExit("process Note was not refreshed after the review queue changed")

    connection = sqlite3.connect(f"file:{RUNTIME / 'data' / 'zotero.sqlite'}?mode=ro", uri=True)
    notes = [row[0] for row in connection.execute(
        "SELECT note FROM itemNotes WHERE note LIKE '%ATR Process Run:%'"
    ).fetchall()]
    if len(notes) != 1:
        raise SystemExit(f"expected one process Note, got {len(notes)}")
    for phrase in ("待审查的人类输入", "最近受影响节点", "不自动改变 lifecycle"):
        if phrase not in notes[0]:
            raise SystemExit(f"process Note does not display review queue boundary: {phrase}")
    print(json.dumps({
        "status": "PASS",
        "runtime": str(RUNTIME),
        "pending_review_count": loaded[-1]["pending_count"],
        "process_note_refreshed": True,
        "nearest_affected_nodes_visible": True,
        "lifecycle_boundary_visible": True,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
