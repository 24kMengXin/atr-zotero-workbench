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
    claims: list[dict[str, Any]]
    item_contract_audits: list[dict[str, Any]]
    knowledge_contexts: list[dict[str, Any]]
    landscape_briefs: list[dict[str, Any]]
    concept_map: dict[str, Any]
    opportunity_map: dict[str, Any]
    research_problems: list[dict[str, Any]]
    human_review_dispositions: list[dict[str, Any]]
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
    claims = read_jsonl(path / "evidence" / "claims.jsonl")
    item_contract_audits = read_jsonl(path / "evidence" / "item-contract-audit.jsonl")
    knowledge_contexts = []
    for context_path in sorted((path / "knowledge").glob("knowledge-context*.json")) if (path / "knowledge").exists() else []:
        knowledge_contexts.append(json.loads(context_path.read_text(encoding="utf-8")))
    landscape_briefs = []
    for brief_path in sorted((path / "knowledge").glob("landscape-brief*.json")) if (path / "knowledge").exists() else []:
        landscape_briefs.append(json.loads(brief_path.read_text(encoding="utf-8")))
    concept_map_path = path / "knowledge" / "concept-map.json"
    concept_map = json.loads(concept_map_path.read_text(encoding="utf-8")) if concept_map_path.exists() else {}
    opportunity_path = path / "knowledge" / "opportunity-map.json"
    opportunity_map = json.loads(opportunity_path.read_text(encoding="utf-8")) if opportunity_path.exists() else {}
    research_problems = []
    problem_dir = path / "knowledge" / "research-problem-cards"
    for problem_path in sorted(problem_dir.glob("*.json")) if problem_dir.exists() else []:
        problem = json.loads(problem_path.read_text(encoding="utf-8"))
        # The artifact path is provenance, not a field authored by the research
        # worker.  Keeping it lets the projection retain an R0 draft alongside
        # its R2 continuation without silently collapsing two different states.
        problem["_artifact_path"] = str(problem_path.relative_to(path))
        research_problems.append(problem)
    human_review_dispositions = read_jsonl(path / "decisions" / "human-review-dispositions.jsonl")
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
    if frontier and not knowledge_contexts:
        gaps.append("当前 run 尚无 knowledge-context artifact；无法展示从前沿张力向断言/实验收缩的可审计路径")
    if not opportunity_map:
        gaps.append("当前 run 尚无 opportunity-map artifact；无法展示现实情境到研究问题的受控启发链路")
    if not research_problems:
        gaps.append("当前 run 尚无 research-problem-card artifact；无法展示两种解释、可区分观测与最小证伪条件")
    return LegacyRun(path, sources, frontier, state, intake, skill_events, claims, item_contract_audits, knowledge_contexts, landscape_briefs, concept_map, opportunity_map, research_problems, human_review_dispositions, gaps)


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


def _claim_text(claim: dict[str, Any]) -> str:
    """The audited legacy runs used both `text` and `claim` field names."""
    return str(claim.get("text") or claim.get("claim") or claim.get("claim_id") or "未命名断言")


def _explicit_claim_source_ids(claim: dict[str, Any]) -> list[str]:
    """Return only source links declared by the artifact itself.

    Older claims commonly contain no paper links.  We must not infer one from
    a seed ID, a filename, or a shared topic: that would turn provenance into
    an attractive but false graph edge.
    """
    ids: list[str] = []
    for key in ("source_ids", "evidence_source_ids", "anchor_source_ids"):
        value = claim.get(key, [])
        if isinstance(value, list):
            ids.extend(str(item) for item in value if item)
    return list(dict.fromkeys(ids))


def project_graph(run: LegacyRun) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    def edge(source: str, target: str, relation: str, **data: Any) -> None:
        if any(item["source"] == source and item["target"] == target and item["relation"] == relation for item in edges):
            return
        edges.append({"source": source, "target": target, "relation": relation, "data": data})

    run_id = run.run_state.get("run_id", run.path.name)
    nodes.append(_node(f"run:{run_id}", "run", run_id, stage=run.run_state.get("active_stage"),
                       status=run.run_state.get("status"), next_action=run.run_state.get("next_action"),
                       topic_route_package_path=run.run_state.get("topic_route_package_path"),
                       stage_contract=run.run_state.get("stage_contract", {}), gaps=run.gaps))
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
                           artifact_ids=event.get("artifact_ids", []), declared_skills=event.get("declared_skills", []),
                           activity_boundary=event.get("activity_boundary")))
        edge(f"run:{run_id}", f"skill:{event_id}", "records_skill_event")
    known_paper_ids = {source.get("source_id") for source in run.sources if source.get("source_id")}
    known_claim_ids: set[str] = set()
    for claim in run.claims:
        claim_id = claim.get("claim_id")
        if not claim_id:
            continue
        claim_id = str(claim_id)
        known_claim_ids.add(claim_id)
        nodes.append(_node(
            f"claim:{claim_id}", "claim", _claim_text(claim),
            claim_id=claim_id, status=claim.get("status", "UNSPECIFIED"),
            version=claim.get("version"), seed_id=claim.get("seed_id"),
            conditions=claim.get("conditions", {}),
            forbidden_claims=claim.get("forbidden_claims", []),
            valid_until=claim.get("valid_until"),
            revalidation_trigger=claim.get("revalidation_trigger", []),
            collision_review=claim.get("collision_review", {}),
        ))
        edge(f"run:{run_id}", f"claim:{claim_id}", "records_claim")
        for source_id in _explicit_claim_source_ids(claim):
            if source_id in known_paper_ids:
                edge(f"claim:{claim_id}", f"paper:{source_id}", "cites_explicit_source")
    for audit in run.item_contract_audits:
        audit_id = str(audit.get("audit_id") or audit.get("source_id") or "unknown")
        audit_node = f"evidence_audit:{audit_id}"
        nodes.append(_node(audit_node, "evidence_audit", audit.get("observed", audit_id),
                           audit_id=audit_id, source_id=audit.get("source_id"), access_status=audit.get("access_status", "UNSPECIFIED"),
                           item_contract_visibility=audit.get("item_contract_visibility", ""), independent_action_oracle=audit.get("independent_action_oracle", ""),
                           does_not_establish=audit.get("does_not_establish", ""), disposition=audit.get("disposition", ""),
                           next_required_action=audit.get("next_required_action", "")))
        edge(f"run:{run_id}", audit_node, "records_evidence_audit")
        source_id = audit.get("source_id")
        if source_id in known_paper_ids:
            edge(audit_node, f"paper:{source_id}", "audits_explicit_source")
    for claim in run.claims:
        claim_id, prior = claim.get("claim_id"), claim.get("supersedes")
        if claim_id and prior and str(prior) in known_claim_ids:
            edge(f"claim:{claim_id}", f"claim:{prior}", "supersedes")
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
    known_questions = {node["data"].get("tension_id") for node in nodes if node["kind"] == "research_question"}
    for context in run.knowledge_contexts:
        context_id = str(context.get("context_id", "unknown"))
        context_node = f"knowledge_context:{context_id}"
        nodes.append(_node(context_node, "knowledge_context", context_id,
                           decision_node=context.get("decision_node"), map_id=context.get("map_id"),
                           unresolved=context.get("unresolved", []), valid_until=context.get("valid_until")))
        edge(f"run:{run_id}", context_node, "records_knowledge_context")
        for tension_id in context.get("frontier_tension_ids", []):
            if tension_id in known_questions:
                edge(f"question:{tension_id}", context_node, "selected_for_contraction")
        previous = context_node
        for step in context.get("contraction_path", []):
            step_id = str(step.get("step_id", "unknown"))
            step_node = f"knowledge_step:{context_id}:{step_id}"
            nodes.append(_node(step_node, "knowledge_step", step.get("question", step_id),
                               context_id=context_id, step_id=step_id, layer=step.get("layer"),
                               invariant_preserved=step.get("invariant_preserved", ""),
                               excluded_explanations=step.get("excluded_explanations", [])))
            edge(previous, step_node, "contracts_to")
            previous = step_node
            for source_id in step.get("evidence_refs", []):
                if source_id in known_paper_ids:
                    edge(step_node, f"paper:{source_id}", "uses_explicit_evidence")
    for brief in run.landscape_briefs:
        brief_id = str(brief.get("brief_id") or brief.get("artifact_id") or brief.get("created_at") or "unknown")
        brief_node = f"landscape_brief:{brief_id}"
        nodes.append(_node(brief_node, "landscape_brief", brief.get("question", brief_id),
                           brief_id=brief_id, disposition=brief.get("disposition"),
                           observed_tension=brief.get("observed_tension", ""),
                           sources_do_not_establish=brief.get("sources_do_not_establish", []),
                           causal_fingerprint=brief.get("causal_fingerprint", {}),
                           rival_worlds=brief.get("rival_worlds", []),
                           smallest_next_discriminator=brief.get("smallest_next_discriminator", ""),
                           named_missing_premise=brief.get("named_missing_premise", ""),
                           immutable=brief.get("immutable") is True))
        edge(f"run:{run_id}", brief_node, "records_landscape_brief")
        for source in brief.get("inspected_sources", []):
            source_id = source.get("source_id")
            if source_id in known_paper_ids:
                edge(brief_node, f"paper:{source_id}", "inspects_explicit_source",
                     locator=source.get("locator", ""), observation=source.get("observation", ""))
    if run.concept_map:
        map_id = str(run.concept_map.get("map_id", "unknown"))
        map_node = f"concept_map:{map_id}"
        nodes.append(_node(map_node, "concept_map", run.concept_map.get("scope", map_id),
                           map_id=map_id, status=run.concept_map.get("status", "UNSPECIFIED"),
                           created_at=run.concept_map.get("created_at"),
                           does_not_establish=run.concept_map.get("does_not_establish", "")))
        edge(f"run:{run_id}", map_node, "records_concept_map")
        declared_concepts = {str(item.get("concept_id")) for item in run.concept_map.get("concepts", []) if item.get("concept_id")}
        for item in run.concept_map.get("concepts", []):
            concept_id = str(item.get("concept_id", "unknown"))
            node_id = f"knowledge_concept:{map_id}:{concept_id}"
            nodes.append(_node(node_id, "knowledge_concept", item.get("label", concept_id),
                               concept_id=concept_id, map_id=map_id, definition=item.get("definition", ""),
                               source_ids=item.get("source_ids", []), does_not_establish=item.get("does_not_establish", ""),
                               depth=item.get("depth")))
            parent_id = item.get("parent_id")
            if parent_id and str(parent_id) in declared_concepts:
                edge(f"knowledge_concept:{map_id}:{parent_id}", node_id, "specializes_concept")
            else:
                edge(map_node, node_id, "roots_concept")
            for source_id in item.get("source_ids", []):
                if source_id in known_paper_ids:
                    edge(node_id, f"paper:{source_id}", "defines_with_explicit_source")
    if run.opportunity_map:
        map_id = str(run.opportunity_map.get("map_id", "unknown"))
        opportunity_node = f"opportunity_map:{map_id}"
        nodes.append(_node(opportunity_node, "opportunity_map", run.opportunity_map.get("scope", map_id),
                           map_id=map_id, searched_through=run.opportunity_map.get("searched_through"),
                           valid_until=run.opportunity_map.get("valid_until"),
                           translation_policy=run.opportunity_map.get("translation_policy", {})))
        edge(f"run:{run_id}", opportunity_node, "records_opportunity_map")
        for cluster in run.opportunity_map.get("tension_clusters", []):
            cluster_id = str(cluster.get("cluster_id", "unknown"))
            cluster_node = f"real_world_tension:{cluster_id}"
            nodes.append(_node(cluster_node, "real_world_tension", cluster.get("observed_tension", cluster_id),
                               cluster_id=cluster_id, actor=cluster.get("actor"), incumbent_practice=cluster.get("incumbent_practice"),
                               material_consequence=cluster.get("material_consequence"), candidate_construct=cluster.get("candidate_construct"),
                               alternative_explanations=cluster.get("alternative_explanations", []),
                               translation_status=cluster.get("translation_status"), does_not_establish=cluster.get("does_not_establish")))
            edge(opportunity_node, cluster_node, "clusters_real_world_tension")
            for source_id in cluster.get("signal_refs", []):
                if source_id in known_paper_ids:
                    edge(cluster_node, f"paper:{source_id}", "grounded_in_explicit_signal")
    problem_id_counts: dict[str, int] = {}
    for problem in run.research_problems:
        problem_id = str(problem.get("problem_id", "unknown"))
        problem_id_counts[problem_id] = problem_id_counts.get(problem_id, 0) + 1
    canonical_problem_paths: dict[str, str] = {}
    for problem in run.research_problems:
        problem_id = str(problem.get("problem_id", "unknown"))
        # Prefer a non-draft version as the stable decision target.  Old drafts
        # remain visible under their artifact identity and link to that target.
        if not str(problem.get("status", "")).startswith("DRAFT_R0"):
            canonical_problem_paths[problem_id] = problem.get("_artifact_path", "")
    for problem in run.research_problems:
        problem_id = str(problem.get("problem_id", "unknown"))
        artifact_path = problem.get("_artifact_path", "")
        is_noncanonical_version = (
            problem_id_counts[problem_id] > 1
            and canonical_problem_paths.get(problem_id)
            and artifact_path != canonical_problem_paths[problem_id]
        )
        problem_node = (
            f"research_problem:{problem_id}:{artifact_path}"
            if is_noncanonical_version else f"research_problem:{problem_id}"
        )
        nodes.append(_node(problem_node, "research_problem", problem.get("research_question", problem_id),
                           problem_id=problem_id, status=problem.get("status", "UNSPECIFIED"), claim_version=problem.get("claim_version"),
                           artifact_path=artifact_path, artifact_version=problem.get("artifact_version"),
                           construct_of_interest=problem.get("construct_of_interest"), status_quo=problem.get("status_quo"),
                           confounded_observation=problem.get("confounded_observation"),
                           counterfactual_worlds=problem.get("counterfactual_worlds", []),
                           decision_consequence=problem.get("decision_consequence"),
                           minimum_falsifier=problem.get("minimum_falsifier"),
                           contribution_boundary=problem.get("contribution_boundary", {})))
        edge(f"run:{run_id}", problem_node, "records_research_problem")
        if is_noncanonical_version:
            edge(problem_node, f"research_problem:{problem_id}", "superseded_by_recorded_problem_version")
        claim_id = problem.get("claim_version")
        if claim_id in known_claim_ids:
            edge(problem_node, f"claim:{claim_id}", "tests_claim")
        for layer in problem.get("evidence_layers", []):
            for source_id in layer.get("sources", []):
                if source_id in known_paper_ids:
                    edge(problem_node, f"paper:{source_id}", "grounds_in_explicit_evidence_layer", evidence_kind=layer.get("kind"))
        for role in problem.get("paper_roles", []):
            source_id = role.get("source_id")
            if source_id in known_paper_ids:
                edge(f"paper:{source_id}", problem_node, "has_explicit_problem_role",
                     posture=role.get("posture", "OBSERVED"), resolves=role.get("resolves", ""),
                     leaves_unresolved=role.get("leaves_unresolved", ""))
    for disposition in run.human_review_dispositions:
        decision_id = str(disposition.get("decision_id", "unknown"))
        node_id = f"human_review:{decision_id}"
        nodes.append(_node(node_id, "human_review_disposition", f"人类反馈处置 · {disposition.get('disposition', 'UNSPECIFIED')}",
                           decision_id=decision_id, packet_id=disposition.get("packet_id"), owner=disposition.get("owner"),
                           disposition=disposition.get("disposition"), rationale=disposition.get("rationale"),
                           recorded_at=disposition.get("recorded_at"), controller_boundary=disposition.get("controller_boundary")))
        edge(f"run:{run_id}", node_id, "records_human_review_disposition")
        target = disposition.get("review_target", {})
        claim_id, source_id = target.get("claim_id"), target.get("source_id")
        if claim_id in known_claim_ids:
            edge(node_id, f"claim:{claim_id}", "disposes_review_of_claim")
        if source_id in known_paper_ids:
            edge(node_id, f"paper:{source_id}", "disposes_review_of_source")
        affected_ids = disposition.get("affected_node_ids", {})
        for tension_id in affected_ids.get("research_questions", []):
            question_id = f"question:{tension_id}"
            if any(node["id"] == question_id for node in nodes):
                edge(node_id, question_id, "requests_reconsideration_of_question")
        for problem_id in affected_ids.get("research_problems", []):
            problem_id = f"research_problem:{problem_id}"
            if any(node["id"] == problem_id for node in nodes):
                edge(node_id, problem_id, "requests_reconsideration_of_problem")
    timeline: list[dict[str, Any]] = []
    for event in run.skill_events:
        if event.get("timestamp"):
            declared = event.get("declared_skills", [])
            suffix = f" · 声明技能：{', '.join(declared)}" if declared else ""
            timeline.append({"at": event["timestamp"], "kind": "skill_event", "id": event.get("event_id"),
                             "label": f"{event.get('skill', 'unknown skill')} · {event.get('event', 'UNKNOWN')} · {event.get('status', 'UNKNOWN')}{suffix}",
                             "artifact_ids": event.get("artifact_ids", []), "activity_boundary": event.get("activity_boundary")})
    for claim in run.claims:
        if claim.get("recorded_at"):
            timeline.append({"at": claim["recorded_at"], "kind": "claim", "id": claim.get("claim_id"),
                             "label": _claim_text(claim), "status": claim.get("status", "UNSPECIFIED")})
    for audit in run.item_contract_audits:
        if audit.get("recorded_at"):
            timeline.append({"at": audit["recorded_at"], "kind": "evidence_audit", "id": audit.get("audit_id") or audit.get("source_id"),
                             "label": f"item-contract audit · {audit.get('disposition', 'UNSPECIFIED')}", "source_id": audit.get("source_id")})
    for context in run.knowledge_contexts:
        if context.get("created_at"):
            timeline.append({"at": context["created_at"], "kind": "knowledge_context", "id": context.get("context_id"),
                             "label": f"知识收缩上下文 · {context.get('decision_node', 'unknown')}", "valid_until": context.get("valid_until")})
    for brief in run.landscape_briefs:
        if brief.get("created_at"):
            timeline.append({"at": brief["created_at"], "kind": "landscape_brief", "id": brief.get("brief_id") or brief.get("artifact_id") or brief["created_at"],
                             "label": f"证据景观简报 · {brief.get('disposition', 'UNSPECIFIED')}", "immutable": brief.get("immutable") is True})
    if run.concept_map.get("created_at"):
        timeline.append({"at": run.concept_map["created_at"], "kind": "concept_map", "id": run.concept_map.get("map_id"),
                         "label": f"知识概念图 · {run.concept_map.get('scope', 'unknown')}", "status": run.concept_map.get("status", "UNSPECIFIED")})
    if run.opportunity_map.get("created_at"):
        timeline.append({"at": run.opportunity_map["created_at"], "kind": "opportunity_map", "id": run.opportunity_map.get("map_id"),
                         "label": f"现实机会图 · {run.opportunity_map.get('scope', 'unknown')}", "valid_until": run.opportunity_map.get("valid_until")})
    timeline.sort(key=lambda item: str(item["at"]))
    return {"schema_version": "0.1", "projection": "derived-read-only", "run": run_id,
            "diagnostics": run.gaps, "timeline": timeline, "nodes": nodes, "edges": edges}
