"""Consume, never delete, human annotation events emitted by the Zotero companion."""
from __future__ import annotations
import json
import hashlib
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists(): return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def impact_report(output: Path) -> dict[str, Any]:
    graph = json.loads((output / "graph.json").read_text(encoding="utf-8"))
    events = _rows(output / "human-input" / "inbox.jsonl")
    latest = {}
    for event in events:
        if event.get("event") == "human_note_modified": latest[event.get("zotero_note_key")] = event
    by_source = {n["data"].get("source_id"): n["id"] for n in graph["nodes"] if n["kind"] == "paper"}
    by_claim = {n["data"].get("claim_id"): n["id"] for n in graph["nodes"] if n["kind"] == "claim"}
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph["edges"]:
        adjacency[edge["source"]].add(edge["target"]); adjacency[edge["target"]].add(edge["source"])
    nodes = {n["id"]: n for n in graph["nodes"]}
    affected = []
    for event in latest.values():
        source, claim = event.get("atr_source_id"), event.get("atr_claim_id")
        # A claim is the more precise target.  Source-level feedback remains
        # supported for old reading notes, but is never silently promoted to a
        # claim review.
        start = by_claim.get(claim) or by_source.get(source)
        target_type = "claim" if by_claim.get(claim) else ("source" if by_source.get(source) else "unmapped")
        questions, claims, paths = [], [], {}
        queue, seen = deque([start] if start else []), {start} if start else set()
        if start:
            paths[start] = [start]
        while queue:
            current = queue.popleft()
            if nodes[current]["kind"] == "research_question":
                questions.append(current)
            if nodes[current]["kind"] == "claim" and current != start:
                claims.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    paths[neighbor] = paths[current] + [neighbor]
                    queue.append(neighbor)
        question_paths = [
            {
                "question": nodes[node_id]["label"],
                "tension_id": nodes[node_id]["data"].get("tension_id"),
                "distance_from_annotated_source": len(paths[node_id]) - 1,
                "path": [{"id": item, "label": nodes[item]["label"], "kind": nodes[item]["kind"]} for item in paths[node_id]],
            }
            for node_id in questions
        ]
        question_paths.sort(key=lambda item: (item["distance_from_annotated_source"], item["question"]))
        nearest_distance = question_paths[0]["distance_from_annotated_source"] if question_paths else None
        nearest = [item for item in question_paths if item["distance_from_annotated_source"] == nearest_distance]
        claim_paths = [
            {
                "claim": nodes[node_id]["label"],
                "claim_id": nodes[node_id]["data"].get("claim_id"),
                "distance_from_review_target": len(paths[node_id]) - 1,
                "path": [{"id": item, "label": nodes[item]["label"], "kind": nodes[item]["kind"]} for item in paths[node_id]],
            }
            for node_id in claims
        ]
        claim_paths.sort(key=lambda item: (item["distance_from_review_target"], item["claim"]))
        affected.append({
            "event": event,
            "annotation_source_id": source,
            "annotation_claim_id": claim,
            "review_target_type": target_type,
            "source_found_in_projection": bool(start),
            "nearest_research_branches": nearest,
            "all_affected_research_questions": question_paths,
            "related_claims": claim_paths,
            "codex_next_action": "请人工审阅该反馈；若它挑战断言或来源边界，创建新的 immutable ATR human-review-packet，再由 owner 决定是否重做 route/claim review。保留既有节点和边作为历史投影，不自动清退文献或改写 ATR lifecycle。",
        })
    return {"schema_version":"0.1", "projection": "derived-human-input-review", "events_seen":len(events),
            "latest_notes":len(latest), "affected":affected}


def refresh_review_queue(output: Path) -> dict[str, Any]:
    """Append newly observed human-review impacts to a durable Codex queue.

    The queue is advisory: a human/Codex owner must explicitly decide whether
    a review changes an ATR claim or route. Existing entries and their statuses
    are retained, so later note edits never erase an earlier line of thought.
    """
    report = impact_report(output)
    path = output / "human-input" / "review-queue.json"
    existing = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
        "schema_version": "0.1", "projection": "codex-review-queue", "items": []
    }
    items = existing.setdefault("items", [])
    known = {item["id"] for item in items}
    added = 0
    for affected in report["affected"]:
        event = affected["event"]
        raw = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        item_id = hashlib.sha256(raw.encode()).hexdigest()[:16]
        if item_id in known:
            continue
        items.append({
            "id": item_id,
            "status": "pending_human_and_codex_review",
            "observed_at": event.get("at"),
            "annotation_source_id": affected["annotation_source_id"],
            "annotation_claim_id": affected["annotation_claim_id"],
            "review_target_type": affected["review_target_type"],
            "source_found_in_projection": affected["source_found_in_projection"],
            "nearest_research_branches": affected["nearest_research_branches"],
            "all_affected_research_questions": affected["all_affected_research_questions"],
            "related_claims": affected["related_claims"],
            "recommended_next_action": affected["codex_next_action"],
            "event": event,
        })
        known.add(item_id); added += 1
    existing["latest_refresh_events_seen"] = report["events_seen"]
    existing["new_items"] = added
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return existing
