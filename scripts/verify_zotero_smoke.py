#!/usr/bin/env python3
"""Verify the stopped repository-local Zotero smoke instance."""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime" / "zotero-smoke"
WORKSPACE = RUNTIME / "workspace"
sys.path.insert(0, str(ROOT / "src"))
from atr_zotero_workbench.human_input import impact_report, materialize_review_packets, refresh_review_queue  # noqa: E402


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    runtime = rows(WORKSPACE / "plugin-runtime.jsonl")
    stages = {row.get("stage") for row in runtime}
    required = {
        "startup_complete", "native_topic_menu_added", "native_item_pane_registered",
        "projection_loaded", "native_topic_synced", "native_note_tab_opened",
        "native_reader_tab_opened", "dev_smoke_feedback_saved",
        "dev_smoke_reader_annotation_saved",
        "process_note_created", "human_review_stance_selected",
        "native_reader_annotation_opened",
    }
    missing = sorted(required - stages)
    if missing:
        raise SystemExit(f"missing runtime stages: {missing}")

    events = rows(WORKSPACE / "human-input" / "inbox.jsonl")
    if any(event.get("atr_run") and not event.get("atr_problem_id") for event in events):
        raise SystemExit("programmatic Topic Note creation leaked into the human-input inbox")
    problem_events = [event for event in events if event.get("atr_problem_id") and event.get("atr_graph_node_id")]
    if len(problem_events) != 1:
        raise SystemExit(f"expected one exact problem Note feedback event, got {len(problem_events)}")
    if problem_events[0].get("review_stance") != "QUALIFIES":
        raise SystemExit(f"Item Pane stance selection was not captured as typed review input: {problem_events[0]}")
    annotation_events = [event for event in events if event.get("event") == "human_annotation_modified"]
    if len(annotation_events) != 1 or not annotation_events[0].get("atr_source_id"):
        raise SystemExit(f"expected one mapped Reader annotation event, got {len(annotation_events)}")
    deep_link = annotation_events[0].get("zotero_open_uri")
    attachment_key = annotation_events[0].get("zotero_attachment_key")
    annotation_key = annotation_events[0].get("zotero_annotation_key")
    if not deep_link or f"/items/{attachment_key}?" not in deep_link or f"annotation={annotation_key}" not in deep_link:
        raise SystemExit("Reader annotation did not preserve an exact Codex-to-Zotero deep link")
    annotation_open = next((row for row in runtime if row.get("stage") == "native_reader_annotation_opened"), None)
    if not annotation_open or annotation_open.get("annotation_key") != annotation_events[0].get("zotero_annotation_key"):
        raise SystemExit("Reader did not reopen the exact captured annotation via annotationID")
    impact = impact_report(WORKSPACE)
    annotation_impact = next(
        row for row in impact["affected"]
        if row["event"].get("event") == "human_annotation_modified"
    )
    nearest = annotation_impact["nearest_research_problems"]
    if not nearest or nearest[0]["distance_from_review_target"] != 1:
        raise SystemExit(f"Reader annotation did not map to the nearest explicit research problem: {nearest}")
    materialize_review_packets(WORKSPACE)
    review_queue = refresh_review_queue(WORKSPACE)
    packets = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(
        (WORKSPACE / "human-input" / "review-packets").glob("HRP-*.json")
    )]
    if len(packets) != 2 or any(packet.get("status") != "PENDING_ATR_OWNER_REVIEW" for packet in packets):
        raise SystemExit("Note and Reader feedback must materialize as two pending, review-only packets")
    if len(review_queue.get("items", [])) != 2:
        raise SystemExit("Note and Reader feedback must appear in the durable Codex review queue")
    links = (WORKSPACE / "human-input" / "review-links.md").read_text(encoding="utf-8")
    if deep_link not in links:
        raise SystemExit("review-links.md does not expose the exact Reader annotation deep link")

    connection = sqlite3.connect(f"file:{RUNTIME / 'data' / 'zotero.sqlite'}?mode=ro", uri=True)
    collections = connection.execute("SELECT collectionName, parentCollectionID FROM collections ORDER BY collectionID").fetchall()
    native_map = json.loads((WORKSPACE / "zotero" / "native-projection.json").read_text(encoding="utf-8"))
    knowledge_objects = [obj for obj in native_map["objects"] if obj.get("object_kind") == "knowledge_note"]
    knowledge_count = len(knowledge_objects)
    research_kinds = {
        "tension_note", "frontier_question_note", "problem_note",
        "derived_question_note", "claim_note", "review_assessment_note",
    }
    research_objects = [obj for obj in native_map["objects"] if obj.get("object_kind") in research_kinds]
    expected_collection_count = 1 + 5 + 5 + knowledge_count + len(research_objects)
    required_collection_names = set(native_map["collections"].values())
    observed_collection_names = {name for name, _ in collections}
    source_item_by_id = {
        tag.removeprefix("atr-source-id:"): item_id
        for tag, item_id in connection.execute(
            "SELECT tags.name, itemTags.itemID FROM tags JOIN itemTags USING(tagID) "
            "WHERE tags.name LIKE 'atr-source-id:%'"
        ).fetchall()
    }
    if (len(collections) != expected_collection_count or collections[0][1] is not None
            or not required_collection_names.issubset(observed_collection_names)):
        raise SystemExit(f"unexpected native collection projection: {collections}")
    collection_tree = dict(connection.execute(
        "SELECT child.collectionName, parent.collectionName "
        "FROM collections child LEFT JOIN collections parent ON child.parentCollectionID=parent.collectionID"
    ).fetchall())
    def knowledge_collection_name(obj: dict) -> str:
        identity = str(obj.get("graph_node_id") or obj["atr_id"]).split(":")[-1]
        return f"知识 · {identity} · {obj['title']}"[:180].strip()
    by_graph_id = {obj["graph_node_id"]: obj for obj in knowledge_objects}
    for obj in knowledge_objects:
        name = knowledge_collection_name(obj)
        parent_obj = by_graph_id.get(obj.get("parent_graph_node_id"))
        expected_parent = knowledge_collection_name(parent_obj) if parent_obj else (
            native_map["collections"]["history"]
            if obj.get("review_role") == "HISTORICAL_VERSION"
            else native_map["collections"]["knowledge"]
        )
        if collection_tree.get(name) != expected_parent:
            raise SystemExit(f"knowledge hierarchy mismatch for {name}: {collection_tree.get(name)} != {expected_parent}")
        item_count = connection.execute(
            "SELECT COUNT(*) FROM collectionItems JOIN collections USING(collectionID) WHERE collectionName=?",
            (name,),
        ).fetchone()[0]
        expected_item_count = 1 + len({source_item_by_id[source_id] for source_id in obj.get("linked_source_ids", [])})
        if item_count != expected_item_count:
            raise SystemExit(f"knowledge collection does not contain its Note plus linked sources: {name}")
    def research_collection_name(obj: dict) -> str:
        prefix = {
            "tension_note": "张力",
            "frontier_question_note": "前沿问题",
            "problem_note": "问题卡",
            "derived_question_note": "细粒度问题",
            "claim_note": "断言",
        }[obj["object_kind"]]
        identity = str(obj.get("graph_node_id") or obj["atr_id"]).split(":")[-1]
        return f"{prefix} · {identity} · {obj['title']}"[:180].strip()
    research_by_graph_id = {obj["graph_node_id"]: obj for obj in research_objects}
    for obj in research_objects:
        name = research_collection_name(obj)
        if obj["object_kind"] == "derived_question_note" and obj.get("parent_graph_node_id") in research_by_graph_id:
            expected_parent = research_collection_name(research_by_graph_id[obj["parent_graph_node_id"]])
        elif obj.get("review_role") == "HISTORICAL_VERSION":
            expected_parent = native_map["collections"]["history"]
        elif obj["object_kind"] == "tension_note":
            expected_parent = native_map["collections"]["research_tensions"]
        elif obj["object_kind"] == "frontier_question_note":
            expected_parent = native_map["collections"]["research_frontier"]
        elif obj["object_kind"] == "claim_note":
            expected_parent = native_map["collections"]["research_claims"]
        else:
            expected_parent = native_map["collections"]["research_current"]
        if collection_tree.get(name) != expected_parent:
            raise SystemExit(f"research hierarchy mismatch for {name}: {collection_tree.get(name)} != {expected_parent}")
        item_count = connection.execute(
            "SELECT COUNT(*) FROM collectionItems JOIN collections USING(collectionID) WHERE collectionName=?",
            (name,),
        ).fetchone()[0]
        expected_item_count = 1 + len({source_item_by_id[source_id] for source_id in obj.get("linked_source_ids", [])})
        if item_count != expected_item_count:
            raise SystemExit(f"research collection does not contain its Note plus linked sources: {name}")
    item_counts = dict(connection.execute(
        "SELECT itemTypes.typeName, COUNT(*) FROM items JOIN itemTypes USING(itemTypeID) GROUP BY itemTypes.typeName"
    ).fetchall())
    expected_notes = 1 + sum(obj.get("object_kind", "").endswith("_note") for obj in native_map["objects"])
    process_notes = [row[0] for row in connection.execute(
        "SELECT note FROM itemNotes WHERE note LIKE '%ATR Process Run:%'"
    ).fetchall()]
    if (len(process_notes) != 1 or "实际事件与产物" not in process_notes[0]
            or "不会用推测补齐缺失历史" not in process_notes[0]):
        raise SystemExit("missing generated native process Note with explicit non-invention boundary")
    problem_notes = [row[0] for row in connection.execute(
        "SELECT note FROM itemNotes WHERE note LIKE '%ATR Problem ID:%'"
    ).fetchall()]
    if not problem_notes or not any("问题姿态" in note and "仍未解决" in note for note in problem_notes):
        raise SystemExit("problem Note does not expose each paper's problem posture and unresolved role")
    for note in problem_notes:
        role_source_ids = re.findall(r" · ([^<]+)<br>问题姿态", note)
        if len(role_source_ids) != len(set(role_source_ids)):
            raise SystemExit(f"problem Note repeats one paper role more than once: {role_source_ids}")
    expected_source_ids = {
        obj["atr_id"] for obj in native_map["objects"] if obj.get("object_kind") == "source_item"
    }
    observed_source_ids = {
        name.removeprefix("atr-source-id:")
        for name, in connection.execute(
            "SELECT DISTINCT tags.name FROM tags JOIN itemTags USING(tagID) "
            "WHERE tags.name LIKE 'atr-source-id:%'"
        ).fetchall()
    }
    regular_item_count = sum(item_counts.get(kind, 0) for kind in ("journalArticle", "webpage"))
    if (item_counts.get("note") != expected_notes
            or observed_source_ids != expected_source_ids
            or not (0 < regular_item_count <= len(expected_source_ids))
            or item_counts.get("attachment") != 1 or item_counts.get("annotation") != 1):
        raise SystemExit(
            f"unexpected native item projection: counts={item_counts}, "
            f"missing_source_tags={sorted(expected_source_ids - observed_source_ids)}, "
            f"extra_source_tags={sorted(observed_source_ids - expected_source_ids)}"
        )
    print(json.dumps({
        "status": "PASS",
        "runtime": str(RUNTIME),
        "stages": sorted(required),
        "problem_feedback_graph_node": problem_events[0]["atr_graph_node_id"],
        "problem_feedback_stance": problem_events[0]["review_stance"],
        "reader_feedback_source_id": annotation_events[0]["atr_source_id"],
        "reader_exact_annotation_reopened": True,
        "reader_nearest_problem_id": nearest[0]["problem_id"],
        "reader_nearest_problem_distance": nearest[0]["distance_from_review_target"],
        "review_packet_count": len(packets),
        "review_queue_count": len(review_queue["items"]),
        "reader_deep_link": deep_link,
        "knowledge_collection_count": knowledge_count,
        "knowledge_hierarchy_verified": True,
        "research_collection_count": len(research_objects),
        "research_hierarchy_verified": True,
        "process_note_verified": True,
        "paper_problem_roles_visible": True,
        "source_id_count": len(expected_source_ids),
        "deduplicated_regular_item_count": regular_item_count,
        "collections": [name for name, _ in collections],
        "item_counts": item_counts,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
