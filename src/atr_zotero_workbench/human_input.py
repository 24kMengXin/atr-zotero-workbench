"""Consume, never delete, human annotation events emitted by the Zotero companion."""
from __future__ import annotations
import json
import hashlib
import datetime as dt
import subprocess
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
        questions, claims, research_problems, decision_objects, paths = [], [], [], [], {}
        queue, seen = deque([start] if start else []), {start} if start else set()
        if start:
            paths[start] = [start]
        while queue:
            current = queue.popleft()
            if nodes[current]["kind"] == "research_question":
                questions.append(current)
            if nodes[current]["kind"] == "claim" and current != start:
                claims.append(current)
            if nodes[current]["kind"] == "research_problem":
                research_problems.append(current)
            if nodes[current]["kind"] in {"claim", "research_question", "real_world_tension", "research_problem"}:
                decision_objects.append(current)
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
        problem_paths = [
            {
                "problem": nodes[node_id]["label"],
                "problem_id": nodes[node_id]["data"].get("problem_id"),
                "status": nodes[node_id]["data"].get("status", "UNSPECIFIED"),
                "distance_from_review_target": len(paths[node_id]) - 1,
                "path": [{"id": item, "label": nodes[item]["label"], "kind": nodes[item]["kind"]} for item in paths[node_id]],
            }
            for node_id in dict.fromkeys(research_problems)
        ]
        problem_paths.sort(key=lambda item: (item["distance_from_review_target"], item["problem"]))
        nearest_problem_distance = problem_paths[0]["distance_from_review_target"] if problem_paths else None
        nearest_problems = [item for item in problem_paths if item["distance_from_review_target"] == nearest_problem_distance]
        decision_paths = [
            {
                "kind": nodes[node_id]["kind"],
                "id": node_id,
                "label": nodes[node_id]["label"],
                "distance_from_review_target": len(paths[node_id]) - 1,
                "path": [{"id": item, "label": nodes[item]["label"], "kind": nodes[item]["kind"]} for item in paths[node_id]],
            }
            for node_id in dict.fromkeys(decision_objects)
        ]
        decision_paths.sort(key=lambda item: (item["distance_from_review_target"], item["kind"], item["label"]))
        nearest_decision_distance = decision_paths[0]["distance_from_review_target"] if decision_paths else None
        nearest_decision_objects = [item for item in decision_paths if item["distance_from_review_target"] == nearest_decision_distance]
        affected.append({
            "event": event,
            "annotation_source_id": source,
            "annotation_claim_id": claim,
            "review_target_type": target_type,
            "source_found_in_projection": bool(start),
            "nearest_research_branches": nearest,
            "all_affected_research_questions": question_paths,
            "related_claims": claim_paths,
            "nearest_research_problems": nearest_problems,
            "all_affected_research_problems": problem_paths,
            "nearest_decision_objects": nearest_decision_objects,
            "all_affected_decision_objects": decision_paths,
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
            "nearest_research_problems": affected["nearest_research_problems"],
            "all_affected_research_problems": affected["all_affected_research_problems"],
            "nearest_decision_objects": affected["nearest_decision_objects"],
            "all_affected_decision_objects": affected["all_affected_decision_objects"],
            "recommended_next_action": affected["codex_next_action"],
            "event": event,
        })
        known.add(item_id); added += 1
    existing["latest_refresh_events_seen"] = report["events_seen"]
    existing["new_items"] = added
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    return existing


def materialize_review_packets(output: Path) -> dict[str, Any]:
    """Materialize immutable ATR inputs from explicit Zotero review events.

    This is intentionally a one-way preparation step, not a controller call.
    A packet says what a researcher reviewed and what branch it may affect; an
    ATR owner/controller must still record a separate disposition before any
    claim, gate, or route can change.
    """
    report = impact_report(output)
    directory = output / "human-input" / "review-packets"
    directory.mkdir(parents=True, exist_ok=True)
    written, existing = [], 0
    for affected in report["affected"]:
        event = affected["event"]
        raw = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        packet_id = "HRP-" + hashlib.sha256(raw.encode()).hexdigest()[:16]
        path = directory / f"{packet_id}.json"
        if path.exists():
            existing += 1
            continue
        packet = {
            "schema_version": "0.2",
            "artifact_type": "human-review-packet",
            "packet_id": packet_id,
            "status": "PENDING_ATR_OWNER_REVIEW",
            "created_from": {
                "zotero_note_key": event.get("zotero_note_key"),
                "observed_at": event.get("at"),
                "notifier": event.get("notifier"),
            },
            "review": {
                "target_type": affected["review_target_type"],
                "claim_id": affected["annotation_claim_id"],
                "source_id": affected["annotation_source_id"],
                "source_locator": event.get("source_locator"),
                "stance": event.get("review_stance", "UNSPECIFIED"),
                "note_html": event.get("note_html", ""),
            },
            "impact": {
                "nearest_research_branches": affected["nearest_research_branches"],
                "all_affected_research_questions": affected["all_affected_research_questions"],
                "related_claims": affected["related_claims"],
                "nearest_research_problems": affected["nearest_research_problems"],
                "all_affected_research_problems": affected["all_affected_research_problems"],
                "nearest_decision_objects": affected["nearest_decision_objects"],
                "all_affected_decision_objects": affected["all_affected_decision_objects"],
            },
            "required_owner_decision": {
                "allowed_dispositions": ["ACCEPT_AS_REVIEW_INPUT", "REQUEST_CLARIFICATION", "OPEN_CLAIM_REVIEW", "OPEN_ROUTE_REVIEW", "NO_LIFECYCLE_CHANGE"],
                "invariant": "This packet cannot itself modify a claim, ATR lifecycle, gate, source record, or historical projection.",
            },
        }
        path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(str(path))
    return {"schema_version": "0.2", "artifact_type": "human-review-packet-batch", "written": written, "existing": existing}


OWNER_DISPOSITIONS = {
    "ACCEPT_AS_REVIEW_INPUT", "REQUEST_CLARIFICATION", "OPEN_CLAIM_REVIEW",
    "OPEN_ROUTE_REVIEW", "NO_LIFECYCLE_CHANGE",
}


def attach_review_packet_to_v2(output: Path, v2_run_dir: Path, packet_id: str,
                               subject_id: str, expected_version: int,
                               atrctl: Path, disposition_ledger: Path) -> dict[str, Any]:
    """Explicitly attach an owner-approved Zotero packet to an ATR v2 run.

    This is deliberately an evidence attachment, not a transition: v2 keeps
    the same subject version and stage.  The owner must subsequently inspect
    the returned impact map and make any route/claim decision through v2's
    separate transactional transition API.
    """
    packet_path = output / "human-input" / "review-packets" / f"{packet_id}.json"
    if not packet_path.is_file():
        raise ValueError(f"review packet not found: {packet_id}")
    packet_bytes = packet_path.read_bytes()
    packet = json.loads(packet_bytes)
    if packet.get("artifact_type") != "human-review-packet":
        raise ValueError("packet has wrong artifact_type")
    if not disposition_ledger.is_file():
        raise ValueError("owner disposition ledger is not available to the v2 bridge")
    records = _rows(disposition_ledger)
    decision = next((row for row in records if row.get("packet_id") == packet_id), None)
    if not decision:
        raise ValueError(f"owner disposition not found for packet: {packet_id}")
    if decision.get("packet_sha256") != hashlib.sha256(packet_bytes).hexdigest():
        raise ValueError("packet hash does not match the owner disposition")
    if decision.get("disposition") not in {"ACCEPT_AS_REVIEW_INPUT", "OPEN_CLAIM_REVIEW", "OPEN_ROUTE_REVIEW"}:
        raise ValueError("owner disposition does not authorize review input attachment")
    if not atrctl.is_file():
        raise ValueError(f"ATR v2 controller not found: {atrctl}")

    def invoke(*args: str) -> str:
        result = subprocess.run(["python3", str(atrctl), *args], text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "atrctl failed")
        return result.stdout.strip()

    artifact_id = invoke("ingest", str(v2_run_dir), str(packet_path), "--kind", "human-review-packet", "--scope", "owner-approved Zotero reading feedback")
    attachment_id = "HRA-" + hashlib.sha256((packet_id + "\0" + decision["decision_id"]).encode()).hexdigest()[:16]
    invoke("attach", str(v2_run_dir), "--subject", subject_id,
           "--expected-version", str(expected_version), "--artifact", artifact_id,
           "--role", "human-review-input", "--attachment-id", attachment_id,
           "--note", f"Owner disposition {decision['decision_id']}: {decision['disposition']}")
    impact = packet.get("impact", {})
    return {
        "artifact_id": artifact_id,
        "attachment_id": attachment_id,
        "subject_id": subject_id,
        "expected_version": expected_version,
        "lifecycle_changed": False,
        "owner_disposition": {"decision_id": decision["decision_id"], "disposition": decision["disposition"]},
        "nearest_decision_objects": impact.get("nearest_decision_objects", []),
        "nearest_research_problems": impact.get("nearest_research_problems", []),
        "required_next_step": "Inspect this attached review input, then use atrctl transition only if a separately authored review artifact warrants a lifecycle decision.",
    }


def record_review_disposition(output: Path, run_dir: Path, packet_id: str, disposition: str,
                              rationale: str, owner: str) -> dict[str, Any]:
    """Append an owner decision for one immutable Zotero review packet.

    This is the deliberately narrow bridge back into ATR.  It records what
    should be reconsidered, but never edits claims, gates, routes, sources, or
    old projections.  The controller must make any later lifecycle transition
    through its own append-only route/gate ledgers.
    """
    if disposition not in OWNER_DISPOSITIONS:
        raise ValueError(f"unsupported disposition: {disposition}")
    if not rationale.strip() or not owner.strip():
        raise ValueError("--rationale and --owner must be non-empty")
    packet_path = output / "human-input" / "review-packets" / f"{packet_id}.json"
    if not packet_path.exists():
        raise ValueError(f"review packet not found: {packet_id}")
    packet_bytes = packet_path.read_bytes()
    packet = json.loads(packet_bytes)
    allowed = packet.get("required_owner_decision", {}).get("allowed_dispositions", [])
    if disposition not in allowed:
        raise ValueError(f"packet does not permit disposition: {disposition}")
    ledger = run_dir / "decisions" / "human-review-dispositions.jsonl"
    existing = _rows(ledger)
    if any(row.get("packet_id") == packet_id for row in existing):
        raise ValueError(f"packet already has an immutable owner disposition: {packet_id}")
    impact = packet.get("impact", {})
    review = packet.get("review", {})
    decision_id = "HRD-" + hashlib.sha256((packet_id + "\0" + disposition + "\0" + rationale).encode()).hexdigest()[:16]
    record = {
        "schema_version": "0.1", "artifact_type": "human-review-disposition",
        "decision_id": decision_id, "packet_id": packet_id,
        "packet_sha256": hashlib.sha256(packet_bytes).hexdigest(),
        "recorded_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "owner": owner, "disposition": disposition, "rationale": rationale,
        "review_target": {"target_type": review.get("target_type"), "claim_id": review.get("claim_id"), "source_id": review.get("source_id"), "source_locator": review.get("source_locator")},
        "affected_node_ids": {
            "research_questions": [item.get("tension_id") for item in impact.get("all_affected_research_questions", []) if item.get("tension_id")],
            "claims": [item.get("claim_id") for item in impact.get("related_claims", []) if item.get("claim_id")],
            "research_problems": [item.get("problem_id") for item in impact.get("all_affected_research_problems", []) if item.get("problem_id")],
        },
        "controller_boundary": "This disposition is an ATR review input only. It does not itself modify a claim, route, gate, source record, lifecycle state, or historical projection.",
    }
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    queue_path = output / "human-input" / "review-queue.json"
    if queue_path.exists():
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        event_id = packet_id.removeprefix("HRP-")
        for item in queue.get("items", []):
            if item.get("id") == event_id:
                item["status"] = "owner_disposition_recorded"
                item.setdefault("disposition_history", []).append({"decision_id": decision_id, "disposition": disposition, "recorded_at": record["recorded_at"]})
        queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    return record
