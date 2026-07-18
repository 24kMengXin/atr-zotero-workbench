"""Read-only adapters that turn ATR evidence into a traceable graph projection."""
from __future__ import annotations

import json
import sqlite3
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


@dataclass
class V2Run:
    """Read-only ATR v2 projection input.

    `atr.sqlite` is authoritative; state.json/events.jsonl are deliberately
    not used as input because v2 declares them rebuildable exports.
    """
    path: Path
    run_id: str
    subjects: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]
    events: list[dict[str, Any]]
    attachments: list[dict[str, Any]]
    gaps: list[str]


def load_v2_run(path: Path) -> V2Run:
    database = path / "atr.sqlite"
    if not database.is_file():
        raise ValueError(f"Not an ATR v2 run: missing {database}")
    conn = sqlite3.connect(database)
    conn.row_factory = sqlite3.Row
    try:
        meta = {row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM meta")}
        subjects = [dict(row) for row in conn.execute("SELECT subject_id,kind,state,version,active,created_at,updated_at FROM subjects ORDER BY subject_id")]
        artifacts = [dict(row) for row in conn.execute("SELECT artifact_id,digest,kind,original_name,created_at,metadata_json FROM artifacts ORDER BY created_at,artifact_id")]
        events = [dict(row) for row in conn.execute("SELECT seq,event_id,subject_id,from_state,to_state,expected_version,artifact_id,review_mode,note,created_at FROM events ORDER BY seq")]
        attachments = [dict(row) for row in conn.execute("SELECT seq,attachment_id,subject_id,subject_version,artifact_id,role,note,created_at FROM attachments ORDER BY seq")]
    finally:
        conn.close()
    for artifact in artifacts:
        body_dir = path / "artifacts" / artifact["digest"]
        bodies = list(body_dir.glob("body.*")) if body_dir.is_dir() else []
        artifact["payload"] = {}
        # JSON is a readable artifact body, never a second authority.  We only
        # project it when the registered immutable body itself declares JSON.
        if len(bodies) == 1 and bodies[0].suffix.lower() == ".json":
            try:
                parsed = json.loads(bodies[0].read_text(encoding="utf-8"))
                if isinstance(parsed, dict):
                    artifact["payload"] = parsed
            except (OSError, json.JSONDecodeError):
                artifact["payload"] = {"_projection_error": "registered JSON artifact cannot be read"}
    gaps = []
    if len([item for item in subjects if item.get("active")]) != 1:
        gaps.append("ATR v2 run 必须恰有一个 active subject；当前 SQLite 投影不满足该约束")
    return V2Run(path, meta.get("run_id", path.name), subjects, artifacts, events, attachments, gaps)


def load_legacy_run(path: Path) -> LegacyRun | V2Run:
    if (path / "atr.sqlite").is_file():
        return load_v2_run(path)
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


def project_v2_graph(run: V2Run) -> dict[str, Any]:
    """Project v2's SQLite authority without treating its exports as input."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    def edge(source: str, target: str, relation: str, **data: Any) -> None:
        if not any(item["source"] == source and item["target"] == target and item["relation"] == relation for item in edges):
            edges.append({"source": source, "target": target, "relation": relation, "data": data})

    def ensure_node(node_id: str, kind: str, label: str, **data: Any) -> str:
        existing = next((item for item in nodes if item["id"] == node_id), None)
        if existing:
            for key, value in data.items():
                if value not in (None, "", [], {}) and not existing["data"].get(key):
                    existing["data"][key] = value
            return node_id
        nodes.append(_node(node_id, kind, label, **data))
        return node_id

    active = next((subject for subject in run.subjects if subject.get("active")), None)
    nodes.append(_node(f"run:{run.run_id}", "run", run.run_id, controller="ATR v2 SQLite", active_subject_id=active.get("subject_id") if active else None, stage=active.get("state") if active else None, gaps=run.gaps))
    for subject in run.subjects:
        node_id = f"subject:{subject['subject_id']}"
        subject_data = dict(subject)
        subject_data["subject_kind"] = subject_data.pop("kind")
        nodes.append(_node(node_id, "atr_v2_subject", subject["subject_id"], **subject_data))
        edge(f"run:{run.run_id}", node_id, "tracks_subject")
    known_artifacts: set[str] = set()
    known_sources: set[str] = set()
    projected_source_nodes: dict[str, dict[str, Any]] = {}

    def entity_key(artifact: dict[str, Any]) -> tuple[str, str] | None:
        payload = artifact.get("payload", {})
        kind = str(payload.get("artifact_type") or artifact.get("kind") or "")
        if kind == "knowledge-map":
            return kind, str(payload.get("map_id") or artifact["artifact_id"])
        if kind == "opportunity-map":
            return kind, str(payload.get("map_id") or artifact["artifact_id"])
        if kind == "problem-case":
            return kind, str(payload.get("problem_id") or artifact["artifact_id"])
        return None

    latest_artifact: dict[tuple[str, str], dict[str, Any]] = {}
    for candidate in run.artifacts:
        key = entity_key(candidate)
        if key and (key not in latest_artifact or (
            str(candidate.get("created_at", "")), candidate["artifact_id"]
        ) > (
            str(latest_artifact[key].get("created_at", "")), latest_artifact[key]["artifact_id"]
        )):
            latest_artifact[key] = candidate

    def versioned(base: str, artifact: dict[str, Any]) -> tuple[str, bool]:
        key = entity_key(artifact)
        historical = bool(key and latest_artifact.get(key, {}).get("artifact_id") != artifact["artifact_id"])
        suffix = "@" + artifact["digest"][:12] if historical else ""
        return base + suffix, historical

    def source_node(source: dict[str, Any], *, provenance: str) -> str | None:
        source_id = source.get("source_id")
        if not source_id:
            return None
        source_id = str(source_id)
        node_id = f"paper:{source_id}"
        recorded_fulltext_state = str(source.get("fulltext_state") or "")
        worker_inspection_state = source.get("worker_inspection_state") or (
            "FULLTEXT_INSPECTED" if "INSPECTED" in recorded_fulltext_state
            else "NOT_RECORDED"
        )
        human_inspection_state = source.get("human_inspection_state") or "NOT_RECORDED"
        if source_id not in known_sources:
            known_sources.add(source_id)
            kind = str(source.get("kind") or source.get("source_kind") or "UNSPECIFIED")
            layer = _source_layer(kind, source.get("source_layer"))
            paper_node = _node(node_id, "paper", str(source.get("title") or source_id), source_id=source_id,
                               doi=source.get("doi", ""), url=source.get("url", ""), pdf_url=source.get("pdf_url", ""),
                               access_status=source.get("access_status", ""), access_route=source.get("access_route", ""),
                               content_form=source.get("content_form", ""),
                               fulltext_state=recorded_fulltext_state,
                               worker_inspection_state=worker_inspection_state,
                               human_inspection_state=human_inspection_state,
                               content_digest=source.get("content_digest", ""),
                               inspection_spans=source.get("inspection_spans", []),
                               zotero_item_key=source.get("zotero_item_key"),
                               zotero_attachment_key=source.get("zotero_attachment_key"),
                               zotero_attachment_state=source.get("zotero_attachment_state", ""),
                               zotero_snapshot_state=source.get("zotero_snapshot_state", ""),
                               local_cache_state=source.get("local_cache_state", ""),
                               local_cache_path=source.get("local_cache_path", ""),
                               cache_role=source.get("cache_role", ""),
                               identity_state=source.get("identity_state", ""),
                               identity_evidence=source.get("identity_evidence", []),
                               identity_review=source.get("identity_review", ""),
                               local_cache_import_policy=source.get("local_cache_import_policy", ""),
                               source_kind=kind, source_layer=layer,
                               locator=source.get("locator", ""), provenance=provenance,
                               source_function=source.get("source_function"), observed_at=source.get("observed_at"),
                               supports=source.get("supports", source.get("claim", source.get("observation", ""))),
                               does_not_support=source.get("does_not_support", source.get("does_not_establish", "")),
                               does_not_establish=source.get("does_not_establish", ""))
            nodes.append(paper_node)
            projected_source_nodes[source_id] = paper_node
            nodes.append(_node(f"evidence:{source_id}", "evidence_boundary", f"{source_id} 的证据边界",
                               supports=source.get("supports", source.get("claim", "")),
                               does_not_support=source.get("does_not_support", source.get("does_not_establish", ""))))
            edge(node_id, f"evidence:{source_id}", "states_boundary")
        else:
            # One bibliographic source can occur in several immutable artifact
            # versions.  Preserve those artifact/edge histories, while allowing
            # the shared Zotero source node to gain a non-interpretive locator
            # that an earlier record did not yet know.
            paper_data = projected_source_nodes[source_id]["data"]
            for field in (
                "doi", "url", "pdf_url", "access_status", "access_route",
                "content_form", "fulltext_state", "content_digest",
                "worker_inspection_state", "human_inspection_state",
                "zotero_item_key", "zotero_attachment_key",
                "zotero_attachment_state", "zotero_snapshot_state",
                "local_cache_state", "local_cache_path",
                "cache_role", "identity_state", "identity_evidence", "identity_review",
                "local_cache_import_policy",
            ):
                if not paper_data.get(field) and source.get(field):
                    paper_data[field] = source[field]
            if (paper_data.get("worker_inspection_state") in {None, "", "NOT_RECORDED"}
                    and worker_inspection_state != "NOT_RECORDED"):
                paper_data["worker_inspection_state"] = worker_inspection_state
            if (paper_data.get("human_inspection_state") in {None, "", "NOT_RECORDED"}
                    and source.get("human_inspection_state") not in {None, "", "NOT_RECORDED"}):
                paper_data["human_inspection_state"] = source["human_inspection_state"]
            if source.get("inspection_spans"):
                existing = paper_data.setdefault("inspection_spans", [])
                for span in source["inspection_spans"]:
                    if span not in existing:
                        existing.append(span)
        return node_id
    for artifact in run.artifacts:
        artifact_id = artifact["artifact_id"]
        known_artifacts.add(artifact_id)
        metadata = json.loads(artifact["metadata_json"]) if artifact.get("metadata_json") else {}
        payload = artifact.get("payload", {})
        nodes.append(_node(f"artifact:{artifact_id}", "atr_v2_artifact", f"{artifact['kind']} · {artifact_id.removeprefix('sha256:')[:12]}", artifact_id=artifact_id, artifact_kind=artifact["kind"], digest=artifact["digest"], original_name=artifact["original_name"], created_at=artifact["created_at"], metadata=metadata, artifact_type=payload.get("artifact_type"), projection_error=payload.get("_projection_error")))
        edge(f"run:{run.run_id}", f"artifact:{artifact_id}", "registers_immutable_artifact")
        artifact_type = str(payload.get("artifact_type") or artifact.get("kind") or "")
        if artifact_type == "portfolio-intake":
            portfolio_id = str(payload.get("portfolio_id") or run.run_id)
            portfolio_node = ensure_node(
                f"portfolio:{portfolio_id}", "research_portfolio",
                str(payload.get("question") or portfolio_id), portfolio_id=portfolio_id,
                controller_boundary=payload.get("controller_boundary", ""), artifact_id=artifact_id,
            )
            edge(f"artifact:{artifact_id}", portfolio_node, "materializes_portfolio_intake")
            for child in payload.get("children", []):
                if not isinstance(child, dict) or not child.get("program_key"):
                    continue
                key = str(child["program_key"])
                child_node = ensure_node(
                    f"research_program:{key}", "research_program", key,
                    program_key=key, child_run_id=child.get("run_id"),
                    subject_id=child.get("subject_id"), relationship=child.get("relationship"),
                    lifecycle_state="SEPARATE_AUTHORITY_INTAKE",
                )
                edge(portfolio_node, child_node, "registers_separate_program_authority")
        if artifact_type == "program-registry":
            portfolio_id = str(payload.get("portfolio_id") or "multilingual-aaai-program-portfolio")
            portfolio_node = ensure_node(f"portfolio:{portfolio_id}", "research_portfolio", portfolio_id, portfolio_id=portfolio_id)
            edge(f"artifact:{artifact_id}", portfolio_node, "registers_program_children")
            for child in payload.get("children", []):
                if not isinstance(child, dict) or not child.get("program_key"):
                    continue
                key = str(child["program_key"])
                child_node = ensure_node(f"research_program:{key}", "research_program", key,
                                         program_key=key, child_run_id=child.get("run_id"), subject_id=child.get("subject_id"))
                edge(portfolio_node, child_node, "registers_separate_program_authority")
        if artifact_type == "portfolio-route-map":
            portfolio_id = str(payload.get("portfolio_id") or "multilingual-aaai-program-portfolio")
            portfolio_node = ensure_node(
                f"portfolio:{portfolio_id}", "research_portfolio", portfolio_id,
                portfolio_id=portfolio_id, history_policy=payload.get("history_policy"),
            )
            edge(f"artifact:{artifact_id}", portfolio_node, "materializes_portfolio_route_map")
            for program in payload.get("programs", []):
                if not isinstance(program, dict) or not program.get("program_key"):
                    continue
                key = str(program["program_key"])
                program_node = ensure_node(
                    f"research_program:{key}", "research_program",
                    str(program.get("label") or key), program_key=key,
                    child_run_id=program.get("child_run_id"),
                    legacy_branch_count=len(program.get("branches", [])),
                )
                edge(portfolio_node, program_node, "registers_separate_program_authority")
                for branch in program.get("branches", []):
                    if not isinstance(branch, dict) or not branch.get("run"):
                        continue
                    legacy_id = str(branch["run"])
                    legacy_node = ensure_node(
                        f"legacy_run:{legacy_id}", "legacy_research_run", legacy_id,
                        recorded_stage=branch.get("recorded_stage"),
                        alignment_disposition=branch.get("alignment_disposition"),
                        integration_action=branch.get("integration_action"),
                        source_count=branch.get("source_count", 0),
                        claim_count=branch.get("claim_count", 0),
                        missing_for_current=branch.get("missing_for_current", []),
                    )
                    edge(program_node, legacy_node, "retains_legacy_branch_as_input")
        if artifact_type == "portfolio-review-summary":
            portfolio_id = str(payload.get("portfolio_id") or "multilingual-aaai-program-portfolio")
            portfolio_node = ensure_node(
                f"portfolio:{portfolio_id}", "research_portfolio", portfolio_id,
                portfolio_id=portfolio_id,
                posterior_review_summary=payload.get("summary", {}),
                posterior_review_boundary=payload.get("does_not_authorize", ""),
            )
            edge(f"artifact:{artifact_id}", portfolio_node, "materializes_portfolio_review_summary")
            for row in payload.get("programs", []):
                if not isinstance(row, dict) or not row.get("program_key"):
                    continue
                key = str(row["program_key"])
                program_node = ensure_node(
                    f"research_program:{key}", "research_program", key,
                    program_key=key,
                    posterior_disposition=row.get("disposition"),
                    posterior_status=row.get("status"),
                    surviving_boundary=row.get("surviving_boundary", ""),
                    next_evidence=row.get("next_evidence", []),
                    collision_review_artifact_id=row.get("collision_review_artifact_id"),
                    owner_review_status="PENDING_HUMAN_OWNER_REVIEW",
                    owner_review_boundary="Portfolio summary is navigation only; the owner input must be recorded in the child collision-review Note.",
                )
                edge(portfolio_node, program_node, "summarizes_child_collision_review")
        if artifact_type == "frontier-map":
            program_key = str(payload.get("domain") or run.run_id)
            program_node = ensure_node(
                f"research_program:{program_key}", "research_program", program_key,
                program_key=program_key,
            )
            edge(f"artifact:{artifact_id}", program_node, "frames_program_frontier")
            for tension in payload.get("frontier_tensions", []):
                if not isinstance(tension, dict) or not tension.get("tension_id"):
                    continue
                tension_id = str(tension["tension_id"])
                question_node = ensure_node(
                    f"research_question:{tension_id}", "research_question",
                    str(tension.get("question") or tension_id), tension_id=tension_id,
                    explanations=tension.get("competing_explanations", []),
                    dimensions=tension.get("dimensions", []), freshness=tension.get("freshness"),
                    review_status=payload.get("verification_status", "PENDING_SOURCE_REVIEW"),
                    does_not_establish=tension.get("does_not_establish") or payload.get("evidence_boundary"),
                    artifact_id=artifact_id,
                )
                edge(program_node, question_node, "frames_frontier_question")
                for source_id in tension.get("anchor_source_ids", []):
                    if str(source_id) in known_sources:
                        edge(question_node, f"paper:{source_id}", "anchors_pending_source_verification")
        if artifact_type == "topic-routing-package":
            package_id = str(payload.get("package_id") or artifact_id)
            topic_node = ensure_node(
                f"topic_route:{package_id}", "topic_route_draft",
                str(payload.get("topic") or package_id), package_id=package_id,
                selected_track=payload.get("selected_track"), next_stage=payload.get("next_stage"),
                rationale=payload.get("rationale"), valid_until=payload.get("valid_until"),
                review_status="PENDING_INDEPENDENT_TOPIC_ROUTE_REVIEW",
                does_not_establish="A structurally valid draft does not authorize a controller transition.",
                artifact_id=artifact_id,
            )
            edge(f"artifact:{artifact_id}", topic_node, "materializes_pending_topic_route")
            active_program = next((
                node["id"] for node in nodes
                if node.get("kind") == "research_program"
            ), None)
            if active_program:
                edge(active_program, topic_node, "awaits_independent_topic_route_review")
        if artifact_type == "program-intake":
            key = str(payload.get("program_key") or run.run_id)
            program_node = ensure_node(
                f"research_program:{key}", "research_program",
                str(payload.get("label") or key), program_key=key,
                root_question=payload.get("root_question", ""), parent_portfolio_run=payload.get("parent_portfolio_run"),
                initial_state=payload.get("initial_state"), next_legal_work=payload.get("next_legal_work"),
                language_axis_binding_required=payload.get("language_axis_binding_required"),
                controller_boundary=payload.get("controller_boundary", ""), artifact_id=artifact_id,
            )
            edge(f"artifact:{artifact_id}", program_node, "materializes_program_intake")
        if artifact_type == "legacy-branch-index":
            key = str(payload.get("program_key") or run.run_id)
            program_node = ensure_node(f"research_program:{key}", "research_program", key, program_key=key)
            edge(f"artifact:{artifact_id}", program_node, "indexes_legacy_branches")
            for branch in payload.get("branches", []):
                if not isinstance(branch, dict) or not branch.get("run"):
                    continue
                legacy_id = str(branch["run"])
                legacy_node = ensure_node(
                    f"legacy_run:{legacy_id}", "legacy_research_run", legacy_id,
                    historical_path=branch.get("path"), catalog_role=branch.get("catalog_role"),
                    catalog_disposition=branch.get("catalog_disposition"),
                    alignment_disposition=branch.get("alignment_disposition"),
                    integration_action=branch.get("integration_action"),
                    source_count=branch.get("sources", 0), claim_count=branch.get("claims", 0),
                    reusable=branch.get("reusable", []), missing_for_current=branch.get("missing_for_current", []),
                )
                edge(program_node, legacy_node, "retains_legacy_branch_as_input")
        if artifact_type in {"legacy-mapping-index", "legacy-program-mapping-index"}:
            program_key = payload.get("program_key")
            mapping_id = str(payload.get("mapping_id") or artifact_id)
            scope = str(program_key or "portfolio")
            mapping_node = ensure_node(
                f"legacy_mapping:{mapping_id}:{scope}", "legacy_mapping_audit",
                "逐项历史消费映射 · " + scope,
                mapping_id=mapping_id, program_key=program_key,
                current_run_id=payload.get("current_run_id"),
                summary=payload.get("summary", {}), policy=payload.get("policy", ""),
                conformance="LEGACY_MAPPED", artifact_id=artifact_id,
            )
            edge(f"artifact:{artifact_id}", mapping_node, "materializes_exact_legacy_consumption")
            if program_key:
                program_node = ensure_node(
                    f"research_program:{program_key}", "research_program", str(program_key),
                    program_key=program_key,
                )
                edge(program_node, mapping_node, "declares_legacy_consumption_boundary")
            manifests_by_run: dict[str, list[dict[str, Any]]] = {}
            for row in payload.get("manifests", []):
                if isinstance(row, dict) and row.get("run_id"):
                    manifests_by_run.setdefault(str(row["run_id"]), []).append(row)
            for legacy_id, rows in sorted(manifests_by_run.items()):
                decisions = sorted({str(row.get("decision")) for row in rows if row.get("decision")})
                legacy_node = ensure_node(
                    f"legacy_run:{legacy_id}", "legacy_research_run", legacy_id,
                    mapped_artifact_count=len(rows), legacy_mapping_status="LEGACY_MAPPED",
                    mapped_decisions=decisions, mapping_id=mapping_id,
                    mapping_boundary="Byte-level sidecars record only declared consumption; they do not promote legacy interpretations or lifecycle state.",
                )
                legacy_record = next(item for item in nodes if item["id"] == legacy_node)
                legacy_record["data"]["missing_for_current"] = [
                    gap for gap in legacy_record["data"].get("missing_for_current", [])
                    if gap != "no LEGACY_MAPPED artifact manifests"
                ]
                edge(mapping_node, legacy_node, "maps_exact_consumed_artifacts", manifest_count=len(rows))
        if artifact_type == "historical-alignment-summary":
            audit_node = ensure_node(
                f"alignment_audit:{payload.get('audit_digest', artifact_id)}", "historical_alignment_audit",
                "历史归位审计", audit_digest=payload.get("audit_digest"), summary=payload.get("summary", {}),
                disposition=payload.get("disposition"), source_boundary=payload.get("source_boundary"),
            )
            edge(f"artifact:{artifact_id}", audit_node, "materializes_alignment_boundary")
        # Knowledge artifacts must carry their own source metadata.  A source
        # ID alone is not enough to invent a Zotero/document edge.
        for source in payload.get("sources", []):
            if isinstance(source, dict):
                node_id = source_node(source, provenance=artifact_id)
                if node_id:
                    edge(f"artifact:{artifact_id}", node_id, "records_explicit_source")
        if artifact["kind"] == "opportunity-decision" or payload.get("artifact_type") == "opportunity-decision":
            decision_id = str(payload.get("decision_id") or artifact_id)
            gap_node = f"reality_signal_gap:{decision_id}"
            nodes.append(_node(
                gap_node, "reality_signal_gap",
                "现实信号不足 · " + str(payload.get("decision") or "UNSPECIFIED"),
                decision_id=decision_id, decision=payload.get("decision"),
                searched_through=payload.get("searched_through"), reason=payload.get("reason", ""),
                missing_source_function=payload.get("missing_source_function", ""),
                next_legal_work=payload.get("next_legal_work", ""),
                does_not_establish=payload.get("does_not_establish", ""),
                controller_boundary=payload.get("controller_boundary", ""),
                artifact_id=artifact_id,
            ))
            edge(f"artifact:{artifact_id}", gap_node, "materializes_reality_signal_gap")
        if artifact["kind"] == "collision-review" or payload.get("artifact_type") == "collision-review":
            review_id = str(payload.get("artifact_id") or artifact_id)
            review_node = f"collision_review:{review_id}"
            nodes.append(_node(
                review_node, "collision_review",
                f"碰撞复核 · {payload.get('disposition', 'UNSPECIFIED')}",
                review_id=review_id,
                input_problem_case_id=payload.get("input_problem_case_id"),
                status=payload.get("status"), disposition=payload.get("disposition"),
                comparisons=payload.get("comparisons", {}),
                coverage_limits=payload.get("coverage_limits", []),
                surviving_boundary=payload.get("surviving_boundary", ""),
                alternative_explanations=payload.get("alternative_explanations", []),
                next_evidence=payload.get("next_evidence", []),
                does_not_authorize=payload.get("does_not_authorize", ""),
                artifact_id=artifact_id,
            ))
            edge(f"artifact:{artifact_id}", review_node, "materializes_collision_review")
            problem_id = payload.get("input_problem_case_id")
            if problem_id:
                edge(f"research_problem:{problem_id}", review_node, "is_claim_scoped_reviewed_by")
            for inspected in payload.get("inspected_sources", []):
                if not isinstance(inspected, dict):
                    continue
                source_id = source_node(inspected, provenance=artifact_id)
                if source_id:
                    edge(review_node, source_id, "inspects_for_collision",
                         locator=inspected.get("locator", ""),
                         comparison_type=inspected.get("comparison_type", ""),
                         finding=inspected.get("finding", ""),
                         does_not_establish=inspected.get("does_not_establish", ""))
        if artifact["kind"] == "knowledge-map" or payload.get("artifact_type") == "knowledge-map":
            map_id = str(payload.get("map_id") or artifact_id)
            map_node, historical = versioned(f"knowledge_map:{map_id}", artifact)
            nodes.append(_node(map_node, "concept_map", str(payload.get("topic") or payload.get("scope") or map_id), map_id=map_id, schema_version=payload.get("schema_version"), map_review_status=payload.get("map_review_status", "LEGACY_SOURCE_IDS_ONLY"), definition=payload.get("definition", ""), does_not_establish=payload.get("does_not_establish", ""), artifact_id=artifact_id, historical_version=historical))
            edge(f"artifact:{artifact_id}", map_node, "materializes_knowledge_map")
            if historical:
                edge(map_node, f"knowledge_map:{map_id}", "superseded_by_knowledge_map_version")
            concepts = [item for item in payload.get("concepts", []) if isinstance(item, dict) and item.get("concept_id")]
            concept_ids = {str(item["concept_id"]) for item in concepts}
            latest_concept_ids = {
                str(item["concept_id"])
                for item in latest_artifact[("knowledge-map", map_id)].get("payload", {}).get("concepts", [])
                if isinstance(item, dict) and item.get("concept_id")
            }
            for concept in concepts:
                concept_id = str(concept["concept_id"])
                concept_node, _ = versioned(f"knowledge_concept:{map_id}:{concept_id}", artifact)
                nodes.append(_node(concept_node, "knowledge_concept", str(concept.get("label") or concept_id), concept_id=concept_id, map_id=map_id, definition=concept.get("definition", ""), source_ids=concept.get("source_ids", []), review_status=concept.get("review_status", "PENDING_SOURCE_REVIEW"), evidence_spans=concept.get("evidence_spans", []), does_not_establish=concept.get("does_not_establish", ""), depth=concept.get("depth"), artifact_id=artifact_id, historical_version=historical))
                parent = concept.get("parent_id")
                parent_node = versioned(f"knowledge_concept:{map_id}:{parent}", artifact)[0] if str(parent) in concept_ids else map_node
                edge(parent_node, concept_node, "specializes_concept" if str(parent) in concept_ids else "roots_concept")
                if historical and concept_id in latest_concept_ids:
                    edge(concept_node, f"knowledge_concept:{map_id}:{concept_id}", "superseded_by_knowledge_map_version")
                for source_id in concept.get("source_ids", []):
                    if str(source_id) in known_sources:
                        edge(concept_node, f"paper:{source_id}", "defines_with_explicit_source")
        if artifact["kind"] == "opportunity-map" or payload.get("artifact_type") == "opportunity-map":
            map_id = str(payload.get("map_id") or artifact_id)
            map_node, historical = versioned(f"opportunity_map:{map_id}", artifact)
            nodes.append(_node(map_node, "opportunity_map", str(payload.get("scope") or map_id),
                               map_id=map_id, searched_through=payload.get("searched_through"),
                               created_at=payload.get("created_at"), valid_until=payload.get("valid_until"),
                               does_not_establish=payload.get("does_not_establish", ""),
                               artifact_id=artifact_id, historical_version=historical))
            edge(f"artifact:{artifact_id}", map_node, "materializes_opportunity_map")
            if historical:
                edge(map_node, f"opportunity_map:{map_id}", "superseded_by_opportunity_map_version")
            latest_tension_ids = {
                str(item["tension_id"])
                for item in latest_artifact[("opportunity-map", map_id)].get("payload", {}).get("tension_clusters", [])
                if isinstance(item, dict) and item.get("tension_id")
            }
            for tension in payload.get("tension_clusters", []):
                if not isinstance(tension, dict) or not tension.get("tension_id"):
                    continue
                tension_id = str(tension["tension_id"])
                tension_node, _ = versioned(f"real_world_tension:{tension_id}", artifact)
                nodes.append(_node(
                    tension_node, "real_world_tension", str(tension.get("label") or tension_id),
                    tension_id=tension_id, actor=tension.get("actor"),
                    incumbent_practice=tension.get("incumbent_practice"),
                    material_consequence=tension.get("material_consequence"),
                    candidate_construct=tension.get("candidate_construct"),
                    alternative_explanations=tension.get("alternative_explanations", []),
                    translation_status=tension.get("translation_status"),
                    does_not_establish=tension.get("does_not_establish", ""),
                    artifact_id=artifact_id, historical_version=historical,
                ))
                edge(map_node, tension_node, "clusters_real_world_tension")
                if historical and tension_id in latest_tension_ids:
                    edge(tension_node, f"real_world_tension:{tension_id}", "superseded_by_opportunity_map_version")
                for source_id in tension.get("source_ids", []):
                    if str(source_id) in known_sources:
                        edge(tension_node, f"paper:{source_id}", "grounded_in_explicit_signal")
        if artifact["kind"] == "problem-case" or payload.get("artifact_type") == "problem-case":
            problem_id = str(payload.get("problem_id") or artifact_id)
            label = str(payload.get("research_question") or payload.get("tension") or payload.get("question") or problem_id)
            problem_node, historical = versioned(f"research_problem:{problem_id}", artifact)
            nodes.append(_node(problem_node, "research_problem", label, problem_id=problem_id,
                               decision_owner=payload.get("decision_owner"), worlds=payload.get("worlds", payload.get("counterfactual_worlds", [])),
                               discriminator=payload.get("discriminator", ""), falsifier=payload.get("falsifier", ""),
                               scope=payload.get("scope", ""), does_not_establish=payload.get("does_not_establish", ""),
                               artifact_id=artifact_id, historical_version=historical))
            edge(f"artifact:{artifact_id}", problem_node, "materializes_problem_case")
            if historical:
                edge(problem_node, f"research_problem:{problem_id}", "superseded_by_recorded_problem_version")
            supersedes_problem_id = payload.get("supersedes_problem_id")
            if supersedes_problem_id and str(supersedes_problem_id) != problem_id:
                edge(f"research_problem:{supersedes_problem_id}", problem_node,
                     "superseded_by_recorded_problem_version")
            for span in payload.get("source_spans", []):
                if isinstance(span, dict):
                    node_id = source_node(span, provenance=artifact_id)
                    if node_id:
                        edge(problem_node, node_id, "grounds_in_explicit_source_span",
                             locator=span.get("locator", ""), observation=span.get("observation", ""),
                             problem_posture=span.get("problem_posture"), resolves=span.get("resolves", ""),
                             leaves_unresolved=span.get("leaves_unresolved", ""),
                             does_not_establish=span.get("does_not_establish", ""))
            declared_problem_sources = {
                str(span.get("source_id")) for span in payload.get("source_spans", [])
                if isinstance(span, dict) and span.get("source_id")
            }
            for question in payload.get("derived_questions", []):
                if not isinstance(question, dict) or not question.get("question_id"):
                    continue
                question_id = str(question["question_id"])
                question_node, _ = versioned(f"derived_question:{problem_id}:{question_id}", artifact)
                nodes.append(_node(
                    question_node, "derived_research_question",
                    str(question.get("question") or question_id), question_id=question_id,
                    status=question.get("status", "REVIEW_TASK"),
                    smallest_discriminator=question.get("smallest_discriminator", ""),
                    does_not_establish=question.get("does_not_establish", ""),
                    parent_problem_id=problem_id,
                    artifact_id=artifact_id, historical_version=historical,
                ))
                edge(problem_node, question_node, "generates_finer_review_question")
                for source_id in question.get("source_ids", []):
                    if str(source_id) in declared_problem_sources and str(source_id) in known_sources:
                        edge(question_node, f"paper:{source_id}", "cites_explicit_source")
    # Some opportunity decisions precede the artifact that contributes the
    # bibliographic metadata for a searched source. Resolve these edges only
    # after every immutable artifact has had a chance to register its sources.
    for artifact in run.artifacts:
        payload = artifact.get("payload", {})
        if payload.get("artifact_type") != "opportunity-decision":
            continue
        decision_id = str(payload.get("decision_id") or artifact["artifact_id"])
        for source_id in payload.get("source_ids", []):
            if str(source_id) in known_sources:
                edge(f"reality_signal_gap:{decision_id}", f"paper:{source_id}",
                     "searched_for_admissible_reality_signal_in")
    timeline: list[dict[str, Any]] = []
    for event in run.events:
        node_id = f"transition:{event['event_id']}"
        nodes.append(_node(node_id, "atr_v2_transition", f"{event.get('from_state') or '∅'} → {event['to_state']}", **event))
        edge(f"subject:{event['subject_id']}", node_id, "records_transition")
        if event["artifact_id"] in known_artifacts:
            edge(node_id, f"artifact:{event['artifact_id']}", "authorized_by_immutable_artifact")
        timeline.append({"at": event["created_at"], "kind": "atr_v2_transition", "id": event["event_id"], "label": f"{event.get('from_state') or '∅'} → {event['to_state']}", "review_mode": event["review_mode"], "artifact_ids": [event["artifact_id"]]})
    for attachment in run.attachments:
        node_id = f"attachment:{attachment['attachment_id']}"
        nodes.append(_node(node_id, "atr_v2_attachment", f"{attachment['role']} · v{attachment['subject_version']}", **attachment))
        edge(f"subject:{attachment['subject_id']}", node_id, "attaches_evidence_without_transition")
        if attachment["artifact_id"] in known_artifacts:
            edge(node_id, f"artifact:{attachment['artifact_id']}", "attaches_immutable_artifact")
        timeline.append({"at": attachment["created_at"], "kind": "atr_v2_attachment", "id": attachment["attachment_id"], "label": f"附件 · {attachment['role']}（不改变 lifecycle）", "artifact_ids": [attachment["artifact_id"]]})
    for artifact in run.artifacts:
        payload = artifact.get("payload", {})
        if payload.get("artifact_type") != "human-review-disposition":
            continue
        disposition_id = str(payload.get("disposition_id") or artifact["artifact_id"])
        node_id = f"human_review:{disposition_id}"
        nodes.append(_node(node_id, "human_review_disposition", f"人类反馈处置 · {payload.get('disposition', 'UNSPECIFIED')}", decision_id=disposition_id, packet_id=payload.get("packet_id"), owner=payload.get("owner"), disposition=payload.get("disposition"), rationale=payload.get("rationale"), controller_boundary=payload.get("controller_boundary"), v2_artifact_id=artifact["artifact_id"]))
        edge(f"artifact:{artifact['artifact_id']}", node_id, "materializes_human_review_disposition")
        target = payload.get("review", {})
        source_id = target.get("source_id")
        if source_id in known_sources:
            edge(node_id, f"paper:{source_id}", "disposes_review_of_source")
        for problem in payload.get("impact", {}).get("all_affected_research_problems", []):
            problem_id = problem.get("problem_id") if isinstance(problem, dict) else None
            if problem_id and any(node["id"] == f"research_problem:{problem_id}" for node in nodes):
                edge(node_id, f"research_problem:{problem_id}", "requests_reconsideration_of_problem")
    for artifact in run.artifacts:
        payload = artifact.get("payload", {})
        if payload.get("artifact_type") != "human-review-assessment":
            continue
        assessment_id = str(payload.get("assessment_id") or artifact["artifact_id"])
        node_id = f"human_review_assessment:{assessment_id}"
        nodes.append(_node(
            node_id, "human_review_assessment",
            f"共创复核 · {payload.get('outcome', 'UNSPECIFIED')}",
            assessment_id=assessment_id, packet_id=payload.get("packet_id"),
            disposition_id=payload.get("disposition_id"), reviewed_at=payload.get("reviewed_at"),
            reviewer=payload.get("reviewer", {}), finding=payload.get("finding", ""),
            outcome=payload.get("outcome"), evidence_basis=payload.get("evidence_basis", []),
            impact=payload.get("impact", {}),
            required_followup_artifact_kind=payload.get("required_followup_artifact_kind"),
            controller_boundary=payload.get("controller_boundary"),
            v2_artifact_id=artifact["artifact_id"],
        ))
        edge(f"artifact:{artifact['artifact_id']}", node_id, "materializes_isolated_human_review_assessment")
        disposition_node = f"human_review:{payload.get('disposition_id')}"
        if any(node["id"] == disposition_node for node in nodes):
            edge(disposition_node, node_id, "reviewed_by_isolated_assessment")
        impact = payload.get("impact", {})
        for target in impact.get("preserve_object_ids", []):
            if any(node["id"] == str(target) for node in nodes):
                edge(node_id, str(target), "preserves_object_after_review")
        for target in impact.get("reconsider_object_ids", []):
            if any(node["id"] == str(target) for node in nodes):
                edge(node_id, str(target), "requests_new_version_after_review")
    timeline.sort(key=lambda item: str(item["at"]))
    return {"schema_version": "0.2", "projection": "derived-read-only-v2-sqlite", "run": run.run_id, "diagnostics": run.gaps, "timeline": timeline, "nodes": nodes, "edges": edges}


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


def project_graph(run: LegacyRun | V2Run) -> dict[str, Any]:
    if isinstance(run, V2Run):
        return project_v2_graph(run)
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
                           url=source.get("url", ""), pdf_url=source.get("pdf_url", ""),
                           source_kind=source_kind, source_layer=source_layer,
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
        # A problem can explicitly decompose into smaller review questions.
        # These are navigation/review nodes, never inferred candidates or claims.
        for child in problem.get("derived_questions", []):
            child_id = str(child.get("question_id", "unknown"))
            child_node = f"derived_question:{problem_id}:{child_id}"
            nodes.append(_node(child_node, "derived_research_question", child.get("question", child_id),
                               question_id=child_id, status=child.get("status", "PENDING_REVIEW"),
                               smallest_discriminator=child.get("smallest_discriminator"),
                               does_not_establish=child.get("does_not_establish"), parent_problem_id=problem_id))
            edge(problem_node, child_node, "generates_finer_review_question")
            for source_id in child.get("source_ids", []):
                if source_id in known_paper_ids:
                    edge(child_node, f"paper:{source_id}", "grounds_in_explicit_source")
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
