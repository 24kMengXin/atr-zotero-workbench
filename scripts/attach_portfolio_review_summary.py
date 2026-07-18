#!/usr/bin/env python3
"""Attach a read-only six-program collision-review summary to the portfolio."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PROGRAMS = [
    "multilingual-agent-action-attribution",
    "multilingual-agent-authorization-safety",
    "multilingual-representation-and-data-decisions",
    "multilingual-agent-state-continuity",
    "agent-infrastructure-and-evaluation-contracts",
    "atr-research-governance",
]


def invoke(command: list[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-run", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--atrctl", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    counts = {"REFRAME": 0, "NEEDS_EVIDENCE": 0}
    for key in PROGRAMS:
        path = ROOT / "programs" / "v2-intakes" / "pilot-reductions" / key / "collision-review.json"
        review = json.loads(path.read_text(encoding="utf-8"))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        child = args.runs_root / f"2026-07-19-{key}-v2-intake"
        with sqlite3.connect(child / "atr.sqlite") as connection:
            attached = connection.execute(
                "SELECT 1 FROM artifacts JOIN attachments USING(artifact_id) WHERE artifacts.digest=? AND attachments.role=?",
                (digest, "R0_COLLISION_REVIEW_WORKER_OUTPUT"),
            ).fetchone()
        if not attached:
            raise ValueError(f"child review is not attached to authority: {key}")
        disposition = review["disposition"]
        counts[disposition] += 1
        rows.append({
            "program_key": key,
            "child_run_id": f"2026-07-19-{key}-v2-intake",
            "collision_review_artifact_id": review["artifact_id"],
            "collision_review_digest": f"sha256:{digest}",
            "status": review["status"],
            "disposition": disposition,
            "surviving_boundary": review["surviving_boundary"],
            "next_evidence": review["next_evidence"],
        })
    body = {
        "schema_version": "1.0",
        "artifact_type": "portfolio-review-summary",
        "artifact_id": "ARH-MULTILINGUAL-PORTFOLIO-R0-COLLISION-SUMMARY-001.v1",
        "portfolio_id": "multilingual-aaai-program-portfolio",
        "programs": rows,
        "summary": {**counts, "program_count": len(rows)},
        "does_not_authorize": "This derived portfolio summary does not establish novelty, replace child artifacts, pass a gate, choose a route, or mutate any child lifecycle.",
    }
    target = ROOT / "programs" / "v2-intakes" / "portfolio-review-summary.json"
    rendered = json.dumps(body, ensure_ascii=False, indent=2) + "\n"
    if target.exists() and target.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"refusing divergent summary: {target}")
    target.write_text(rendered, encoding="utf-8")
    attachment_id = "ATT-2026-07-19-multilingual-program-portfolio-v2-COLLISION-SUMMARY"
    with sqlite3.connect(args.portfolio_run / "atr.sqlite") as connection:
        before = connection.execute("SELECT state,version FROM subjects WHERE subject_id=?", ("portfolio:multilingual-aaai",)).fetchone()
        exists = connection.execute("SELECT 1 FROM attachments WHERE attachment_id=?", (attachment_id,)).fetchone()
    if not exists:
        artifact_id = invoke(["python3", str(args.atrctl), "ingest", str(args.portfolio_run), str(target), "--kind", "portfolio-review-summary", "--scope", "derived navigation summary; child collision reviews remain authoritative"])
        invoke(["python3", str(args.atrctl), "attach", str(args.portfolio_run), "--subject", "portfolio:multilingual-aaai", "--expected-version", "0", "--artifact", artifact_id, "--role", "PORTFOLIO_COLLISION_REVIEW_SUMMARY", "--attachment-id", attachment_id, "--note", "Six child posterior reviews summarized for navigation; not a gate or route decision."])
    check = json.loads(invoke(["python3", str(args.atrctl), "check", str(args.portfolio_run)]))
    with sqlite3.connect(args.portfolio_run / "atr.sqlite") as connection:
        after = connection.execute("SELECT state,version FROM subjects WHERE subject_id=?", ("portfolio:multilingual-aaai",)).fetchone()
    if not check.get("pass") or before != after or after != ("INTAKE", 0):
        raise ValueError({"before": before, "after": after, "check": check})
    print(json.dumps({"status": "ATTACHED" if not exists else "ALREADY_ATTACHED", "summary": counts, "authority": after, "check": check}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
