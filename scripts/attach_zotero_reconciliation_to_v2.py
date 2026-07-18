#!/usr/bin/env python3
"""Attach a digest-versioned, read-only Zotero availability audit to v2 runs."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any


def ctl(path: Path, *args: str) -> str:
    result = subprocess.run([sys.executable, str(path), *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def active(run: Path) -> tuple[str, int, str]:
    with sqlite3.connect(run / "atr.sqlite") as db:
        row = db.execute("SELECT subject_id,version,state FROM subjects WHERE active=1").fetchone()
    if not row:
        raise ValueError(f"no active subject: {run}")
    return str(row[0]), int(row[1]), str(row[2])


def attached(run: Path, attachment_id: str) -> bool:
    with sqlite3.connect(run / "atr.sqlite") as db:
        return db.execute("SELECT 1 FROM attachments WHERE attachment_id=?", (attachment_id,)).fetchone() is not None


def stable_payload(path: Path, payload: dict[str, Any]) -> tuple[Path, str]:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    target = path / f"{payload.get('program_key') or 'portfolio'}.{digest[:12]}.json"
    if target.exists() and target.read_text(encoding="utf-8") != encoded:
        raise ValueError(f"digest collision or divergent reconciliation payload: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(encoded, encoding="utf-8")
    return target, digest


def attach_one(atrctl: Path, run: Path, subject: str, artifact: Path, digest: str) -> dict[str, Any]:
    actual_subject, version, state = active(run)
    if actual_subject != subject:
        raise ValueError(f"subject mismatch: {run}: {actual_subject} != {subject}")
    attachment_id = f"ATT-{run.name}-ZOTERO-LOCAL-RECON-{digest[:12]}"
    if attached(run, attachment_id):
        return {"run_id": run.name, "status": "ALREADY_ATTACHED", "state": state}
    artifact_id = ctl(atrctl, "ingest", str(run), str(artifact),
                      "--kind", "zotero-local-source-reconciliation",
                      "--scope", "read-only local availability audit; not inspection or evidence")
    ctl(atrctl, "attach", str(run), "--subject", subject, "--expected-version", str(version),
        "--artifact", artifact_id, "--role", "ZOTERO_LOCAL_AVAILABILITY_REVIEW_ONLY",
        "--attachment-id", attachment_id,
        "--note", "Exact Zotero item/PDF availability only; title candidates and scholarly inspection remain unresolved.")
    after = active(run)
    if after != (actual_subject, version, state):
        raise ValueError(f"availability attachment changed lifecycle authority: {run}")
    check = json.loads(ctl(atrctl, "check", str(run)))
    if not check.get("pass"):
        raise ValueError(f"controller check failed: {run}: {check}")
    return {"run_id": run.name, "status": "ATTACHED", "state": state, "artifact_id": artifact_id}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path); parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True); parser.add_argument("--definitions-dir", type=Path, required=True)
    parser.add_argument("--atrctl", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    sources = report["sources"]
    matches = [row for row in sources if row["identity_status"] != "NOT_FOUND_IN_ZOTERO"]
    common = {"schema_version": "1.0", "artifact_type": "zotero-local-source-reconciliation",
              "captured_at": report["generated_at"], "policy": report["policy"],
              "controller_boundary": "Local Zotero availability is review-only. It cannot establish FULLTEXT_INSPECTED, claim support, a gate, a route, or a lifecycle transition."}
    portfolio_payload = {**common, "scope": "portfolio", "summary": report["summary"],
                         "matches": [], "program_summaries": report["summary"]["programs"]}
    artifact, digest = stable_payload(args.definitions_dir.resolve(), portfolio_payload)
    results = [attach_one(args.atrctl.resolve(), args.runs_root.resolve() / "2026-07-19-multilingual-program-portfolio-v2",
                          "portfolio:multilingual-aaai", artifact, digest)]
    for child in registry["children"]:
        program = child["program_key"]
        program_matches = [{**row, "source_id": row["canonical_source_id"]}
                           for row in matches if program in row.get("program_keys", [])]
        payload = {**common, "scope": "program", "program_key": program,
                   "summary": report["summary"]["programs"][program], "matches": program_matches}
        artifact, digest = stable_payload(args.definitions_dir.resolve(), payload)
        results.append(attach_one(args.atrctl.resolve(), args.runs_root.resolve() / child["run_id"],
                                  child["subject_id"], artifact, digest))
    print(json.dumps({"attachments": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
