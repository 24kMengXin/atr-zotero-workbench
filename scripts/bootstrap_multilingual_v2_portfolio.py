#!/usr/bin/env python3
"""Create one ATR v2 portfolio and six INTAKE-only program children.

The bootstrap consumes the audited catalog, not chat memory.  It creates new
controller authorities and immutable attachments; it never edits historical
runs, copies their lifecycle state, or advances a new subject past INTAKE.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def stable_write(path: Path, body: dict[str, Any]) -> None:
    encoded = json.dumps(body, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != encoded:
        raise ValueError(f"refusing to overwrite divergent bootstrap definition: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")


def run(command: list[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def create_run(atrctl: Path, target: Path, run_id: str, subject_id: str,
               subject_kind: str, definitions: list[tuple[Path, str, str, str]]) -> dict[str, Any]:
    """Create a run and attach definitions.

    definitions rows are (path, artifact kind, attachment role, note).  The
    first definition owns subject creation; remaining definitions are attached
    at version 0 without a lifecycle transition.
    """
    if target.exists():
        report = json.loads(run(["python3", str(atrctl), "check", str(target)]))
        if not report.get("pass"):
            raise ValueError(f"existing v2 run is invalid: {target}: {report}")
        return {"run_id": run_id, "path": str(target), "created": False, "check": report}

    run(["python3", str(atrctl), "init", str(target), "--run-id", run_id])
    artifact_ids = []
    for definition, kind, _, _ in definitions:
        artifact_ids.append(run([
            "python3", str(atrctl), "ingest", str(target), str(definition),
            "--kind", kind, "--scope", "historical alignment input; no lifecycle authorization",
        ]))
    run([
        "python3", str(atrctl), "add-subject", str(target),
        "--subject", subject_id, "--kind", subject_kind,
        "--artifact", artifact_ids[0], "--event-id", f"EV-INTAKE-{run_id}",
    ])
    for index, ((_, _, role, note), artifact_id) in enumerate(zip(definitions[1:], artifact_ids[1:]), start=1):
        run([
            "python3", str(atrctl), "attach", str(target),
            "--subject", subject_id, "--expected-version", "0",
            "--artifact", artifact_id, "--role", role,
            "--attachment-id", f"ATT-{run_id}-{index:02d}", "--note", note,
        ])
    report = json.loads(run(["python3", str(atrctl), "check", str(target)]))
    if not report.get("pass"):
        raise ValueError(f"new v2 run failed check: {target}: {report}")
    return {"run_id": run_id, "path": str(target), "created": True, "artifact_ids": artifact_ids, "check": report}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog", type=Path)
    parser.add_argument("audit", type=Path)
    parser.add_argument("--atrctl", type=Path, required=True)
    parser.add_argument("--definitions-dir", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--date", default="2026-07-19")
    args = parser.parse_args()

    catalog_path = args.catalog.resolve(); audit_path = args.audit.resolve()
    catalog = load(catalog_path); audit = load(audit_path)
    if audit.get("summary", {}).get("run_count") != sum(len(program.get("branches", [])) for program in catalog.get("programs", [])):
        raise ValueError("audit/catalog run count mismatch")
    if audit.get("summary", {}).get("runs_with_integrity_issues"):
        raise ValueError("historical integrity issues require quarantine before bootstrap")
    audit_digest = "sha256:" + hashlib.sha256(audit_path.read_bytes()).hexdigest()

    portfolio_run_id = f"{args.date}-multilingual-program-portfolio-v2"
    child_registry = []
    audit_programs = {program["key"]: program for program in audit["programs"]}
    for program in catalog["programs"]:
        key = program["key"]
        child_registry.append({
            "program_key": key,
            "run_id": f"{args.date}-{key}-v2-intake",
            "subject_id": f"program:{key}",
            "relationship": "PORTFOLIO_CHILD_SEPARATE_AUTHORITY",
        })

    portfolio_intake = {
        "schema_version": "1.0", "artifact_type": "portfolio-intake",
        "portfolio_id": "multilingual-aaai-program-portfolio",
        "question": "How should the six historically distinct multilingual/agent research programs be revalidated and developed without collapsing their mechanisms or inheriting legacy lifecycle claims?",
        "historical_alignment_audit": audit_digest,
        "children": child_registry,
        "controller_boundary": "This intake registers separate program authorities. It does not promote any historical stage, gate, claim, source interpretation, or child result.",
    }
    audit_summary = {
        "schema_version": "1.0", "artifact_type": "historical-alignment-summary",
        "audit_digest": audit_digest,
        "summary": audit["summary"],
        "disposition": "LEGACY_MAP_INPUT_ONLY",
        "source_boundary": "A source record is metadata/abstract history until access, attachment, full-text inspection, and locator evidence are recorded separately.",
    }
    registry_body = {
        "schema_version": "1.0", "artifact_type": "program-registry",
        "portfolio_id": "multilingual-aaai-program-portfolio", "children": child_registry,
        "mutation_boundary": "Children never mutate this parent; terminal child summaries require a later explicit attachment.",
    }
    definitions_dir = args.definitions_dir.resolve()
    portfolio_defs = []
    for name, body, kind, role, note in (
        ("portfolio-intake.json", portfolio_intake, "portfolio-intake", "SUBJECT_ORIGIN", "Creates the portfolio at INTAKE only."),
        ("historical-alignment-summary.json", audit_summary, "historical-alignment-summary", "HISTORICAL_INPUT_BOUNDARY", "Records what may and may not be reused."),
        ("program-registry.json", registry_body, "program-registry", "CHILD_AUTHORITY_REGISTRY", "Registers six separate child authorities."),
    ):
        path = definitions_dir / name; stable_write(path, body); portfolio_defs.append((path, kind, role, note))

    results = []
    results.append(create_run(
        args.atrctl.resolve(), args.runs_root.resolve() / portfolio_run_id,
        portfolio_run_id, "portfolio:multilingual-aaai", "portfolio", portfolio_defs,
    ))
    for program in catalog["programs"]:
        key = program["key"]; program_audit = audit_programs[key]
        run_id = f"{args.date}-{key}-v2-intake"
        intake = {
            "schema_version": "1.0", "artifact_type": "program-intake",
            "program_key": key, "label": program["label"], "root_question": program["root_question"],
            "parent_portfolio_run": portfolio_run_id,
            "language_axis_binding_required": "multilingual" in key,
            "historical_alignment_audit": audit_digest,
            "initial_state": "INTAKE",
            "next_legal_work": "deduplicate and reverify sources; author a fresh program-level topic route and FKS knowledge context",
            "controller_boundary": "The historical branches are inputs only. This artifact does not inherit their stage, gate, claim, route, or scholarly verdict.",
        }
        branches = {
            "schema_version": "1.0", "artifact_type": "legacy-branch-index", "program_key": key,
            "branches": [{
                "run": row["run"], "path": row["path"],
                "catalog_role": row["catalog_role"], "catalog_disposition": row["catalog_disposition"],
                "alignment_disposition": row["alignment_disposition"],
                "integration_action": row["program_integration_action"],
                "sources": row["counts"]["sources"], "claims": row["counts"]["claims"],
                "reusable": row["reusable_as_provenance_input"],
                "missing_for_current": row["not_sufficient_for_current_continuation"],
            } for row in program_audit["runs"]],
            "consumption_rule": "No branch artifact is consumed until it receives an artifact-level LEGACY_MAPPED manifest and its source claims are reverified.",
        }
        program_dir = definitions_dir / "programs" / key
        intake_path = program_dir / "program-intake.json"; stable_write(intake_path, intake)
        branches_path = program_dir / "legacy-branch-index.json"; stable_write(branches_path, branches)
        results.append(create_run(
            args.atrctl.resolve(), args.runs_root.resolve() / run_id, run_id,
            f"program:{key}", "research-program",
            [
                (intake_path, "program-intake", "SUBJECT_ORIGIN", "Creates the program at INTAKE only."),
                (branches_path, "legacy-branch-index", "LEGACY_BRANCH_LINEAGE", "Indexes historical branches without promoting them."),
            ],
        ))
    print(json.dumps({"portfolio": portfolio_run_id, "runs": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
