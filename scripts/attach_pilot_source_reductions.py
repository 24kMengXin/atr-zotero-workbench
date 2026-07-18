#!/usr/bin/env python3
"""Attach source-inspected pilot reductions without lifecycle transition."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PILOTS = {
    "multilingual-agent-action-attribution": [
        ("source-inspection-packet.json", "source-inspection-packet", "FULLTEXT_SOURCE_INSPECTION_REVIEW_ONLY", "SOURCE-INSPECTION"),
        ("opportunity-decision.json", "opportunity-decision", "R0_OPPORTUNITY_DECISION_REVIEW_ONLY", "OPPORTUNITY-DECISION"),
        ("problem-case.json", "problem-case", "DRAFT_PROBLEM_CASE_PENDING_REVIEW", "DRAFT-PROBLEM-CASE"),
        ("collision-review.json", "collision-review", "R0_COLLISION_REVIEW_WORKER_OUTPUT", "COLLISION-REVIEW"),
    ],
    "multilingual-agent-authorization-safety": [
        ("source-inspection-packet.json", "source-inspection-packet", "FULLTEXT_SOURCE_INSPECTION_REVIEW_ONLY", "SOURCE-INSPECTION"),
        ("opportunity-decision.json", "opportunity-decision", "R0_OPPORTUNITY_DECISION_REVIEW_ONLY", "OPPORTUNITY-DECISION"),
        ("problem-case.json", "problem-case", "DRAFT_PROBLEM_CASE_PENDING_REVIEW", "DRAFT-PROBLEM-CASE"),
        ("collision-review.json", "collision-review", "R0_COLLISION_REVIEW_WORKER_OUTPUT", "COLLISION-REVIEW"),
    ],
    "multilingual-representation-and-data-decisions": [
        ("source-inspection-packet.json", "source-inspection-packet", "FULLTEXT_SOURCE_INSPECTION_REVIEW_ONLY", "SOURCE-INSPECTION"),
        ("opportunity-map.json", "opportunity-map", "DRAFT_OPPORTUNITY_MAP_PENDING_REVIEW", "DRAFT-OPPORTUNITY-MAP"),
        ("problem-case.json", "problem-case", "DRAFT_PROBLEM_CASE_PENDING_REVIEW", "DRAFT-PROBLEM-CASE"),
        ("collision-review.json", "collision-review", "R0_COLLISION_REVIEW_WORKER_OUTPUT", "COLLISION-REVIEW"),
    ],
    "multilingual-agent-state-continuity": [
        ("source-inspection-packet.json", "source-inspection-packet", "FULLTEXT_SOURCE_INSPECTION_REVIEW_ONLY", "SOURCE-INSPECTION"),
        ("opportunity-map.json", "opportunity-map", "DRAFT_OPPORTUNITY_MAP_PENDING_REVIEW", "DRAFT-OPPORTUNITY-MAP"),
        ("problem-case.json", "problem-case", "DRAFT_PROBLEM_CASE_PENDING_REVIEW", "DRAFT-PROBLEM-CASE"),
        ("collision-review.json", "collision-review", "R0_COLLISION_REVIEW_WORKER_OUTPUT", "COLLISION-REVIEW"),
    ],
    "agent-infrastructure-and-evaluation-contracts": [
        ("source-inspection-packet.json", "source-inspection-packet", "FULLTEXT_SOURCE_INSPECTION_REVIEW_ONLY", "SOURCE-INSPECTION"),
        ("opportunity-map.json", "opportunity-map", "DRAFT_OPPORTUNITY_MAP_PENDING_REVIEW", "DRAFT-OPPORTUNITY-MAP"),
        ("problem-case.json", "problem-case", "DRAFT_PROBLEM_CASE_PENDING_REVIEW", "DRAFT-PROBLEM-CASE"),
        ("collision-review.json", "collision-review", "R0_COLLISION_REVIEW_WORKER_OUTPUT", "COLLISION-REVIEW"),
    ],
    "atr-research-governance": [
        ("source-inspection-packet.json", "source-inspection-packet", "FULLTEXT_SOURCE_INSPECTION_REVIEW_ONLY", "SOURCE-INSPECTION"),
        ("opportunity-decision.json", "opportunity-decision", "R0_OPPORTUNITY_DECISION_REVIEW_ONLY", "OPPORTUNITY-DECISION"),
        ("problem-case.json", "problem-case", "DRAFT_PROBLEM_CASE_PENDING_REVIEW", "DRAFT-PROBLEM-CASE"),
        ("collision-review.json", "collision-review", "R0_COLLISION_REVIEW_WORKER_OUTPUT", "COLLISION-REVIEW"),
    ],
}


def invoke(command: list[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def verify_packet(path: Path) -> None:
    packet = json.loads(path.read_text(encoding="utf-8"))
    for source in packet.get("sources", []):
        digest = source.get("content_digest", "")
        cache = source.get("local_cache_path")
        if not cache or not digest.startswith("sha256:"):
            continue
        cached_path = ROOT / cache
        actual = hashlib.sha256(cached_path.read_bytes()).hexdigest()
        if actual != digest.removeprefix("sha256:"):
            raise ValueError(f"digest mismatch for {cached_path}: {actual}")


def verify_collision_review(path: Path) -> None:
    review = json.loads(path.read_text(encoding="utf-8"))
    if review.get("status") != "CLAIM_SCOPED_POSTERIOR_REVIEW_NOT_GATE":
        raise ValueError(f"unsafe collision-review status: {path}")
    if review.get("disposition") not in {"REFRAME", "NEEDS_EVIDENCE"}:
        raise ValueError(f"unsupported collision-review disposition: {path}")
    for source in review.get("inspected_sources", []):
        cache = ROOT / source["local_cache_path"]
        actual = hashlib.sha256(cache.read_bytes()).hexdigest()
        if source.get("content_digest") != f"sha256:{actual}":
            raise ValueError(f"digest mismatch for {cache}: {actual}")


def current(run: Path, attachment_id: str) -> bool:
    with sqlite3.connect(run / "atr.sqlite") as conn:
        return conn.execute(
            "SELECT 1 FROM attachments WHERE attachment_id=?", (attachment_id,)
        ).fetchone() is not None


def authority_snapshot(run: Path, subject: str) -> dict:
    with sqlite3.connect(run / "atr.sqlite") as conn:
        state, version = conn.execute(
            "SELECT state, version FROM subjects WHERE subject_id=?", (subject,)
        ).fetchone()
        attachments = conn.execute(
            "SELECT COUNT(*) FROM attachments WHERE subject_id=?", (subject,)
        ).fetchone()[0]
    return {"state": state, "version": version, "attachment_count": attachments}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--atrctl", type=Path, required=True)
    args = parser.parse_args()
    output = []
    for program, artifacts in PILOTS.items():
        run_id = f"2026-07-19-{program}-v2-intake"
        run = args.runs_root.resolve() / run_id
        subject = f"program:{program}"
        before = authority_snapshot(run, subject)
        if before["state"] != "INTAKE" or before["version"] != 0:
            raise ValueError(f"refusing non-INTAKE authority: {program} {before}")
        attached = []
        pilot_root = ROOT / "programs" / "v2-intakes" / "pilot-reductions" / program
        verify_packet(pilot_root / "source-inspection-packet.json")
        for filename, kind, role, suffix in artifacts:
            path = pilot_root / filename
            if kind == "collision-review":
                verify_collision_review(path)
            attachment_id = f"ATT-{run_id}-{suffix}"
            if current(run, attachment_id):
                attached.append({"attachment_id": attachment_id, "status": "ALREADY_ATTACHED"})
                continue
            artifact_id = invoke([
                "python3", str(args.atrctl.resolve()), "ingest", str(run), str(path),
                "--kind", kind, "--scope", "R0 source reduction; review-only; no lifecycle authorization",
            ])
            invoke([
                "python3", str(args.atrctl.resolve()), "attach", str(run),
                "--subject", subject, "--expected-version", "0", "--artifact", artifact_id,
                "--role", role, "--attachment-id", attachment_id,
                "--note", "Source-inspected pilot reduction; independent review required; no transition.",
            ])
            attached.append({"attachment_id": attachment_id, "status": "ATTACHED", "artifact_id": artifact_id})
        check = json.loads(invoke(["python3", str(args.atrctl.resolve()), "check", str(run)]))
        if not check.get("pass"):
            raise ValueError(f"controller check failed for {program}: {check}")
        after = authority_snapshot(run, subject)
        if after["state"] != before["state"] or after["version"] != before["version"]:
            raise ValueError(f"attachment unexpectedly mutated lifecycle: {program} {before} -> {after}")
        output.append({"program": program, "before": before, "after": after, "attachments": attached})
    print(json.dumps({"pilots": output}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
