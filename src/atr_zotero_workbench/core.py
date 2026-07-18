"""Read-only adapters that turn ATR evidence into a traceable graph projection."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


@dataclass
class LegacyRun:
    path: Path
    sources: list[dict[str, Any]]
    frontier: dict[str, Any]
    run_state: dict[str, Any]
    intake: dict[str, Any]
    skill_events: list[dict[str, Any]]
    gaps: list[str]


def load_legacy_run(path: Path) -> LegacyRun:
    required = path / "evidence" / "sources.jsonl"
    if not required.exists():
        raise ValueError(f"Not a supported ATR v1 run: missing {required}")
    frontier_path = path / "knowledge" / "frontier-map.json"
    frontier = json.loads(frontier_path.read_text(encoding="utf-8")) if frontier_path.exists() else {}
    state_path = path / "run-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    intake_path = path / "intake.json"
    intake = json.loads(intake_path.read_text(encoding="utf-8")) if intake_path.exists() else {}
    skill_events = read_jsonl(path / "observability" / "skill-events.jsonl")
    gaps = []
    for relative in ("evidence/claims.jsonl", "evidence/edges.jsonl", "observability/skill-events.jsonl"):
        target = path / relative
        if not target.exists() or not target.read_text(encoding="utf-8").strip():
            gaps.append(f"缺少可用的 {relative}")
    sources = read_jsonl(required)
    # Real-world material is intentionally held outside the scholarly ledger.
    # Agents or researchers add only source-grounded rows here; the projection
    # retains its different epistemic role all the way to the Zotero UI.
    contextual_path = path / "evidence" / "contextual-sources.jsonl"
    for source in read_jsonl(contextual_path):
        source.setdefault("source_layer", "contextual_inspiration")
        sources.append(source)
    if state.get("schema_version") == "1.0" and not frontier:
        gaps.append("当前 ATR v0.9 run 尚无 knowledge/frontier-map.json；只展示 intake 与生命周期，不生成研究问题")
    if not sources:
        gaps.append("当前 run 的 evidence/sources.jsonl 为空；不生成文献或证据结论")
    return LegacyRun(path, sources, frontier, state, intake, skill_events, gaps)


def _node(node_id: str, kind: str, label: str, **data: Any) -> dict[str, Any]:
    return {"id": node_id, "kind": kind, "label": label, "data": data}


def _source_layer(source_kind: str, declared: str | None = None) -> str:
    """Keep contextual inspiration distinct from scholarly evidence.

    The legacy ledger has a free-text `kind`, so this is deliberately a
    conservative classification. Unknown material remains a source requiring
    human review rather than being promoted to academic evidence.
    """
    if declared in {"scholarly_evidence", "contextual_inspiration", "source_needs_review"}:
        return declared
    kind = source_kind.upper()
    if any(token in kind for token in ("BLOG", "NEWS", "MAGAZINE", "REPORT", "WHITEPAPER", "SOCIAL")):
        return "contextual_inspiration"
    if any(token in kind for token in ("PAPER", "BENCHMARK", "PREPRINT", "CONFERENCE", "JOURNAL")):
        return "scholarly_evidence"
    return "source_needs_review"


def project_graph(run: LegacyRun) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    def edge(source: str, target: str, relation: str, **data: Any) -> None:
        if any(item["source"] == source and item["target"] == target and item["relation"] == relation for item in edges):
            return
        edges.append({"source": source, "target": target, "relation": relation, "data": data})

    run_id = run.run_state.get("run_id", run.path.name)
    nodes.append(_node(f"run:{run_id}", "run", run_id, stage=run.run_state.get("active_stage"),
                       status=run.run_state.get("status"), next_action=run.run_state.get("next_action"), gaps=run.gaps))
    for gate_id, status in run.run_state.get("gates", {}).items():
        nodes.append(_node(f"gate:{gate_id}", "gate", f"{gate_id} · {status}", gate_id=gate_id, status=status))
        edge(f"run:{run_id}", f"gate:{gate_id}", "tracks_gate")
    for event in run.skill_events:
        event_id = event.get("event_id")
        if not event_id:
            continue
        nodes.append(_node(f"skill:{event_id}", "skill_event",
                           f"{event.get('skill', 'unknown skill')} · {event.get('event', 'UNKNOWN')} · {event.get('status', 'UNKNOWN')}",
                           event_id=event_id, timestamp=event.get("timestamp"), skill=event.get("skill"),
                           event=event.get("event"), status=event.get("status"), invocation=event.get("invocation"),
                           artifact_ids=event.get("artifact_ids", [])))
        edge(f"run:{run_id}", f"skill:{event_id}", "records_skill_event")
    domain = run.frontier.get("domain") or run.intake.get("initial_question") or "未定义领域"
    nodes.append(_node("concept:domain", "concept", domain, scope=run.frontier.get("scope", "")))
    edge(f"run:{run_id}", "concept:domain", "explores")
    for source in run.sources:
        sid = source["source_id"]
        source_kind = source.get("kind", "")
        source_layer = _source_layer(source_kind, source.get("source_layer"))
        nodes.append(_node(f"paper:{sid}", "paper", source.get("title", sid), source_id=sid,
                           url=source.get("url", ""), source_kind=source_kind, source_layer=source_layer,
                           supports=source.get("supports", ""), does_not_support=source.get("does_not_support", ""),
                           why_it_matters=source.get("why_it_matters", ""), keywords=source.get("keywords", []),
                           related_tension_ids=source.get("related_tension_ids", [])))
        edge("concept:domain", f"paper:{sid}",
             "has_evidence" if source_layer == "scholarly_evidence" else "inspires_context")
        nodes.append(_node(f"evidence:{sid}", "evidence_boundary", f"{sid} 的证据边界",
                           supports=source.get("supports", ""), does_not_support=source.get("does_not_support", "")))
        edge(f"paper:{sid}", f"evidence:{sid}", "states_boundary")
    for tension in run.frontier.get("frontier_tensions", []):
        tid = tension["tension_id"]
        nodes.append(_node(f"question:{tid}", "research_question", tension["question"],
                           tension_id=tid, source="ATR frontier-map（问题，不是论文结论）",
                           explanations=tension.get("competing_explanations", []),
                           freshness=tension.get("freshness", "")))
        edge("concept:domain", f"question:{tid}", "contains_question")
        concept_ids = []
        for dim in tension.get("dimensions", []):
            cid = f"concept:{dim}"
            if not any(item["id"] == cid for item in nodes):
                nodes.append(_node(cid, "concept", dim))
            edge(f"question:{tid}", cid, "requires_concept")
            concept_ids.append(cid)
        for sid in tension.get("anchor_source_ids", []):
            if any(item["id"] == f"paper:{sid}" for item in nodes):
                edge(f"question:{tid}", f"paper:{sid}", "anchored_by")
                # This is deliberately a question-scoped association, not a
                # claim that the source establishes the concept. It lets the
                # knowledge view link a concept to the reading that made it
                # relevant while preserving the source's evidence boundary.
                for cid in concept_ids:
                    edge(cid, f"paper:{sid}", "illustrated_by_question_anchor",
                         tension_id=tid, attribution="derived_question_context")
        for source in run.sources:
            if tid in source.get("related_tension_ids", []) and source.get("source_id"):
                sid = source["source_id"]
                if _source_layer(source.get("kind", ""), source.get("source_layer")) == "contextual_inspiration":
                    edge(f"question:{tid}", f"paper:{sid}", "inspired_by_context",
                         attribution="contextual_inspiration", why_it_matters=source.get("why_it_matters", ""))
    return {"schema_version": "0.1", "projection": "derived-read-only", "run": run_id,
            "diagnostics": run.gaps, "nodes": nodes, "edges": edges}
