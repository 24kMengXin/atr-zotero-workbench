#!/usr/bin/env python3
"""Create strict ATR v2 attachments from the audited multilingual continuation.

This is a deterministic migration projection.  It never edits the historical
continuation or advances the v2 subject.  Missing locators remain explicitly
unverified instead of being invented.
"""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTINUATION = Path("/Users/zone/Documents/multilingual-aaai/research-runs/2026-07-18-multilingual-agent-action-continuation")
GRAPH = ROOT / "output" / "multilingual-agent-action-continuation" / "graph.json"
OLD_V2 = Path("/Users/zone/Documents/multilingual-aaai/research-runs/2026-07-18-multilingual-agent-action-v2-intake")
OUT = ROOT / ".runtime" / "v2-alignment-inputs"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    graph = load(GRAPH)
    sources = {
        node["data"]["source_id"]: node
        for node in graph["nodes"]
        if node.get("kind") == "paper" and node.get("data", {}).get("source_id")
    }

    def source_record(source_id: str, *, source_function: str | None = None) -> dict:
        node = sources[source_id]
        data = node.get("data", {})
        record = {
            "source_id": source_id,
            "title": node.get("label") or source_id,
            "url": data.get("url") or "UNRESOLVED_URL_REQUIRES_OWNER_REVIEW",
            "kind": data.get("source_kind") or "SOURCE_NEEDS_REVIEW",
            "supports": data.get("supports") or "Only the explicitly recorded continuation observation.",
            "does_not_establish": data.get("does_not_support") or data.get("does_not_establish")
            or "No broader claim is established by this migration record.",
        }
        if source_function:
            record["source_function"] = source_function
            record["observed_at"] = data.get("observed_at") or "2026-07-18"
        return record

    concept = load(CONTINUATION / "knowledge" / "concept-map.json")
    concept_source_ids = sorted({sid for item in concept["concepts"] for sid in item.get("source_ids", [])})
    knowledge_map = {
        "artifact_type": "knowledge-map",
        "schema_version": "1.0",
        "map_id": concept["map_id"],
        "topic": "Multilingual structured tool execution and action attribution",
        "scope": concept["scope"],
        "created_at": concept["created_at"],
        "does_not_establish": concept["does_not_establish"],
        "sources": [source_record(source_id) for source_id in concept_source_ids],
        "concepts": concept["concepts"],
    }

    opportunity = load(CONTINUATION / "knowledge" / "opportunity-map.json")
    opportunity_functions = {
        "SRC-MLCL-2026": "SCIENTIFIC_FRONTIER",
        "SRC-MCP-SCHEMA-CONVERGENCE-2026": "PRIMARY_WORKFLOW",
    }
    opportunity_sources = [
        source_record(source_id, source_function=opportunity_functions[source_id])
        for source_id in opportunity["signal_refs"]
    ]
    opportunity_map = {
        "artifact_type": "opportunity-map",
        "schema_version": "1.0",
        "map_id": opportunity["map_id"],
        "scope": opportunity["scope"],
        "searched_through": opportunity["searched_through"],
        "created_at": opportunity["created_at"],
        "valid_until": opportunity["valid_until"],
        "does_not_establish": "The signals motivate a bounded review question; they do not certify novelty, prevalence, deployment harm, or a lifecycle transition.",
        "sources": opportunity_sources,
        "tension_clusters": [{
            "tension_id": cluster["cluster_id"],
            "label": cluster["observed_tension"],
            "source_ids": cluster["signal_refs"],
            "actor": cluster["actor"],
            "incumbent_practice": cluster["incumbent_practice"],
            "material_consequence": cluster["material_consequence"],
            "candidate_construct": cluster["candidate_construct"],
            "alternative_explanations": cluster["alternative_explanations"],
            "translation_status": cluster["translation_status"],
            "does_not_establish": cluster["does_not_establish"],
        } for cluster in opportunity["tension_clusters"]],
    }

    problem = load(CONTINUATION / "knowledge" / "research-problem-cards" / "RQ-multilingual-action-attribution.v1.json")
    old_problem_candidates = [
        load(path) for path in sorted((OLD_V2 / "artifacts").glob("*/body.json"))
        if load(path).get("artifact_type") == "problem-case"
    ]
    old_problem = next(
        candidate for candidate in old_problem_candidates
        if candidate.get("problem_id") != problem["problem_id"]
    )
    old_spans = {span["source_id"]: span for span in old_problem.get("source_spans", [])}
    role_by_source = {role["source_id"]: role for role in problem["paper_roles"]}
    posture = {
        "OBJECTIVE_DIAGNOSTIC": "OBJECTIVELY_LEAVES",
        "OBJECTIVE_MEASUREMENT": "OBJECTIVELY_LEAVES",
        "WORKFLOW_CONSTRAINT": "CONTEXT_ONLY",
    }
    problem_source_ids = sorted({
        *role_by_source,
        *(sid for question in problem.get("derived_questions", []) for sid in question.get("source_ids", [])),
    })
    spans = []
    for source_id in problem_source_ids:
        record = source_record(source_id)
        role = role_by_source.get(source_id)
        previous = old_spans.get(source_id, {})
        spans.append({
            **record,
            "locator": previous.get("locator") or sources[source_id].get("data", {}).get("locator")
            or "NOT_YET_VERIFIED_IN_ZOTERO",
            "observation": previous.get("observation") or record["supports"],
            "problem_posture": posture.get((role or {}).get("posture"), "CONTEXT_ONLY"),
            "resolves": (role or {}).get("resolves")
            or "No problem-resolution role is established; this source is retained only because an explicit derived question cites it.",
            "leaves_unresolved": (role or {}).get("leaves_unresolved")
            or "Its exact relevance and locator require Zotero review.",
            "does_not_establish": record["does_not_establish"],
        })
    problem_case = {
        "artifact_type": "problem-case",
        "problem_id": problem["problem_id"],
        "supersedes_problem_id": old_problem["problem_id"],
        "research_question": problem["research_question"],
        "worlds": [f"{world['label']}：{world['explanation']}" for world in problem["counterfactual_worlds"]],
        "discriminator": old_problem["discriminator"],
        "falsifier": problem["minimum_falsifier"],
        "scope": old_problem.get("scope") or problem["contribution_boundary"]["promotion_rule"],
        "does_not_establish": "This is a review-bound problem case, not a passed claim, proposal, prevalence estimate, or deployment-harm finding.",
        "source_spans": spans,
        "derived_questions": problem["derived_questions"],
    }

    OUT.mkdir(parents=True, exist_ok=True)
    for name, payload in {
        "knowledge-map.v2.json": knowledge_map,
        "opportunity-map.v2.json": opportunity_map,
        "problem-case.v2.json": problem_case,
    }.items():
        (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
