#!/usr/bin/env python3
"""Attach a portfolio-level route/history map without advancing lifecycle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
from typing import Any


def invoke(command: list[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def stable_write(path: Path, body: dict[str, Any]) -> None:
    encoded = json.dumps(body, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != encoded:
        raise ValueError(f"refusing to overwrite divergent portfolio route map: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audit", type=Path)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--definition", type=Path, required=True)
    parser.add_argument("--atrctl", type=Path, required=True)
    args = parser.parse_args()

    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    programs = []
    for program in audit.get("programs", []):
        programs.append({
            "program_key": program["key"],
            "label": program["label"],
            "child_run_id": f"2026-07-19-{program['key']}-v2-intake",
            "branches": [{
                "run": row["run"],
                "recorded_stage": row.get("state", {}).get("active_stage"),
                "alignment_disposition": row.get("alignment_disposition"),
                "integration_action": row.get("program_integration_action"),
                "source_count": row.get("counts", {}).get("sources", 0),
                "claim_count": row.get("counts", {}).get("claims", 0),
                "missing_for_current": row.get("not_sufficient_for_current_continuation", []),
            } for row in program.get("runs", [])],
        })
    body = {
        "schema_version": "1.0",
        "artifact_type": "portfolio-route-map",
        "portfolio_id": "multilingual-aaai-program-portfolio",
        "programs": programs,
        "history_policy": "Legacy branches remain visible as read-only provenance inputs; they never inherit authority into a v2 child.",
        "summary": {
            "program_count": len(programs),
            "legacy_branch_count": sum(len(program["branches"]) for program in programs),
        },
    }
    stable_write(args.definition, body)
    attachment_id = "ATT-2026-07-19-multilingual-program-portfolio-v2-ROUTE-MAP"
    connection = sqlite3.connect(args.run_dir / "atr.sqlite")
    try:
        exists = connection.execute(
            "SELECT 1 FROM attachments WHERE attachment_id=?", (attachment_id,)
        ).fetchone() is not None
    finally:
        connection.close()
    if exists:
        print(json.dumps({"attached": False, "reason": "ALREADY_ATTACHED"}, ensure_ascii=False))
        return
    artifact_id = invoke([
        "python3", str(args.atrctl), "ingest", str(args.run_dir), str(args.definition),
        "--kind", "portfolio-route-map", "--scope", "read-only portfolio navigation and historical lineage",
    ])
    invoke([
        "python3", str(args.atrctl), "attach", str(args.run_dir),
        "--subject", "portfolio:multilingual-aaai", "--expected-version", "0",
        "--artifact", artifact_id, "--role", "PORTFOLIO_ROUTE_AND_HISTORY_MAP",
        "--attachment-id", attachment_id,
        "--note", "Six v2 child authorities and 28 legacy branches; navigation only, no lifecycle transition.",
    ])
    check = json.loads(invoke(["python3", str(args.atrctl), "check", str(args.run_dir)]))
    if not check.get("pass"):
        raise ValueError(f"controller check failed: {check}")
    print(json.dumps({"attached": True, "artifact_id": artifact_id, "check": check}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
