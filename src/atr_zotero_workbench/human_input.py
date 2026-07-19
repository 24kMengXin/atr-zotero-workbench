"""Consume, never delete, human annotation events emitted by the Zotero companion."""
from __future__ import annotations
import json
import hashlib
import datetime as dt
import subprocess
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

REVIEW_PROPAGATION_RELATIONS = {
    # Explicit source-to-decision evidence links
    "anchored_by", "illustrated_by_question_anchor", "cites_explicit_source",
    "inspired_by_context", "grounded_in_explicit_source",
    "has_explicit_problem_role", "grounds_in_explicit_source_span",
    "grounds_in_explicit_evidence_layer", "grounded_in_explicit_signal",
    "defines_with_explicit_source", "specializes_concept",
    # Explicit collision-review bridge: a paper inspected by a claim-scoped
    # review can reach only the problem that names that review.  The generic
    # artifact/run containment edges remain excluded.
    "inspects_for_collision", "is_claim_scoped_reviewed_by",
    "searched_for_admissible_reality_signal_in",
    # Explicit decision lineage; deliberately excludes run/program/gate containment
    "raises_question", "supersedes", "generates_finer_review_question",
    "refines_question", "derived_from_problem",
}

DECISION_OBJECT_PRIORITY = {
    "claim": 0,
    "collision_review": 1,
    "research_problem": 2,
    "research_question": 3,
    "derived_research_question": 3,
    "real_world_tension": 4,
    "reality_signal_gap": 5,
    "knowledge_concept": 6,
    "atr_v2_subject": 7,
    "research_program": 8,
    "research_portfolio": 9,
    "historical_alignment_audit": 10,
    "legacy_research_run": 11,
}

def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists(): return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def _event_item_id(event: dict[str, Any]) -> str:
    raw = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def _ignored_event_reason(event: dict[str, Any]) -> str | None:
    if event.get("input_origin") == "PLUGIN_GENERATED":
        return "PLUGIN_GENERATED"
    if event.get("event") == "human_note_modified":
        changed = event.get("notifier", {}).get("changed")
        if isinstance(changed, dict) and changed and set(changed) <= {"collections"}:
            return "COLLECTION_METADATA_ONLY"
    return None

def impact_report(output: Path) -> dict[str, Any]:
    graph = json.loads((output / "graph.json").read_text(encoding="utf-8"))
    events = _rows(output / "human-input" / "inbox.jsonl")
    latest = {}
    ignored = []
    for event in events:
        if event.get("event") not in {"human_note_modified", "human_annotation_modified"}:
            continue
        ignored_reason = _ignored_event_reason(event)
        if ignored_reason:
            ignored.append({"id": _event_item_id(event), "reason": ignored_reason, "event": event})
            continue
        key = event.get("zotero_note_key") or event.get("zotero_annotation_key")
        if key:
            latest[(event.get("event"), key)] = event
    by_source = {n["data"].get("source_id"): n["id"] for n in graph["nodes"] if n["kind"] == "paper"}
    historical_nodes = set()
    for edge in graph["edges"]:
        if edge.get("relation") == "superseded_by_recorded_problem_version":
            historical_nodes.add(edge.get("source"))
        elif edge.get("relation") == "supersedes":
            historical_nodes.add(edge.get("target"))

    def current_index(kind: str, field: str) -> dict[str, str]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for node in graph["nodes"]:
            value = node.get("data", {}).get(field)
            if node.get("kind") == kind and value:
                grouped[value].append(node["id"])
        return {
            value: sorted(ids, key=lambda node_id: (node_id in historical_nodes, node_id))[0]
            for value, ids in grouped.items()
        }

    by_claim = current_index("claim", "claim_id")
    by_problem = current_index("research_problem", "problem_id")
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph["edges"]:
        if edge.get("relation") not in REVIEW_PROPAGATION_RELATIONS:
            continue
        adjacency[edge["source"]].add(edge["target"]); adjacency[edge["target"]].add(edge["source"])
    nodes = {n["id"]: n for n in graph["nodes"]}
    topic_node = next(
        (node["id"] for node in graph["nodes"] if node.get("kind") == "atr_v2_subject" and node.get("data", {}).get("active")),
        next((node["id"] for node in graph["nodes"] if node.get("kind") == "run"), None),
    )
    affected = []
    for event in latest.values():
        run_id = event.get("atr_run")
        source, claim, problem = event.get("atr_source_id"), event.get("atr_claim_id"), event.get("atr_problem_id")
        graph_node_id = event.get("atr_graph_node_id")
        # A claim is the more precise target.  Source-level feedback remains
        # supported for old reading notes, but is never silently promoted to a
        # claim review.
        explicit_node = nodes.get(graph_node_id)
        if explicit_node and not (
            (explicit_node.get("kind") == "claim" and explicit_node.get("data", {}).get("claim_id") == claim)
            or (explicit_node.get("kind") == "research_problem" and explicit_node.get("data", {}).get("problem_id") == problem)
            or (explicit_node.get("kind") == "knowledge_concept" and graph_node_id == explicit_node.get("id"))
            or (explicit_node.get("kind") == "collision_review" and graph_node_id == explicit_node.get("id"))
            or (explicit_node.get("kind") == "reality_signal_gap" and graph_node_id == explicit_node.get("id"))
            or (explicit_node.get("kind") in {"research_portfolio", "research_program",
                "legacy_research_run", "historical_alignment_audit"}
                and graph_node_id == explicit_node.get("id"))
            or (explicit_node.get("kind") in {"research_question", "derived_research_question", "real_world_tension"}
                and graph_node_id == explicit_node.get("id"))
        ):
            explicit_node = None
        start = ((explicit_node or {}).get("id") or by_claim.get(claim) or by_problem.get(problem)
                 or by_source.get(source) or (topic_node if run_id == graph.get("run") else None))
        target_type = (
            "claim" if nodes.get(start, {}).get("kind") == "claim"
            else "collision_review" if nodes.get(start, {}).get("kind") == "collision_review"
            else "research_problem" if nodes.get(start, {}).get("kind") == "research_problem"
            else "source" if by_source.get(source)
            else "knowledge" if nodes.get(start, {}).get("kind") == "knowledge_concept"
            else "research_question" if nodes.get(start, {}).get("kind") in {"research_question", "derived_research_question"}
            else "real_world_tension" if nodes.get(start, {}).get("kind") == "real_world_tension"
            else "reality_signal_gap" if nodes.get(start, {}).get("kind") == "reality_signal_gap"
            else "portfolio" if nodes.get(start, {}).get("kind") == "research_portfolio"
            else "program" if nodes.get(start, {}).get("kind") == "research_program"
            else "history" if nodes.get(start, {}).get("kind") == "legacy_research_run"
            else "alignment_audit" if nodes.get(start, {}).get("kind") == "historical_alignment_audit"
            else "topic" if start == topic_node and run_id == graph.get("run")
            else "unmapped"
        )
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
            if nodes[current]["kind"] in {"atr_v2_subject", "knowledge_concept", "claim", "collision_review", "research_question", "derived_research_question", "real_world_tension", "reality_signal_gap", "research_problem", "research_portfolio", "research_program", "legacy_research_run", "historical_alignment_audit"}:
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
            "annotation_run_id": run_id,
            "annotation_source_id": source,
            "annotation_claim_id": claim,
            "annotation_problem_id": problem,
            "annotation_graph_node_id": graph_node_id,
            "zotero_open_uri": event.get("zotero_open_uri"),
            "review_target_type": target_type,
            "target_found_in_projection": bool(start),
            # Retained for readers of report schema 0.2. It historically meant
            # "any review target resolved", not specifically a source.
            "source_found_in_projection": bool(start),
            "review_path_policy": "EXPLICIT_SOURCE_DECISION_RELATIONS_ONLY",
            "nearest_research_branches": nearest,
            "all_affected_research_questions": question_paths,
            "related_claims": claim_paths,
            "nearest_research_problems": nearest_problems,
            "all_affected_research_problems": problem_paths,
            "nearest_decision_objects": nearest_decision_objects,
            "all_affected_decision_objects": decision_paths,
            "codex_next_action": "请人工审阅该反馈；若它挑战断言或来源边界，创建新的 immutable ATR human-review-packet，再由 owner 决定是否重做 route/claim review。保留既有节点和边作为历史投影，不自动清退文献或改写 ATR lifecycle。",
        })
    return {"schema_version":"0.2", "projection": "derived-human-input-review", "events_seen":len(events),
            "ignored_events": ignored, "ignored_event_count": len(ignored),
            "latest_feedback_objects":len(latest), "latest_notes":sum(1 for kind, _ in latest if kind == "human_note_modified"),
            "latest_annotations":sum(1 for kind, _ in latest if kind == "human_annotation_modified"), "affected":affected}


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
        item_id = _event_item_id(event)
        if item_id in known:
            continue
        items.append({
            "id": item_id,
            "status": "pending_human_and_codex_review",
            "observed_at": event.get("at"),
            "annotation_source_id": affected["annotation_source_id"],
            "annotation_run_id": affected["annotation_run_id"],
            "annotation_claim_id": affected["annotation_claim_id"],
            "annotation_problem_id": affected["annotation_problem_id"],
            "annotation_graph_node_id": affected["annotation_graph_node_id"],
            "zotero_open_uri": affected["zotero_open_uri"],
            "review_target_type": affected["review_target_type"],
            "target_found_in_projection": affected["target_found_in_projection"],
            "source_found_in_projection": affected["source_found_in_projection"],
            "review_path_policy": affected["review_path_policy"],
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
    ignored = {item["id"]: item["reason"] for item in report.get("ignored_events", [])}
    for item in items:
        if item.get("status") == "pending_human_and_codex_review" and item.get("id") in ignored:
            item["status"] = "ignored_non_cognitive_event"
            item["ignore_reason"] = ignored[item["id"]]
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
        packet_id = "HRP-" + _event_item_id(event)
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
                "zotero_annotation_key": event.get("zotero_annotation_key"),
                "zotero_attachment_key": event.get("zotero_attachment_key"),
                "event_type": event.get("event"),
                "observed_at": event.get("at"),
                "notifier": event.get("notifier"),
            },
            "review": {
                "target_type": affected["review_target_type"],
                "run_id": affected["annotation_run_id"],
                "claim_id": affected["annotation_claim_id"],
                "problem_id": affected["annotation_problem_id"],
                "graph_node_id": affected["annotation_graph_node_id"],
                "source_id": affected["annotation_source_id"],
                "source_locator": event.get("source_locator"),
                "zotero_open_uri": event.get("zotero_open_uri"),
                "stance": event.get("review_stance", "UNSPECIFIED"),
                "owner_route_input": event.get("owner_route_input"),
                "owner_route_rationale": event.get("owner_route_rationale"),
                "note_html": event.get("note_html", ""),
                "annotation": {
                    "type": event.get("annotation_type"),
                    "text": event.get("annotation_text"),
                    "comment": event.get("annotation_comment"),
                    "color": event.get("annotation_color"),
                    "page_label": event.get("annotation_page_label"),
                    "position": event.get("annotation_position"),
                } if event.get("event") == "human_annotation_modified" else None,
            },
            "impact": {
                "target_found_in_projection": affected["target_found_in_projection"],
                "review_path_policy": affected["review_path_policy"],
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
    links_path = materialize_review_links(output)
    return {"schema_version": "0.2", "artifact_type": "human-review-packet-batch", "written": written, "existing": existing, "review_links": str(links_path)}


def materialize_review_links(output: Path) -> Path:
    """Build a derived Markdown index back to exact Zotero annotations."""
    directory = output / "human-input" / "review-packets"
    rows = []
    for path in sorted(directory.glob("HRP-*.json")) if directory.exists() else []:
        packet = json.loads(path.read_text(encoding="utf-8"))
        uri = packet.get("review", {}).get("zotero_open_uri")
        if not uri:
            continue
        label = packet.get("review", {}).get("source_id") or packet.get("review", {}).get("problem_id") or packet["packet_id"]
        rows.append(f"- [{packet['packet_id']} · {label} · 回到原始高亮]({uri})")
    target = output / "human-input" / "review-links.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "# Zotero 原始阅读定位\n\n"
        "这些链接来自 Zotero 在 annotation 事件发生时记录的 library/group、attachment、PDF page 与 annotation key；Codex 不重新猜测定位。\n\n"
        + ("\n".join(rows) if rows else "当前 packet 没有可用的 Reader annotation deep link。") + "\n",
        encoding="utf-8",
    )
    return target


def review_registry(registry_path: Path, out_path: Path) -> dict[str, Any]:
    """Aggregate human review input from every explicitly registered topic.

    Per-topic queues and immutable packets remain authoritative.  This
    replaceable Codex inbox only identifies where human attention changed the
    graph and which explicit decision object is nearest; it cannot advance a
    lifecycle state or rewrite history.
    """
    from .runs import validate_registry

    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    errors = validate_registry(registry)
    if errors:
        raise ValueError("invalid ATR workbench registry: " + "; ".join(errors))

    active_key = registry["active_run"]
    topics: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    new_queue_items = 0
    new_review_packets = 0
    for run in registry["runs"]:
        workspace = Path(run["workspace"])
        topic = {
            "key": run["key"],
            "label": run.get("label") or run["key"],
            "run_id": run.get("run_id"),
            "workspace": str(workspace),
            "active": run["key"] == active_key,
            "controller_kind": run["controller_kind"],
        }
        if not (workspace / "graph.json").is_file():
            topic.update({"status": "MISSING_PROJECTION", "events_seen": 0, "pending": 0})
            topics.append(topic)
            continue
        if not (workspace / "human-input" / "inbox.jsonl").is_file():
            topic.update({"status": "NO_HUMAN_INPUT", "events_seen": 0, "pending": 0})
            topics.append(topic)
            continue

        report = impact_report(workspace)
        queue = refresh_review_queue(workspace)
        packets = materialize_review_packets(workspace)
        topic_pending = [
            item for item in queue.get("items", [])
            if item.get("status") == "pending_human_and_codex_review"
        ]
        topic.update({
            "status": "PENDING_REVIEW" if topic_pending else "REVIEWED_OR_EMPTY",
            "events_seen": report["events_seen"],
            "latest_feedback_objects": report["latest_feedback_objects"],
            "pending": len(topic_pending),
            "new_queue_items": queue.get("new_items", 0),
            "new_review_packets": len(packets["written"]),
        })
        topics.append(topic)
        new_queue_items += queue.get("new_items", 0)
        new_review_packets += len(packets["written"])
        for item in topic_pending:
            nearest = item.get("nearest_decision_objects") or []
            nearest_distance = min(
                (node.get("distance_from_review_target", 10**9) for node in nearest),
                default=None,
            )
            primary = min(nearest, key=lambda node: (
                node.get("distance_from_review_target", 10**9),
                DECISION_OBJECT_PRIORITY.get(node.get("kind"), 10**9),
                node.get("id") or "",
            ), default=None)
            pending.append({
                "topic_key": run["key"],
                "topic_label": topic["label"],
                "active_topic": topic["active"],
                "workspace": str(workspace),
                "queue_item_id": item["id"],
                "observed_at": item.get("observed_at"),
                "review_target_type": item.get("review_target_type"),
                "source_id": item.get("annotation_source_id"),
                "graph_node_id": item.get("annotation_graph_node_id"),
                "zotero_open_uri": item.get("zotero_open_uri"),
                "nearest_decision_distance": nearest_distance,
                "primary_decision_object": primary,
                "nearest_decision_objects": nearest,
                "nearest_research_problems": item.get("nearest_research_problems", []),
                "review_path_policy": item.get("review_path_policy"),
                "required_action": item.get("recommended_next_action"),
            })

    pending.sort(key=lambda item: (
        not item["active_topic"],
        item["nearest_decision_distance"] if item["nearest_decision_distance"] is not None else 10**9,
        item.get("observed_at") or "",
        item["topic_key"],
        item["queue_item_id"],
    ))
    summary = {
        "schema_version": "0.1",
        "projection": "codex-multi-topic-human-input-inbox",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "registry": str(registry_path.resolve()),
        "active_topic": active_key,
        "lifecycle_effect": "REVIEW_INPUT_ONLY",
        "history_policy": "APPEND_ONLY_PRESERVE_OLD_NODES_AND_EDGES",
        "topics": topics,
        "pending": pending,
        "counts": {
            "topics_registered": len(topics),
            "topics_with_pending_review": sum(topic["pending"] > 0 for topic in topics),
            "pending_review_objects": len(pending),
            "new_queue_items": new_queue_items,
            "new_review_packets": new_review_packets,
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = out_path.parent / ("." + out_path.name + ".tmp")
    temporary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(out_path)
    return summary


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


def attach_review_assessment_to_v2(output: Path, v2_run_dir: Path, assessment_path: Path,
                                   subject_id: str, expected_version: int,
                                   atrctl: Path) -> dict[str, Any]:
    """Record a separately authored assessment and close the pending UI item.

    The v2 controller validates owner/reviewer isolation and the assessment's
    packet/disposition lineage.  This bridge only invokes that transactional
    API and updates the derived Zotero queue; it cannot transition the subject.
    """
    if not assessment_path.is_file():
        raise ValueError(f"assessment not found: {assessment_path}")
    assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    if assessment.get("artifact_type") != "human-review-assessment":
        raise ValueError("assessment has wrong artifact_type")
    for field in ("assessment_id", "packet_id", "disposition_id", "outcome"):
        if not assessment.get(field):
            raise ValueError(f"assessment lacks {field}")
    packet_path = output / "human-input" / "review-packets" / f"{assessment['packet_id']}.json"
    if not packet_path.is_file():
        raise ValueError("assessment packet does not exist in this Zotero workspace")
    if not atrctl.is_file():
        raise ValueError(f"ATR v2 controller not found: {atrctl}")
    result = subprocess.run([
        "python3", str(atrctl), "record-human-assessment", str(v2_run_dir),
        "--subject", subject_id, "--expected-version", str(expected_version),
        "--assessment", str(assessment_path),
    ], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "atrctl failed")
    artifact_id = result.stdout.strip()
    queue_path = output / "human-input" / "review-queue.json"
    if queue_path.is_file():
        queue = json.loads(queue_path.read_text(encoding="utf-8"))
        event_id = str(assessment["packet_id"]).removeprefix("HRP-")
        for item in queue.get("items", []):
            if item.get("id") == event_id:
                item["status"] = "review_assessment_recorded"
                item.setdefault("assessment_history", []).append({
                    "assessment_id": assessment["assessment_id"],
                    "disposition_id": assessment["disposition_id"],
                    "outcome": assessment["outcome"],
                    "artifact_id": artifact_id,
                })
        queue_path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "artifact_id": artifact_id,
        "assessment_id": assessment["assessment_id"],
        "packet_id": assessment["packet_id"],
        "outcome": assessment["outcome"],
        "required_followup_artifact_kind": assessment.get("required_followup_artifact_kind"),
        "subject_id": subject_id,
        "subject_version": expected_version,
        "lifecycle_changed": False,
        "history_policy": "PRESERVE_OLD_NODES_AND_EDGES_UNTIL_SEPARATE_TYPED_ARTIFACT",
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
        "review_target": {"target_type": review.get("target_type"), "claim_id": review.get("claim_id"), "problem_id": review.get("problem_id"), "source_id": review.get("source_id"), "source_locator": review.get("source_locator")},
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
