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


def json_object(path: Path) -> tuple[dict[str, Any], list[str]]:
    if not path.exists():
        return {}, [f"missing {path.name}"]
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as exc:
        return {}, [f"{path.name} invalid JSON ({exc.msg})"]


def audit_run(path: Path, disposition: str, role: str) -> dict[str, Any]:
    sources, issues = json_rows(path / "evidence" / "sources.jsonl")
    claims, claim_issues = json_rows(path / "evidence" / "claims.jsonl")
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
    return {
        "run": path.name, "path": str(path), "catalog_disposition": disposition, "catalog_role": role,
        "state": {"schema_version": state.get("schema_version"), "harness_release": state.get("harness_release"), "active_stage": state.get("active_stage")},
        "counts": {"sources": sources, "claims": claims}, "artifacts": artifacts,
        "reusable_as_provenance_input": reuse, "not_sufficient_for_current_continuation": noncurrent,
        "integrity_issues": issues, "blocking_issues": blocking,
    }


def audit(catalog_path: Path) -> dict[str, Any]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    programs = []
    all_runs = []
    for program in catalog.get("programs", []):
        rows = []
        for branch in program.get("branches", []):
            path = (catalog_path.parent / branch["run"]).resolve()
            rows.append(audit_run(path, branch.get("disposition", "UNSPECIFIED"), branch.get("role", "")))
        all_runs.extend(rows)
        programs.append({"key": program["key"], "label": program["label"], "root_question": program["root_question"], "runs": rows})
    disposition_counts = Counter(row["catalog_disposition"] for row in all_runs)
    return {
        "schema_version": "0.1", "artifact_type": "historical-program-alignment-audit", "catalog": str(catalog_path.resolve()),
        "policy": catalog.get("policy", {}), "summary": {
            "program_count": len(programs), "run_count": len(all_runs),
            "runs_with_integrity_issues": sum(bool(row["integrity_issues"]) for row in all_runs),
            "runs_with_parseable_sources": sum(row["counts"]["sources"] > 0 for row in all_runs),
            "dispositions": dict(sorted(disposition_counts.items())),
        }, "programs": programs,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = audit(args.catalog)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
