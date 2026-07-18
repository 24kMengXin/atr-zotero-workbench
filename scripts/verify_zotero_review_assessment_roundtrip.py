#!/usr/bin/env python3
"""Verify Zotero rendered the isolated review assessment as a native Note."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime" / "zotero-smoke"
WORKSPACE = RUNTIME / "workspace"


def main() -> None:
    metadata = json.loads((RUNTIME / "review-roundtrip-metadata.json").read_text())
    graph = json.loads((WORKSPACE / "graph.json").read_text())
    native = json.loads((WORKSPACE / "zotero" / "native-projection.json").read_text())
    assessment_id = metadata["assessment"]["assessment_id"]
    assessment_node = next((node for node in graph["nodes"] if node["id"] == f"human_review_assessment:{assessment_id}"), None)
    if not assessment_node or assessment_node["data"].get("outcome") != "REQUEST_EVIDENCE":
        raise SystemExit("rebuilt graph lacks the isolated review assessment")
    obj = next((item for item in native["objects"] if item.get("object_kind") == "review_assessment_note" and item.get("atr_id") == assessment_id), None)
    if not obj or native["collections"].get("research_reviews") != "05 · 共创复核":
        raise SystemExit("native map lacks the co-creation review Note/Collection contract")
    source_run = Path(metadata["source_run"])
    if hashlib.sha256((source_run / "atr.sqlite").read_bytes()).hexdigest() != metadata["source_sqlite_sha256_before"]:
        raise SystemExit("real v2 authority changed during repository-local smoke")
    conn = sqlite3.connect(RUNTIME / "review-v2-run" / "atr.sqlite")
    subject = conn.execute("SELECT state,version FROM subjects WHERE subject_id=?", (metadata["subject"]["id"],)).fetchone()
    assessment_count = conn.execute("SELECT COUNT(*) FROM human_review_assessments WHERE assessment_id=?", (assessment_id,)).fetchone()[0]
    conn.close()
    if list(subject) != [metadata["subject"]["state_before"], metadata["subject"]["version_before"]] or assessment_count != 1:
        raise SystemExit("assessment changed lifecycle or was not recorded exactly once")
    zotero = sqlite3.connect(f"file:{RUNTIME / 'data' / 'zotero.sqlite'}?mode=ro", uri=True)
    notes = [row[0] for row in zotero.execute("SELECT note FROM itemNotes WHERE note LIKE ?", (f"%ATR Review Assessment: {assessment_id}%",))]
    process_notes = [row[0] for row in zotero.execute("SELECT note FROM itemNotes WHERE note LIKE '%ATR Process Run:%'")]
    collections = [row[0] for row in zotero.execute("SELECT collectionName FROM collections WHERE collectionName='05 · 共创复核'")]
    zotero.close()
    if len(notes) != 1 or not collections or not any("human-review-assessment" in note for note in process_notes):
        raise SystemExit("Zotero did not materialize the assessment as one native Note in the review Collection")
    for phrase in ("REQUEST_EVIDENCE", "preserve every linked source", "does not itself", "evidence-review"):
        if phrase not in notes[0]:
            raise SystemExit(f"review Note lacks required visible boundary: {phrase}")
    print(json.dumps({
        "pass": True,
        "assessment_id": assessment_id,
        "native_note_count": len(notes),
        "collection": "05 · 共创复核",
        "subject_state": subject[0],
        "subject_version": subject[1],
        "real_authority_unchanged": True,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
