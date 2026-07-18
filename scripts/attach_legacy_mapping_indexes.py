#!/usr/bin/env python3
"""Attach verified legacy-mapping indexes to unchanged v2 subject versions."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import sys


PORTFOLIO_RUN_ID = "2026-07-19-multilingual-program-portfolio-v2"
PORTFOLIO_SUBJECT = "portfolio:multilingual-aaai"


def run_ctl(ctl: Path, *args: str) -> str:
    result = subprocess.run(
        [sys.executable, str(ctl), *args], capture_output=True, text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def active_subject(run_dir: Path) -> tuple[str, int, str]:
    with sqlite3.connect(run_dir / "atr.sqlite") as connection:
        row = connection.execute(
            "SELECT subject_id, version, state FROM subjects WHERE active=1"
        ).fetchone()
    if not row:
        raise ValueError(f"run has no active subject: {run_dir}")
    return str(row[0]), int(row[1]), str(row[2])


def has_attachment(run_dir: Path, attachment_id: str) -> bool:
    with sqlite3.connect(run_dir / "atr.sqlite") as connection:
        return connection.execute(
            "SELECT 1 FROM attachments WHERE attachment_id=?", (attachment_id,)
        ).fetchone() is not None


def attach(ctl: Path, run_dir: Path, index_path: Path, subject: str,
           expected_run_id: str) -> dict[str, str]:
    if run_dir.name != expected_run_id:
        raise ValueError(f"run directory mismatch: {run_dir} != {expected_run_id}")
    actual_subject, version, state = active_subject(run_dir)
    if actual_subject != subject:
        raise ValueError(f"subject mismatch in {run_dir}: {actual_subject} != {subject}")
    attachment_id = f"ATT-{expected_run_id}-LEGACY-MAPPING-INDEX-V1"
    if has_attachment(run_dir, attachment_id):
        return {"run_id": expected_run_id, "status": "ALREADY_ATTACHED", "state": state}
    artifact_id = run_ctl(
        ctl, "ingest", str(run_dir), str(index_path),
        "--kind", "legacy-mapping-index",
        "--scope", "explicit historical artifact sidecars; review and navigation only",
    )
    run_ctl(
        ctl, "attach", str(run_dir), "--subject", subject,
        "--expected-version", str(version), "--artifact", artifact_id,
        "--role", "LEGACY_MAPPING_INDEX_REVIEW_ONLY",
        "--attachment-id", attachment_id,
        "--note", "Declares exact legacy artifacts consumed by current alignment; no lifecycle, claim, gate, or route effect.",
    )
    after_subject, after_version, after_state = active_subject(run_dir)
    if (after_subject, after_version, after_state) != (actual_subject, version, state):
        raise ValueError(f"mapping attachment changed lifecycle authority: {run_dir}")
    return {"run_id": expected_run_id, "status": "ATTACHED", "state": state}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--mapping-root", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--ctl", type=Path, required=True)
    args = parser.parse_args()
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    mapping_root = args.mapping_root.resolve()
    index = json.loads((mapping_root / "legacy-mapping-index.json").read_text(encoding="utf-8"))
    results = [attach(
        args.ctl.resolve(), args.runs_root.resolve() / PORTFOLIO_RUN_ID,
        mapping_root / "legacy-mapping-index.json", PORTFOLIO_SUBJECT, PORTFOLIO_RUN_ID,
    )]
    by_program = {row["program_key"]: row for row in registry.get("children", [])}
    for program, relative in sorted(index["program_indexes"].items()):
        child = by_program.get(program)
        if not child:
            raise ValueError(f"mapping index has no registered child: {program}")
        results.append(attach(
            args.ctl.resolve(), args.runs_root.resolve() / child["run_id"],
            mapping_root / relative, child["subject_id"], child["run_id"],
        ))
    print(json.dumps({"attachments": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
