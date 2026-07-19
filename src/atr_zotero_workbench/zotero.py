"""Safe Zotero export and opt-in Web API writer. No local database access."""
from __future__ import annotations

import hashlib, json, os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError


REPO_ROOT = Path(__file__).resolve().parents[2]


def verified_local_pdf(data: dict, repo_root: Path = REPO_ROOT) -> dict:
    """Resolve an explicitly authorized cache file without weakening artifact provenance."""
    result = {"state": "NOT_AUTHORIZED", "path": None}
    if data.get("identity_state") != "IDENTITY_VERIFIED":
        return result
    if data.get("local_cache_import_policy") != "ALLOW_ZOTERO_STORED_COPY_ON_EXPLICIT_READ":
        return result
    relative = data.get("local_cache_path")
    digest = str(data.get("content_digest") or "")
    if not isinstance(relative, str) or not relative.endswith(".pdf") or not digest.startswith("sha256:"):
        return {"state": "INVALID_CONTRACT", "path": None}
    candidate = (repo_root / relative).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError:
        return {"state": "OUTSIDE_REPO", "path": None}
    if not candidate.is_file():
        return {"state": "FILE_MISSING", "path": None}
    actual = hashlib.sha256(candidate.read_bytes()).hexdigest()
    if actual != digest.removeprefix("sha256:"):
        return {"state": "DIGEST_MISMATCH", "path": None, "actual_digest": f"sha256:{actual}"}
    return {"state": "READY", "path": str(candidate)}


def validate_native_projection(projection: dict, graph: dict) -> list[str]:
    """Return structural errors in the graph-to-Zotero native object contract."""
    errors: list[str] = []
    if projection.get("schema_version") != "0.1":
        errors.append("native projection schema_version must be 0.1")
    if projection.get("projection") != "atr-zotero-native-map":
        errors.append("native projection kind must be atr-zotero-native-map")
    if projection.get("run") != graph.get("run"):
        errors.append("native projection run must match graph run")

    nodes = {node.get("id"): node for node in graph.get("nodes", []) if node.get("id")}
    source_ids = {
        node.get("data", {}).get("source_id")
        for node in nodes.values()
        if node.get("kind") == "paper" and node.get("data", {}).get("source_id")
    }
    object_ids: set[str] = set()
    markers: set[str] = set()
    for index, obj in enumerate(projection.get("objects", [])):
        prefix = f"objects[{index}]"
        object_id, marker = obj.get("object_id"), obj.get("marker")
        if not object_id:
            errors.append(f"{prefix} lacks object_id")
        elif object_id in object_ids:
            errors.append(f"duplicate object_id: {object_id}")
        else:
            object_ids.add(object_id)
        if not marker:
            errors.append(f"{prefix} lacks marker")
        elif marker in markers:
            errors.append(f"duplicate marker: {marker}")
        else:
            markers.add(marker)

        node_id = obj.get("graph_node_id")
        if node_id and node_id not in nodes:
            errors.append(f"{prefix} references missing graph node: {node_id}")
        parent_id = obj.get("parent_graph_node_id")
        if parent_id and parent_id not in nodes:
            errors.append(f"{prefix} references missing parent graph node: {parent_id}")
        for source_id in obj.get("linked_source_ids", []):
            if source_id not in source_ids:
                errors.append(f"{prefix} references missing source: {source_id}")

    kinds = [obj.get("object_kind") for obj in projection.get("objects", [])]
    if kinds.count("topic_note") != 1:
        errors.append("native projection must contain exactly one topic_note")
    kind_mapping = {
        "paper": "source_item",
        "research_problem": "problem_note",
        "claim": "claim_note",
        "knowledge_concept": "knowledge_note",
        "real_world_tension": "tension_note",
        "reality_signal_gap": "reality_gap_note",
        "research_question": "frontier_question_note",
        "derived_research_question": "derived_question_note",
        "collision_review": "collision_review_note",
        "human_review_assessment": "review_assessment_note",
        "topic_route_draft": "route_note",
    }
    for graph_kind, object_kind in kind_mapping.items():
        expected = {node_id for node_id, node in nodes.items() if node.get("kind") == graph_kind}
        observed = {
            obj.get("graph_node_id") for obj in projection.get("objects", [])
            if obj.get("object_kind") == object_kind
        }
        if expected != observed:
            errors.append(
                f"native projection incompletely maps {graph_kind}: "
                f"missing={sorted(expected - observed)}, extra={sorted(observed - expected)}"
            )
    for index, obj in enumerate(projection.get("objects", [])):
        parent_id = obj.get("parent_graph_node_id")
        if obj.get("object_kind") == "knowledge_note" and parent_id \
                and nodes.get(parent_id, {}).get("kind") != "knowledge_concept":
            errors.append(f"objects[{index}] knowledge parent must be a knowledge_concept")
        if obj.get("object_kind") == "derived_question_note" and parent_id \
                and nodes.get(parent_id, {}).get("kind") != "research_problem":
            errors.append(f"objects[{index}] derived question parent must be a research_problem")
        if obj.get("object_kind") == "collision_review_note" and parent_id \
                and nodes.get(parent_id, {}).get("kind") != "research_problem":
            errors.append(f"objects[{index}] collision review parent must be a research_problem")
    collections = projection.get("collections", {})
    for role in ("root", "overview", "knowledge", "research", "sources", "history",
                 "research_tensions", "research_frontier", "research_current", "research_claims",
                 "research_reviews"):
        if not collections.get(role):
            errors.append(f"native projection lacks {role} collection role")
    feedback = projection.get("feedback_contract", {})
    if set(feedback.get("accepted_events", [])) != {"human_note_modified", "human_annotation_modified"}:
        errors.append("feedback contract must accept native note and Reader annotation events")
    if feedback.get("target_priority") != ["claim", "collision_review", "research_problem", "research_question", "real_world_tension", "reality_signal_gap", "source", "knowledge", "topic"]:
        errors.append("feedback target priority must fall back from exact research decisions through sources/knowledge to topic")
    if feedback.get("lifecycle_effect") != "REVIEW_INPUT_ONLY":
        errors.append("Zotero feedback must remain REVIEW_INPUT_ONLY")
    if feedback.get("history_policy") != "APPEND_ONLY_PRESERVE_OLD_NODES_AND_EDGES":
        errors.append("native projection must preserve historical nodes and edges")
    return errors


def native_projection(graph: dict) -> dict:
    """Build the testable contract consumed by the native Zotero plugin."""
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    by_id = {node["id"]: node for node in nodes}
    historical_nodes = set()
    for edge in edges:
        if edge.get("relation") in {
            "superseded_by_recorded_problem_version",
            "superseded_by_knowledge_map_version",
            "superseded_by_opportunity_map_version",
        }:
            historical_nodes.add(edge.get("source"))
        elif edge.get("relation") == "supersedes":
            historical_nodes.add(edge.get("target"))
    changed = True
    while changed:
        changed = False
        for edge in edges:
            if (edge.get("source") in historical_nodes
                    and edge.get("relation") in {"specializes_concept", "generates_finer_review_question", "clusters_real_world_tension"}
                    and edge.get("target") not in historical_nodes):
                historical_nodes.add(edge.get("target")); changed = True
    subject = next((node for node in nodes if node["kind"] == "atr_v2_subject" and node.get("data", {}).get("active")), None)
    title = (subject or {}).get("label") or graph.get("program", {}).get("label") or graph.get("run") or "ATR Topic"

    def linked_sources(node_id: str) -> list[str]:
        result = []
        for edge in edges:
            if edge.get("source") != node_id and edge.get("target") != node_id:
                continue
            other_id = edge["target"] if edge["source"] == node_id else edge["source"]
            other = by_id.get(other_id)
            if other and other.get("kind") == "paper" and other.get("data", {}).get("source_id"):
                result.append(other["data"]["source_id"])
        return sorted(set(result))

    def parent_knowledge_node(node_id: str) -> str | None:
        return next((
            edge.get("source") for edge in edges
            if edge.get("target") == node_id
            and edge.get("relation") == "specializes_concept"
            and by_id.get(edge.get("source"), {}).get("kind") == "knowledge_concept"
        ), None)

    def parent_problem_node(node_id: str) -> str | None:
        return next((
            edge.get("source") for edge in edges
            if edge.get("target") == node_id
            and edge.get("relation") == "generates_finer_review_question"
            and by_id.get(edge.get("source"), {}).get("kind") == "research_problem"
        ), None)

    def reviewed_problem_node(node_id: str) -> str | None:
        return next((
            edge.get("source") for edge in edges
            if edge.get("target") == node_id
            and edge.get("relation") == "is_claim_scoped_reviewed_by"
            and by_id.get(edge.get("source"), {}).get("kind") == "research_problem"
        ), None)

    def parent_by_relation(node_id: str, relation: str, parent_kind: str) -> str | None:
        return next((
            edge.get("source") for edge in edges
            if edge.get("target") == node_id and edge.get("relation") == relation
            and by_id.get(edge.get("source"), {}).get("kind") == parent_kind
        ), None)

    objects = [{
        "object_id": f"topic:{graph.get('run')}",
        "object_kind": "topic_note",
        "graph_node_id": subject.get("id") if subject else None,
        "atr_id": graph.get("run"),
        "title": title,
        "marker": f"ATR Topic Run: {graph.get('run')}",
        "collection_role": "OVERVIEW",
        "linked_source_ids": [],
    }]
    for node in nodes:
        data = node.get("data", {})
        if node.get("kind") == "paper" and data.get("source_id"):
            local_pdf = verified_local_pdf(data)
            objects.append({
                "object_id": f"source:{data['source_id']}",
                "object_kind": "source_item",
                "graph_node_id": node["id"],
                "atr_id": data["source_id"],
                "title": node.get("label"),
                "marker": f"atr-source-id:{data['source_id']}",
                "collection_role": "SOURCES",
                "linked_source_ids": [data["source_id"]],
                "doi": data.get("doi"),
                "url": data.get("url"),
                "pdf_url": data.get("pdf_url"),
                "access_status": data.get("access_status"),
                "access_route": data.get("access_route"),
                "content_form": data.get("content_form"),
                "fulltext_state": data.get("fulltext_state"),
                "worker_inspection_state": data.get("worker_inspection_state"),
                "human_inspection_state": data.get("human_inspection_state"),
                "content_digest": data.get("content_digest"),
                "inspection_spans": data.get("inspection_spans", []),
                "zotero_item_key": data.get("zotero_item_key"),
                "zotero_attachment_key": data.get("zotero_attachment_key"),
                "zotero_attachment_state": data.get("zotero_attachment_state"),
                "zotero_snapshot_state": data.get("zotero_snapshot_state"),
                "local_cache_state": data.get("local_cache_state"),
                "local_cache_path": data.get("local_cache_path"),
                "local_cache_import_state": local_pdf["state"],
                "verified_local_pdf_path": local_pdf["path"],
                "identity_state": data.get("identity_state"),
                "identity_evidence": data.get("identity_evidence", []),
                "local_cache_import_policy": data.get("local_cache_import_policy"),
                "source_layer": data.get("source_layer"),
            })
        elif node.get("kind") == "research_problem" and data.get("problem_id"):
            objects.append({
                "object_id": f"problem:{node['id']}",
                "object_kind": "problem_note",
                "graph_node_id": node["id"],
                "atr_id": data["problem_id"],
                "title": node.get("label"),
                "marker": f"ATR Problem ID: {data['problem_id']} | ATR Graph Node: {node['id']}",
                "review_role": "HISTORICAL_VERSION" if node["id"] in historical_nodes else "CURRENT_REVIEW_TARGET",
                "collection_role": "HISTORY" if node["id"] in historical_nodes else "RESEARCH_CURRENT",
                "linked_source_ids": linked_sources(node["id"]),
            })
        elif node.get("kind") == "claim" and data.get("claim_id"):
            objects.append({
                "object_id": f"claim:{node['id']}",
                "object_kind": "claim_note",
                "graph_node_id": node["id"],
                "atr_id": data["claim_id"],
                "title": node.get("label"),
                "marker": f"ATR Claim ID: {data['claim_id']} | ATR Graph Node: {node['id']}",
                "review_role": "HISTORICAL_VERSION" if node["id"] in historical_nodes else "CURRENT_REVIEW_TARGET",
                "collection_role": "HISTORY" if node["id"] in historical_nodes else "RESEARCH_CLAIMS",
                "linked_source_ids": linked_sources(node["id"]),
            })
        elif node.get("kind") == "knowledge_concept":
            objects.append({
                "object_id": f"knowledge:{node['id']}",
                "object_kind": "knowledge_note",
                "graph_node_id": node["id"],
                "parent_graph_node_id": parent_knowledge_node(node["id"]),
                "atr_id": data.get("concept_id") or node["id"],
                "title": node.get("label"),
                "marker": f"ATR Knowledge Node: {node['id']}",
                "review_role": "HISTORICAL_VERSION" if node["id"] in historical_nodes else "LEARNING_AND_REVIEW_TARGET",
                "collection_role": "HISTORY" if node["id"] in historical_nodes else "KNOWLEDGE",
                "linked_source_ids": linked_sources(node["id"]),
            })
        elif node.get("kind") == "real_world_tension":
            objects.append({
                "object_id": f"tension:{node['id']}",
                "object_kind": "tension_note",
                "graph_node_id": node["id"],
                "atr_id": data.get("tension_id") or node["id"],
                "title": node.get("label"),
                "marker": f"ATR Tension Node: {node['id']}",
                "review_role": "HISTORICAL_VERSION" if node["id"] in historical_nodes else "REAL_WORLD_INSPIRATION_REVIEW_TARGET",
                "collection_role": "HISTORY" if node["id"] in historical_nodes else "RESEARCH_TENSION",
                "linked_source_ids": linked_sources(node["id"]),
            })
        elif node.get("kind") == "reality_signal_gap":
            objects.append({
                "object_id": f"reality-gap:{node['id']}",
                "object_kind": "reality_gap_note",
                "graph_node_id": node["id"],
                "atr_id": data.get("decision_id") or node["id"],
                "title": node.get("label"),
                "marker": f"ATR Reality Signal Gap: {node['id']}",
                "review_role": "REALITY_SIGNAL_SEARCH_BOUNDARY",
                "collection_role": "RESEARCH_TENSION",
                "linked_source_ids": linked_sources(node["id"]),
            })
        elif node.get("kind") == "research_question":
            objects.append({
                "object_id": f"question:{node['id']}",
                "object_kind": "frontier_question_note",
                "graph_node_id": node["id"],
                "atr_id": data.get("tension_id") or node["id"],
                "title": node.get("label"),
                "marker": f"ATR Research Question Node: {node['id']}",
                "review_role": "FRONTIER_REVIEW_TARGET",
                "collection_role": "RESEARCH_FRONTIER",
                "linked_source_ids": linked_sources(node["id"]),
            })
        elif node.get("kind") == "derived_research_question":
            objects.append({
                "object_id": f"derived-question:{node['id']}",
                "object_kind": "derived_question_note",
                "graph_node_id": node["id"],
                "parent_graph_node_id": parent_problem_node(node["id"]),
                "atr_id": data.get("question_id") or node["id"],
                "title": node.get("label"),
                "marker": f"ATR Derived Question Node: {node['id']}",
                "review_role": "HISTORICAL_VERSION" if node["id"] in historical_nodes else "FINER_GRAINED_REVIEW_TARGET",
                "collection_role": "HISTORY" if node["id"] in historical_nodes else "RESEARCH_DERIVED",
                "linked_source_ids": linked_sources(node["id"]),
            })
        elif node.get("kind") == "collision_review":
            objects.append({
                "object_id": f"collision-review:{node['id']}",
                "object_kind": "collision_review_note",
                "graph_node_id": node["id"],
                "parent_graph_node_id": reviewed_problem_node(node["id"]),
                "atr_id": data.get("review_id") or node["id"],
                "title": node.get("label"),
                "marker": f"ATR Collision Review: {data.get('review_id') or node['id']} | ATR Graph Node: {node['id']}",
                "review_role": "READ_ONLY_WORKER_OUTPUT_NOT_GATE",
                "collection_role": "RESEARCH_REVIEWS",
                "linked_source_ids": linked_sources(node["id"]),
            })
        elif node.get("kind") == "human_review_assessment" and data.get("assessment_id"):
            objects.append({
                "object_id": f"review-assessment:{node['id']}",
                "object_kind": "review_assessment_note",
                "graph_node_id": node["id"],
                "atr_id": data["assessment_id"],
                "title": node.get("label"),
                "marker": f"ATR Review Assessment: {data['assessment_id']} | ATR Graph Node: {node['id']}",
                "review_role": "IMMUTABLE_CODEX_REVIEW",
                "collection_role": "RESEARCH_REVIEWS",
                "linked_source_ids": linked_sources(node["id"]),
            })
        elif node.get("kind") == "topic_route_draft":
            objects.append({
                "object_id": f"topic-route:{node['id']}", "object_kind": "route_note",
                "graph_node_id": node["id"], "atr_id": data.get("package_id") or node["id"],
                "title": node.get("label"), "marker": f"ATR Topic Route Node: {node['id']}",
                "review_role": "PENDING_INDEPENDENT_ROUTE_REVIEW", "collection_role": "OVERVIEW",
                "linked_source_ids": linked_sources(node["id"]),
            })
        elif node.get("kind") == "research_portfolio":
            objects.append({
                "object_id": f"portfolio:{node['id']}", "object_kind": "portfolio_note",
                "graph_node_id": node["id"], "atr_id": data.get("portfolio_id") or node["id"],
                "title": node.get("label"), "marker": f"ATR Portfolio Node: {node['id']}",
                "review_role": "NAVIGATION_AND_REVIEW_BOUNDARY", "collection_role": "OVERVIEW",
                "linked_source_ids": [],
            })
        elif node.get("kind") == "research_program":
            objects.append({
                "object_id": f"program:{node['id']}", "object_kind": "program_note",
                "graph_node_id": node["id"],
                "parent_graph_node_id": parent_by_relation(node["id"], "registers_separate_program_authority", "research_portfolio"),
                "atr_id": data.get("program_key") or node["id"], "title": node.get("label"),
                "marker": f"ATR Research Program Node: {node['id']}",
                "review_role": "PROGRAM_INTAKE_REVIEW", "collection_role": "OVERVIEW",
                "linked_source_ids": [],
            })
        elif node.get("kind") == "legacy_research_run":
            objects.append({
                "object_id": f"legacy-run:{node['id']}", "object_kind": "legacy_run_note",
                "graph_node_id": node["id"],
                "parent_graph_node_id": parent_by_relation(node["id"], "retains_legacy_branch_as_input", "research_program"),
                "atr_id": node["id"], "title": node.get("label"),
                "marker": f"ATR Legacy Run Node: {node['id']}",
                "review_role": "HISTORICAL_VERSION", "collection_role": "HISTORY",
                "linked_source_ids": [],
            })
        elif node.get("kind") == "historical_alignment_audit":
            objects.append({
                "object_id": f"alignment-audit:{node['id']}", "object_kind": "alignment_audit_note",
                "graph_node_id": node["id"], "atr_id": data.get("audit_digest") or node["id"],
                "title": node.get("label"), "marker": f"ATR Alignment Audit Node: {node['id']}",
                "review_role": "IMMUTABLE_MIGRATION_BOUNDARY", "collection_role": "HISTORY",
                "linked_source_ids": [],
            })
        elif node.get("kind") == "legacy_mapping_audit":
            objects.append({
                "object_id": f"legacy-mapping-audit:{node['id']}", "object_kind": "alignment_audit_note",
                "graph_node_id": node["id"], "atr_id": data.get("mapping_id") or node["id"],
                "title": node.get("label"), "marker": f"ATR Alignment Audit Node: {node['id']}",
                "review_role": "IMMUTABLE_MIGRATION_BOUNDARY", "collection_role": "HISTORY",
                "linked_source_ids": [],
            })
        elif node.get("kind") == "zotero_source_reconciliation":
            objects.append({
                "object_id": f"zotero-reconciliation:{node['id']}",
                "object_kind": "alignment_audit_note",
                "graph_node_id": node["id"], "atr_id": node["id"],
                "title": node.get("label"),
                "marker": f"ATR Alignment Audit Node: {node['id']}",
                "collection_role": "HISTORY", "review_role": "AVAILABILITY_AUDIT_ONLY",
                "linked_source_ids": linked_sources(node["id"]),
            })
        elif node.get("kind") == "repo_pdf_zotero_handoff_audit":
            objects.append({
                "object_id": f"repo-pdf-handoff:{node['id']}", "object_kind": "alignment_audit_note",
                "graph_node_id": node["id"], "atr_id": node["id"], "title": node.get("label"),
                "marker": f"ATR Alignment Audit Node: {node['id']}",
                "collection_role": "HISTORY", "review_role": "AVAILABILITY_AUDIT_ONLY",
                "linked_source_ids": linked_sources(node["id"]),
            })
    projection = {
        "schema_version": "0.1",
        "projection": "atr-zotero-native-map",
        "run": graph.get("run"),
        "source_graph_projection": graph.get("projection", "legacy-read-only"),
        "topic": {"title": title, "marker": f"ATR Topic Run: {graph.get('run')}"},
        "collections": {
            "root": f"ATR · {title}",
            "overview": "01 · Topic 与演化",
            "knowledge": "02 · 知识体系",
            "research": "03 · 研究问题与断言",
            "sources": "04 · 来源阅读",
            "history": "05 · 历史版本",
            "research_tensions": "01 · 现实世界张力",
            "research_frontier": "02 · 前沿研究问题",
            "research_current": "03 · 当前问题卡",
            "research_claims": "04 · 待审查断言",
            "research_reviews": "05 · 共创复核",
        },
        "objects": objects,
        "feedback_contract": {
            "accepted_events": ["human_note_modified", "human_annotation_modified"],
            "target_priority": ["claim", "collision_review", "research_problem", "research_question", "real_world_tension", "reality_signal_gap", "source", "knowledge", "topic"],
            "lifecycle_effect": "REVIEW_INPUT_ONLY",
            "history_policy": "APPEND_ONLY_PRESERVE_OLD_NODES_AND_EDGES",
        },
    }
    errors = validate_native_projection(projection, graph)
    if errors:
        raise ValueError("invalid native Zotero projection: " + "; ".join(errors))
    return projection


def export_native_projection(graph: dict, out: Path) -> Path:
    path = out / "zotero" / "native-projection.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(native_projection(graph), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def export_bundle(graph: dict, out: Path) -> None:
    zotero = out / "zotero"; cards = zotero / "reading-cards"
    cards.mkdir(parents=True, exist_ok=True)
    items = []
    for node in graph["nodes"]:
        if node["kind"] != "paper": continue
        data = node["data"]; sid = data["source_id"]
        item_type = "article-journal" if data.get("source_layer") == "scholarly_evidence" else "webpage"
        items.append({"id": sid, "type": item_type, "title": node["label"], "URL": data["url"],
                      "keyword": ["ATR", "atr-source-id:" + sid, "atr-source-kind:" + data["source_kind"],
                                  "atr-source-layer:" + data.get("source_layer", "source_needs_review")],
                      "note": f"ATR source ID: {sid}\nEvidence boundary recorded in reading card."})
        (cards / f"{sid}.md").write_text(
            f"# {node['label']}\n\nATR source ID: `{sid}`\n\n## 来源支持的内容\n\n{data['supports']}\n\n"
            f"## 来源不支持 / 不能推出的内容\n\n{data['does_not_support']}\n\n"
            "## 我的阅读与反驳\n\n- [ ] 我核对了原文的相关段落：\n- [ ] 我不同意或需要澄清的地方：\n- [ ] 这对哪个研究问题有影响：\n", encoding="utf-8")
    (zotero / "items.csl.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    export_native_projection(graph, out)


def sync_web_api(graph: dict, audit_path: Path) -> dict:
    """Create a dedicated collection then source items and child notes. Requires explicit env credentials."""
    required = {key: os.getenv(key) for key in ("ZOTERO_LIBRARY_TYPE", "ZOTERO_LIBRARY_ID", "ZOTERO_API_KEY")}
    missing = [k for k, v in required.items() if not v]
    if missing: raise RuntimeError("Refusing Zotero write: missing " + ", ".join(missing))
    base = f"https://api.zotero.org/{required['ZOTERO_LIBRARY_TYPE']}s/{required['ZOTERO_LIBRARY_ID']}"
    headers = {"Zotero-API-Key": required["ZOTERO_API_KEY"], "Content-Type": "application/json"}
    def post(path: str, body: list[dict]) -> dict:
        req = Request(base + path, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urlopen(req, timeout=30) as response: return json.loads(response.read() or b"{}")
        except HTTPError as e: raise RuntimeError(f"Zotero API {e.code}: {e.read().decode()}") from e
    collection = post("/collections", [{"name": f"ATR · {graph['run']}"}])
    collection_key = collection["successful"]["0"]["key"]
    records = []
    for node in graph["nodes"]:
        if node["kind"] == "paper":
            d = node["data"]
            records.append({"itemType":"journalArticle", "title":node["label"], "url":d["url"],
                            "extra":f"ATR source ID: {d['source_id']}", "tags":[{"tag":"ATR"},{"tag":f"atr-source-id:{d['source_id']}"}], "collections":[collection_key]})
    item_result = post("/items", records) if records else {}
    notes = []
    for index, node in enumerate(n for n in graph["nodes"] if n["kind"] == "paper"):
        item = item_result.get("successful", {}).get(str(index), {})
        key = item.get("key") if isinstance(item, dict) else None
        if key:
            d = node["data"]
            notes.append({"itemType": "note", "parentItem": key,
                          "note": f"<h1>ATR 阅读卡</h1><p>Source ID: {d['source_id']}</p>"
                                  f"<h2>来源支持的内容</h2><p>{d['supports']}</p>"
                                  f"<h2>来源不支持的内容</h2><p>{d['does_not_support']}</p>"
                                  "<h2>我的阅读与反驳</h2><p></p>"})
    result = {"collection": collection, "items": item_result, "notes": post("/items", notes) if notes else {}}
    audit_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
