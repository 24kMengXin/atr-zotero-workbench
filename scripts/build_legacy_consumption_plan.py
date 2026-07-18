#!/usr/bin/env python3
"""Declare the exact multilingual legacy artifacts consumed by current v2 work.

This builder is research-specific policy.  It creates a reviewable plan for the
generic harness `v2/legacy_map.py`; it does not write manifests, edit historical
runs, or attach anything to a controller authority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from typing import Any


PORTFOLIO_RUN = "2026-07-19-multilingual-program-portfolio-v2"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def nonempty(path: Path) -> bool:
    return path.is_file() and bool(path.read_text(encoding="utf-8").strip())


def stage_from_state(path: Path) -> str:
    state = load(path)
    active = str(state.get("active_stage") or "R0")
    match = re.match(r"^(R4V|R[0-9])(?:_|$)", active)
    return match.group(1) if match else "R0"


def entry_key(relative: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", relative.casefold()).strip("-")


def build(catalog_path: Path, registry_path: Path, source_root: Path) -> dict[str, Any]:
    catalog = load(catalog_path)
    registry = load(registry_path)
    registry_rows = registry.get("children") or registry.get("programs") or []
    current_by_program = {
        row["program_key"]: row["run_id"] for row in registry_rows
    }
    entries = []

    def add(*, run: Path, program: str, current: str, stage: str, relative: str,
            artifact_type: str, decision: str, boundary: str, extra_consumers=()) -> None:
        path = run / relative if relative != "." else run
        if not path.exists():
            raise ValueError(f"declared consumed legacy artifact is missing: {path}")
        consumers = [
            "historical-program-alignment-audit:v0.2",
            PORTFOLIO_RUN,
            current,
            *extra_consumers,
        ]
        entries.append({
            "entry_key": entry_key("run-snapshot" if relative == "." else relative),
            "run_id": run.name,
            "program_key": program,
            "current_run_id": current,
            "stage": stage,
            "path": run.relative_to(source_root).as_posix() if relative == "." else path.relative_to(source_root).as_posix(),
            "artifact_type": artifact_type,
            "status": "ARCHIVED",
            "decision": decision,
            "boundary": boundary,
            "produced_by": [f"legacy-run:{run.name}"],
            "consumed_by": list(dict.fromkeys(consumers)),
            "claim_versions": [],
            "evidence_cutoff": None,
            "limitations": [
                boundary,
                "Legacy stage, gate, claim, and route records have no current lifecycle authority.",
                "A matching digest proves byte identity only; it does not prove source access, full-text inspection, or scholarly correctness.",
            ],
        })

    seen_runs = set()
    for program in catalog.get("programs", []):
        key = program["key"]
        current = current_by_program.get(key)
        if not current:
            raise ValueError(f"program has no registered current v2 child: {key}")
        for branch in program.get("branches", []):
            run = (catalog_path.parent / branch["run"]).resolve()
            if not run.is_dir() or not run.is_relative_to(source_root):
                raise ValueError(f"legacy run is outside source root: {run}")
            if run.name in seen_runs:
                raise ValueError(f"legacy run assigned to more than one program: {run.name}")
            seen_runs.add(run.name)
            stage = stage_from_state(run / "run-state.json")
            add(run=run, program=key, current=current, stage=stage, relative=".", artifact_type="MAN",
                decision="STRUCTURAL_INTEGRITY_INPUT_ONLY",
                boundary="Whole-run snapshot is consumed only to reproduce structural-check results; no contained artifact is thereby promoted.")
            add(run=run, program=key, current=current, stage=stage, relative="run-state.json", artifact_type="MAN",
                decision="RETAIN_AS_LEGACY_STATE_SNAPSHOT",
                boundary="Historical lifecycle snapshot is navigation context only and must not be copied into v2 state.")
            add(run=run, program=key, current=current, stage=stage, relative="evidence/sources.jsonl", artifact_type="SRC",
                decision="REUSE_AFTER_SOURCE_REVERIFICATION",
                boundary="Historical metadata/abstract interpretations are identity candidates; current use requires deduplication, access state, and located source review.",
                extra_consumers=("multilingual-source-inventory:v1.0",))
            if (run / "evidence" / "edges.jsonl").is_file():
                add(run=run, program=key, current=current, stage=stage, relative="evidence/edges.jsonl", artifact_type="MAN",
                    decision="RETAIN_AS_LEGACY_PROVENANCE",
                    boundary="Legacy edge semantics remain historical until explicitly remapped to typed current relations.")
            if nonempty(run / "evidence" / "claims.jsonl"):
                add(run=run, program=key, current=current, stage=stage, relative="evidence/claims.jsonl", artifact_type="CLM",
                    decision="RETAIN_AS_CLAIM_HISTORY",
                    boundary="Legacy claims remain historical and require a new version plus claim-scoped review before current use.")
            optional = [
                ("knowledge/frontier-map.json", "MAP", "REUSE_AS_HISTORICAL_FRONTIER_INPUT",
                 "Historical frontier framing is review input only; current use requires refreshed sources and a new bounded map."),
                ("knowledge/opportunity-map.json", "OCM", "REUSE_AS_R0_5_INPUT_ONLY",
                 "Historical real-world signals are inspiration only, not a gap, novelty, route, or lifecycle certificate."),
                ("knowledge/concept-map.json", "MAP", "RETAIN_AS_LEGACY_CONCEPT_INPUT",
                 "Historical concepts are not a source-reviewed current knowledge hierarchy."),
            ]
            for relative, artifact_type, decision, boundary in optional:
                if (run / relative).is_file():
                    add(run=run, program=key, current=current, stage=stage, relative=relative,
                        artifact_type=artifact_type, decision=decision, boundary=boundary)
            for path in sorted((run / "knowledge").glob("knowledge-context*.json")):
                add(run=run, program=key, current=current, stage=stage,
                    relative=path.relative_to(run).as_posix(), artifact_type="MAP",
                    decision="RETAIN_AS_LEGACY_KNOWLEDGE_CONTEXT",
                    boundary="Legacy contraction/context is preserved for review and cannot serve as a canonical current knowledge context.")
            cards = run / "knowledge" / "research-problem-cards"
            if cards.is_dir():
                for path in sorted(cards.glob("*.json")):
                    add(run=run, program=key, current=current, stage=stage,
                        relative=path.relative_to(run).as_posix(), artifact_type="QST",
                        decision="RETAIN_AS_LEGACY_PROBLEM_HISTORY",
                        boundary="Historical problem wording is not a current problem-case or gate result.")
            if nonempty(run / "observability" / "skill-events.jsonl"):
                add(run=run, program=key, current=current, stage=stage,
                    relative="observability/skill-events.jsonl", artifact_type="MAN",
                    decision="RETAIN_AS_PROCESS_HISTORY",
                    boundary="Unpaired v1 process events remain visible history and are excluded from exact invocation/token claims.")

    return {
        "schema_version": "1.0",
        "mapping_id": "multilingual-aaai-legacy-consumption-v1",
        "source_root": str(source_root),
        "policy": {
            "legacy_runs_are_read_only": True,
            "only_declared_artifacts_are_consumed": True,
            "no_lifecycle_effect": True,
            "unclassified_material": "ARCHIVE_PENDING_ARTIFACT_LEVEL_REVIEW",
        },
        "expected_run_count": len(seen_runs),
        "entries": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    payload = build(
        args.catalog.resolve(), args.registry.resolve(), args.source_root.resolve()
    )
    if payload["expected_run_count"] != 28:
        raise ValueError(f"expected 28 historical runs, found {payload['expected_run_count']}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out.exists() and args.out.read_text(encoding="utf-8") != text:
        raise ValueError(f"refusing to overwrite divergent consumption plan: {args.out}")
    args.out.write_text(text, encoding="utf-8")
    print(json.dumps({"runs": payload["expected_run_count"], "entries": len(payload["entries"])}, sort_keys=True))


if __name__ == "__main__":
    main()
