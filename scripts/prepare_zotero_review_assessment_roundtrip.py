#!/usr/bin/env python3
"""Prepare phase 3 of the repo-local Zotero co-creation smoke.

This clones the real v2 authority into `.runtime`, records a synthetic owner
disposition and isolated assessment for an existing smoke packet, rebuilds the
projection in place, and disables creation of further smoke feedback. It never
mutates the real research run or claims that the synthetic fixture is
scholarly evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / ".runtime" / "zotero-smoke"
WORKSPACE = RUNTIME / "workspace"
CLONE = RUNTIME / "review-v2-run"
ASSESSMENT = RUNTIME / "review-assessment-input.json"
ATRCTL = ROOT.parents[1] / "multilingual-aaai" / "auto-research-harness" / "v2" / "atrctl.py"

sys.path.insert(0, str(ROOT / "src"))
from atr_zotero_workbench.app import build  # noqa: E402
from atr_zotero_workbench.human_input import attach_review_assessment_to_v2  # noqa: E402


def run(*args: str) -> str:
    result = subprocess.run([sys.executable, str(ATRCTL), *args], text=True, capture_output=True)
    if result.returncode:
        raise SystemExit(result.stderr.strip() or result.stdout.strip() or "atrctl failed")
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="replace only .runtime/zotero-smoke/review-v2-run")
    args = parser.parse_args()
    if not ATRCTL.is_file():
        raise SystemExit(f"missing v2 controller: {ATRCTL}")
    packets = sorted((WORKSPACE / "human-input" / "review-packets").glob("HRP-*.json"))
    selected = next((path for path in packets if json.loads(path.read_text())["review"]["target_type"] == "research_problem"), None)
    if not selected:
        raise SystemExit("run the first Zotero smoke phase before preparing the assessment roundtrip")
    registry = json.loads((ROOT / "output" / "runs.json").read_text())
    active = next(row for row in registry["runs"] if row["key"] == registry["active_run"])
    source_run = Path(active["run_dir"])
    if not (source_run / "atr.sqlite").is_file():
        raise SystemExit("active Zotero run is not a v2 SQLite authority")
    if CLONE.exists():
        if not args.reset:
            raise SystemExit(f"review clone exists: {CLONE}; pass --reset to replace it")
        shutil.rmtree(CLONE)
    shutil.copytree(source_run, CLONE)
    source_digest = hashlib.sha256((source_run / "atr.sqlite").read_bytes()).hexdigest()
    conn = sqlite3.connect(CLONE / "atr.sqlite")
    subject_id, version, state = conn.execute(
        "SELECT subject_id,version,state FROM subjects WHERE active=1"
    ).fetchone()
    conn.close()
    packet = json.loads(selected.read_text())
    run(
        "record-human-disposition", str(CLONE), "--subject", subject_id,
        "--expected-version", str(version), "--packet", str(selected),
        "--disposition", "OPEN_CLAIM_REVIEW", "--owner", "repository-smoke-owner",
        "--rationale", "Synthetic repository-local UI smoke only; open review without making a scholarly or lifecycle judgment.",
    )
    conn = sqlite3.connect(CLONE / "atr.sqlite")
    disposition_id = conn.execute(
        "SELECT disposition_id FROM human_review_dispositions WHERE packet_id=?", (packet["packet_id"],)
    ).fetchone()[0]
    conn.close()
    graph = json.loads((WORKSPACE / "graph.json").read_text())
    problem_id = packet["review"]["graph_node_id"]
    preserve = sorted({
        edge["target"] if edge["source"] == problem_id else edge["source"]
        for edge in graph.get("edges", [])
        if problem_id in {edge.get("source"), edge.get("target")}
        and (edge["target"] if edge["source"] == problem_id else edge["source"]).startswith("paper:")
    })
    assessment_id = "HRA-SMOKE-" + hashlib.sha256((packet["packet_id"] + "\0" + disposition_id).encode()).hexdigest()[:12]
    assessment = {
        "schema_version": "1.0",
        "artifact_type": "human-review-assessment",
        "assessment_id": assessment_id,
        "packet_id": packet["packet_id"],
        "disposition_id": disposition_id,
        "reviewed_at": packet.get("created_from", {}).get("observed_at") or "2026-07-18T00:00:00Z",
        "reviewer": {
            "id": "repository-smoke-isolated-reviewer",
            "role": "evidence_reviewer",
            "isolated_from_disposition_owner": True,
        },
        "finding": "Synthetic UI smoke: preserve every linked source and request a separately authored evidence review; no scholarly conclusion is made.",
        "outcome": "REQUEST_EVIDENCE",
        "evidence_basis": [{
            "kind": "HUMAN_REVIEW_PACKET",
            "ref": packet["packet_id"],
            "locator": "Repository-local generated Zotero Note stance",
            "observation": "The feedback bridge produced a problem-scoped packet and nearest-root impact path.",
            "does_not_establish": "This generated smoke input establishes neither source correctness, problem validity, novelty, nor any lifecycle verdict.",
        }],
        "impact": {
            "preserve_object_ids": preserve,
            "reconsider_object_ids": [problem_id],
        },
        "required_followup_artifact_kind": "evidence-review",
        "controller_boundary": "This assessment does not itself modify a claim, problem, route, gate, source record, lifecycle state, or historical projection. A separately authored typed artifact and controller action are required.",
    }
    ASSESSMENT.write_text(json.dumps(assessment, ensure_ascii=False, indent=2), encoding="utf-8")
    bridge = attach_review_assessment_to_v2(
        WORKSPACE, CLONE, ASSESSMENT, subject_id, version, ATRCTL,
    )
    build(CLONE, WORKSPACE)
    profile_user = RUNTIME / "profile" / "user.js"
    with profile_user.open("a", encoding="utf-8") as handle:
        handle.write('user_pref("extensions.atr-zotero-workbench.devSmokeFeedbackOnStartup", false);\n')
        handle.write('user_pref("extensions.atr-zotero-workbench.devSmokeReaderAnnotationOnStartup", false);\n')
    metadata = {
        "schema_version": "0.1",
        "mode": "REPOSITORY_LOCAL_SYNTHETIC_REVIEW_ROUNDTRIP",
        "source_run": str(source_run),
        "source_sqlite_sha256_before": source_digest,
        "clone": str(CLONE),
        "subject": {"id": subject_id, "version_before": version, "state_before": state},
        "packet_id": packet["packet_id"],
        "disposition_id": disposition_id,
        "assessment": bridge,
        "scientific_boundary": "UI/transaction code-path smoke only; not research evidence or an owner judgment.",
    }
    (RUNTIME / "review-roundtrip-metadata.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
