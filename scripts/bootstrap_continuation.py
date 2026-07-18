#!/usr/bin/env python3
"""Bootstrap a new ATR continuation run from a read-only program catalog.

The script intentionally imports provenance, not conclusions. It never moves
or edits a historical run, never promotes historical claims into the current
claim ledger, and refuses to overwrite a continuation that has started work.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--program", required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    catalog_path, target = args.catalog.resolve(), args.target.resolve()
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    program = next((row for row in catalog.get("programs", []) if row.get("key") == args.program), None)
    if not program:
        raise SystemExit(f"unknown program: {args.program}")
    state_path, sources_path = target / "run-state.json", target / "evidence" / "sources.jsonl"
    if not state_path.exists():
        raise SystemExit(f"not an initialized ATR run: {target}")
    if sources_path.exists() and sources_path.read_text(encoding="utf-8").strip():
        raise SystemExit("refusing to overwrite a continuation with existing source work")

    sources: dict[str, dict[str, Any]] = {}
    claim_history: list[dict[str, Any]] = []
    branch_records: list[dict[str, Any]] = []
    canonical_frontier: Path | None = None
    for branch in program.get("branches", []):
        run = (catalog_path.parent / branch["run"]).resolve()
        branch_records.append({"run": run.name, "path": str(run), "role": branch.get("role"), "disposition": branch.get("disposition")})
        for source in rows(run / "evidence" / "sources.jsonl"):
            source_id = source.get("source_id")
            if not source_id:
                continue
            if source_id not in sources:
                imported = dict(source)
                imported["historical_run_ids"] = [run.name]
                sources[source_id] = imported
            elif run.name not in sources[source_id]["historical_run_ids"]:
                sources[source_id]["historical_run_ids"].append(run.name)
        for claim in rows(run / "evidence" / "claims.jsonl"):
            claim_history.append({"historical_run": run.name, "claim": claim})
        if branch.get("disposition") == "canonical_frontier_branch":
            candidate = run / "knowledge" / "frontier-map.json"
            if candidate.exists():
                canonical_frontier = candidate

    sources_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for _, row in sorted(sources.items())), encoding="utf-8")
    migration = target / "migration"
    migration.mkdir(exist_ok=True)
    (migration / "historical-claims.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in claim_history), encoding="utf-8")
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    write_json(migration / "baseline.json", {
        "schema_version": "0.1", "artifact_type": "historical-program-baseline", "created_at": now,
        "program_key": program["key"], "program_label": program["label"], "root_question": program["root_question"],
        "catalog_path": str(catalog_path), "branches": branch_records,
        "source_count": len(sources), "historical_claim_count": len(claim_history),
        "invariant": "Imported sources and historical claims are provenance inputs, not current continuation conclusions.",
    })
    if canonical_frontier:
        frontier = json.loads(canonical_frontier.read_text(encoding="utf-8"))
        frontier["map_id"] = f"FKM-{program['key']}-continuation.v1"
        frontier["source_ledger_path"] = "evidence/sources.jsonl"
        write_json(target / "knowledge" / "frontier-map.json", frontier)
        write_json(migration / "frontier-provenance.json", {"source_run": canonical_frontier.parents[1].name, "source_path": str(canonical_frontier), "copied_at": now})

    state = json.loads(state_path.read_text(encoding="utf-8"))
    # Repair only the known initializer omissions on this newly created run;
    # this does not advance a gate or mutate any historical run.
    state["harness_release"] = "0.9.0"
    state.setdefault("gates", {}).setdefault("G2C-CONSTRUCTION", "PENDING")
    state["policy_features"]["knowledge_context_required"] = True
    state["next_action"] = "Create a source-grounded topic-routing package and knowledge-context from the imported frontier map; do not promote historical claims until an explicit current claim review. Then acquire real-world signals for an opportunity map and formulate a falsifiable research-problem card."
    state["updated_at"] = now
    write_json(state_path, state)
    intake = json.loads((target / "intake.json").read_text(encoding="utf-8"))
    intake["source_files"] = [str(catalog_path), str(migration / "baseline.json")]
    intake["constraints"] = {"historical_runs_read_only": True, "current_claim_ledger_starts_empty": True, "human_review_required_before_claim_promotion": True}
    write_json(target / "intake.json", intake)
    (target / "MISSING_ARTIFACTS.md").write_text("""# Required continuation artifacts\n\nThe following are intentionally absent and must be produced from new, source-grounded work:\n\n- `decisions/topic-routing-package.json`: choose the proportionate knowledge-building route.\n- `knowledge/knowledge-context-*.json`: auditable contraction from frontier tension to a current claim.\n- `knowledge/opportunity-map.json`: independently sourced real-world signals; no popularity proxy.\n- `knowledge/research-problem-cards/*.json`: competing worlds, discriminator, and minimum falsifier.\n- `evidence/claims.jsonl`: current claims only after explicit review; historical claims remain in `migration/`.\n- source locators and human review packets from Zotero.\n\nNo missing artifact may be backfilled by copying an AI summary or inferring a historical event.\n""", encoding="utf-8")
    print(json.dumps({"target": str(target), "sources_imported": len(sources), "historical_claims_preserved": len(claim_history), "frontier_imported": bool(canonical_frontier)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
