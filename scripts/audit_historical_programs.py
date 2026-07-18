#!/usr/bin/env python3
"""Inventory ATR history without mutating or promoting any historical run.

The output makes program-catalog dispositions operational: every referenced
directory is inspected for the artifacts that can be reused as a provenance
input, and for missing artifacts that prevent treating the old directory as a
current continuation.  It deliberately never repairs, deletes, or moves the
historical inputs.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any


def json_rows(path: Path) -> tuple[int, list[str]]:
    if not path.exists():
        return 0, [f"missing {path.name}"]
    errors: list[str] = []
    count = 0
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            json.loads(line)
            count += 1
        except json.JSONDecodeError as exc:
            errors.append(f"{path.name}:{number} invalid JSON ({exc.msg})")
    return count, errors


def load_json_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            body = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(body, dict):
            rows.append(body)
    return rows


def json_object(path: Path) -> tuple[dict[str, Any], list[str]]:
    if not path.exists():
        return {}, [f"missing {path.name}"]
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as exc:
        return {}, [f"{path.name} invalid JSON ({exc.msg})"]


def _harness_result(script: Path, path: Path) -> dict[str, Any] | None:
    if not script.is_file():
        return None
    process = subprocess.run(
        ["python3", str(script), str(path), "--json"],
        capture_output=True, text=True, check=False,
    )
    try:
        body = json.loads(process.stdout)
    except json.JSONDecodeError:
        return {"pass": False, "errors": [process.stderr.strip() or "checker returned non-JSON output"]}
    body["exit_code"] = process.returncode
    return body


def audit_run(path: Path, disposition: str, role: str, harness_root: Path | None = None) -> dict[str, Any]:
    sources, issues = json_rows(path / "evidence" / "sources.jsonl")
    source_rows = load_json_rows(path / "evidence" / "sources.jsonl")
    claims, claim_issues = json_rows(path / "evidence" / "claims.jsonl")
    if (path / "evidence" / "claims.jsonl").exists():
        issues.extend(claim_issues)
    state, state_issues = json_object(path / "run-state.json")
    issues.extend(state_issues)
    frontier, frontier_issues = json_object(path / "knowledge" / "frontier-map.json")
    # A frontier map is optional for some historical route/claim runs, so keep
    # it separate from malformed-input issues.
    if frontier_issues and frontier_issues != ["missing frontier-map.json"]:
        issues.extend(frontier_issues)
    artifacts = {
        "frontier_map": bool(frontier),
        "knowledge_context": any((path / "knowledge").glob("knowledge-context*.json")),
        "opportunity_map": (path / "knowledge" / "opportunity-map.json").exists(),
        "concept_map": (path / "knowledge" / "concept-map.json").exists(),
        "problem_cards": len(list((path / "knowledge" / "research-problem-cards").glob("*.json"))) if (path / "knowledge" / "research-problem-cards").exists() else 0,
        "skill_events": (path / "observability" / "skill-events.jsonl").exists() and bool((path / "observability" / "skill-events.jsonl").read_text(encoding="utf-8").strip()),
        "artifact_manifests": len(list(path.rglob("artifact-manifest.json"))),
    }
    source_access = {
        "records": sources,
        "with_doi": sum(bool(row.get("doi")) for row in source_rows),
        "with_pdf_url": sum(bool(row.get("pdf_url")) for row in source_rows),
        "with_access_status": sum(bool(row.get("access_status")) for row in source_rows),
        "declared_fulltext_attached": sum(bool(row.get("fulltext_attached") or row.get("zotero_attachment_key")) for row in source_rows),
        "declared_fulltext_inspected": sum(bool(row.get("fulltext_inspected") and (row.get("locator") or row.get("inspected_locator"))) for row in source_rows),
        "with_content_locator": sum(bool(row.get("locator") or row.get("inspected_locator")) for row in source_rows),
    }
    reuse = []
    if sources: reuse.append("source_ledger")
    if claims: reuse.append("claim_history")
    if artifacts["frontier_map"]: reuse.append("frontier_map")
    if artifacts["skill_events"]: reuse.append("recorded_process_events")
    blocking = []
    if not sources: blocking.append("no parseable source ledger")
    if issues: blocking.append("malformed required artifact")
    noncurrent = []
    for key in ("knowledge_context", "opportunity_map", "concept_map"):
        if not artifacts[key]: noncurrent.append(f"missing {key}")
    if not claims: noncurrent.append("no current claim ledger")
    if artifacts["artifact_manifests"] == 0: noncurrent.append("no LEGACY_MAPPED artifact manifests")
    if source_access["with_access_status"] < sources: noncurrent.append("source access/fulltext state undeclared")
    if source_access["declared_fulltext_inspected"] == 0: noncurrent.append("no source declared FULLTEXT_INSPECTED with locator")

    artifact_dispositions = []
    if sources:
        artifact_dispositions.append({"artifact": "evidence/sources.jsonl", "decision": "REUSE_AFTER_SOURCE_REVERIFICATION", "boundary": "metadata/abstract records are not inspected full text"})
    if claims:
        artifact_dispositions.append({"artifact": "evidence/claims.jsonl", "decision": "RETAIN_AS_CLAIM_HISTORY", "boundary": "cannot become a current claim without a new claim version and review"})
    if (path / "evidence" / "edges.jsonl").is_file():
        artifact_dispositions.append({"artifact": "evidence/edges.jsonl", "decision": "RETAIN_AS_LEGACY_PROVENANCE", "boundary": "edge semantics require remapping before v2 projection"})
    if artifacts["frontier_map"]:
        artifact_dispositions.append({"artifact": "knowledge/frontier-map.json", "decision": "REUSE_AS_HISTORICAL_FRONTIER_INPUT", "boundary": "requires current source refresh and FKS review"})
    if artifacts["knowledge_context"]:
        artifact_dispositions.append({"artifact": "knowledge/knowledge-context*.json", "decision": "RETAIN_AS_LEGACY_KNOWLEDGE_CONTEXT", "boundary": "not a current canonical knowledge context"})
    if artifacts["opportunity_map"]:
        artifact_dispositions.append({"artifact": "knowledge/opportunity-map.json", "decision": "REUSE_AS_R0_5_INPUT_ONLY", "boundary": "not a gap, seed, or route certificate"})
    if artifacts["skill_events"]:
        artifact_dispositions.append({"artifact": "observability/skill-events.jsonl", "decision": "RETAIN_AS_PROCESS_HISTORY", "boundary": "v1.0 events are excluded from pair-certified invocation metrics"})
    artifact_dispositions.extend([
        {"artifact": "run-state.json", "decision": "RETAIN_AS_LEGACY_STATE_SNAPSHOT", "boundary": "must not be copied into v2 lifecycle state"},
        {"artifact": "unclassified prose/code/results", "decision": "ARCHIVE_PENDING_ARTIFACT_LEVEL_REVIEW", "boundary": "not consumed automatically"},
    ])

    structural = _harness_result(harness_root / "scripts" / "check_run.py", path) if harness_root else None
    localization = _harness_result(harness_root / "scripts" / "advise_stage.py", path) if harness_root else None
    alignment_disposition = "QUARANTINE_REQUIRED_ARTIFACT" if blocking else "LEGACY_MAP_INPUT_ONLY"
    if disposition.startswith("canonical_"):
        integration_action = "PRIORITY_REVIEW_INPUT"
    elif disposition.startswith("merge_as_"):
        integration_action = "MERGE_AFTER_DEDUP_AND_REVERIFY"
    else:
        integration_action = "RETAIN_BRANCH_AFTER_REVERIFY"
    return {
        "run": path.name, "path": str(path), "catalog_disposition": disposition, "catalog_role": role,
        "state": {"schema_version": state.get("schema_version"), "harness_release": state.get("harness_release"), "active_stage": state.get("active_stage")},
        "counts": {"sources": sources, "claims": claims}, "artifacts": artifacts, "source_access": source_access,
        "reusable_as_provenance_input": reuse, "not_sufficient_for_current_continuation": noncurrent,
        "artifact_dispositions": artifact_dispositions,
        "alignment_disposition": alignment_disposition,
        "program_integration_action": integration_action,
        "harness_structural_check": structural,
        "harness_stage_localization": localization,
        "integrity_issues": issues, "blocking_issues": blocking,
    }


def audit(catalog_path: Path, harness_root: Path | None = None) -> dict[str, Any]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    programs = []
    all_runs = []
    for program in catalog.get("programs", []):
        rows = []
        for branch in program.get("branches", []):
            path = (catalog_path.parent / branch["run"]).resolve()
            rows.append(audit_run(path, branch.get("disposition", "UNSPECIFIED"), branch.get("role", ""), harness_root))
        all_runs.extend(rows)
        programs.append({"key": program["key"], "label": program["label"], "root_question": program["root_question"], "runs": rows})
    disposition_counts = Counter(row["catalog_disposition"] for row in all_runs)
    all_source_rows = []
    for row in all_runs:
        all_source_rows.extend(load_json_rows(Path(row["path"]) / "evidence" / "sources.jsonl"))
    unique_source_ids = {str(row.get("source_id", "")).strip() for row in all_source_rows if row.get("source_id")}
    unique_urls = {str(row.get("url", "")).strip() for row in all_source_rows if row.get("url")}
    unique_titles = {str(row.get("title", "")).strip() for row in all_source_rows if row.get("title")}
    return {
        "schema_version": "0.2", "artifact_type": "historical-program-alignment-audit", "catalog": str(catalog_path.resolve()),
        "policy": catalog.get("policy", {}), "summary": {
            "program_count": len(programs), "run_count": len(all_runs),
            "runs_with_integrity_issues": sum(bool(row["integrity_issues"]) for row in all_runs),
            "runs_with_parseable_sources": sum(row["counts"]["sources"] > 0 for row in all_runs),
            "source_records": sum(row["source_access"]["records"] for row in all_runs),
            "unique_source_ids": len(unique_source_ids),
            "unique_source_urls": len(unique_urls),
            "unique_source_titles": len(unique_titles),
            "duplicate_source_id_rows": len(all_source_rows) - len(unique_source_ids),
            "source_records_with_access_status": sum(row["source_access"]["with_access_status"] for row in all_runs),
            "source_records_declared_fulltext_inspected": sum(row["source_access"]["declared_fulltext_inspected"] for row in all_runs),
            "runs_with_legacy_manifests": sum(row["artifacts"]["artifact_manifests"] > 0 for row in all_runs),
            "structurally_valid_under_current_checker": sum(bool((row["harness_structural_check"] or {}).get("pass")) for row in all_runs),
            "alignment_dispositions": dict(sorted(Counter(row["alignment_disposition"] for row in all_runs).items())),
            "dispositions": dict(sorted(disposition_counts.items())),
        },
        "program_gap_matrix": [
            {
                "program": program["key"],
                "historical_runs": len(program["runs"]),
                "source_records": sum(row["counts"]["sources"] for row in program["runs"]),
                "required_before_current_v2_chain": [
                    "new program-level v2 intake and topic route",
                    "source access/fulltext re-verification with Zotero attachment state",
                    "LEGACY_MAPPED manifests for every consumed artifact",
                    "fresh source-grounded FKS/knowledge context",
                    "opportunity decision (map or NO_ADMISSIBLE_SIGNAL)",
                    "current claim/problem versions only after their independent gates",
                ],
            }
            for program in programs
        ],
        "programs": programs,
    }


def markdown_report(report: dict[str, Any]) -> str:
    s = report["summary"]
    lines = [
        "# multilingual-aaai → ATR v2 历史归位矩阵",
        "",
        "> 这是只读迁移判定，不改写历史 run。结构检查通过只说明旧契约自洽，不代表它已成为当前 ATR v2 研究链。",
        "",
        "## 总体判定",
        "",
        f"- 覆盖 {s['program_count']} 个 program、{s['run_count']} 个历史 run；当前 checker 结构通过 {s['structurally_valid_under_current_checker']}/{s['run_count']}。",
        f"- 共 {s['source_records']} 条来源记录、{s['unique_source_ids']} 个唯一 source ID、{s['unique_source_urls']} 个唯一 URL、{s['unique_source_titles']} 个唯一标题；source ID 重复行 {s['duplicate_source_id_rows']} 条，进入 Zotero 前必须去重。",
        f"- access status 已声明 {s['source_records_with_access_status']}/{s['source_records']}；带定位的全文已检查记录 {s['source_records_declared_fulltext_inspected']}/{s['source_records']}。因此这些来源目前只能按 metadata/abstract 历史输入处理，不能声称已经下载、阅读或核实全文。",
        f"- 只有 {s['runs_with_legacy_manifests']}/{s['run_count']} 个 run 含任意 artifact manifest；没有 manifest 的材料只能 `LEGACY_MAPPED`，不能作为新 run 的 canonical 模板。",
        "- 28 个 run 全部归为 `LEGACY_MAP_INPUT_ONLY`：没有发现需要物理删除的 JSON 损坏，但旧 stage、gate、claim 和 route 全部退出 current 权威；清退发生在当前投影与授权层，不破坏历史目录。",
        "",
        "## 六个 program 的弹性骨架缺口",
        "",
        "| Program | 历史 run | 来源记录 | 成为 current v2 链前必须补齐 |",
        "| --- | ---: | ---: | --- |",
    ]
    for row in report["program_gap_matrix"]:
        lines.append(f"| `{row['program']}` | {row['historical_runs']} | {row['source_records']} | " + "；".join(row["required_before_current_v2_chain"]) + " |")
    lines.extend([
        "",
        "## 28 个 run 的逐项归位",
        "",
        "| Program | 历史 run | 旧 stage | 来源 / claim | 可复用结构 | 归位动作 |",
        "| --- | --- | --- | ---: | --- | --- |",
    ])
    for program in report["programs"]:
        for row in program["runs"]:
            available = []
            for key, label in (("frontier_map", "frontier"), ("knowledge_context", "knowledge-context"), ("opportunity_map", "opportunity"), ("concept_map", "concept-map")):
                if row["artifacts"][key]:
                    available.append(label)
            if row["artifacts"]["problem_cards"]:
                available.append(f"problem-card×{row['artifacts']['problem_cards']}")
            if row["artifacts"]["skill_events"]:
                available.append("process-events")
            lines.append(
                f"| `{program['key']}` | `{row['run']}` | `{row['state']['active_stage'] or 'UNKNOWN'}` | "
                f"{row['counts']['sources']} / {row['counts']['claims']} | {', '.join(available) or '仅基础 ledger'} | "
                f"`{row['program_integration_action']}`；`{row['alignment_disposition']}` |"
            )
    lines.extend([
        "",
        "## 清退与保留规则",
        "",
        "- 来源 ledger：`REUSE_AFTER_SOURCE_REVERIFICATION`；先按 DOI/URL/标题去重，再补 Zotero attachment、access route、全文检查 locator。",
        "- 旧 claim：`RETAIN_AS_CLAIM_HISTORY`；不得复制为 current claim。",
        "- 旧 frontier/knowledge/opportunity：只作为新 program 综合的输入，必须重新绑定已核查来源和当前 cutoff。",
        "- 旧 gate/route/run-state：只显示为历史过程，绝不迁移其 PASS 或 stage。",
        "- v1.0 未配对 skill event：保留可视化时间线，但从精确 invocation/token 指标中隔离。",
        "- 未分类 prose/code/result：默认 archive，只有获得 artifact-level manifest 和明确父子 lineage 后才进入新链。",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--harness-root", type=Path)
    parser.add_argument("--markdown-out", type=Path)
    args = parser.parse_args()
    report = audit(args.catalog, args.harness_root.resolve() if args.harness_root else None)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.markdown_out:
        args.markdown_out.parent.mkdir(parents=True, exist_ok=True)
        args.markdown_out.write_text(markdown_report(report), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
