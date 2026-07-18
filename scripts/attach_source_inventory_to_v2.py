#!/usr/bin/env python3
"""Attach program-scoped canonical source queues to six ATR v2 children.

The attachment is metadata-only review input.  It does not transition a child,
assert attachment/full-text availability, or promote legacy interpretations.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
from typing import Any

def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def stable_write(path: Path, body: dict[str, Any]) -> None:
    encoded = json.dumps(body, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != encoded:
        raise ValueError(f"refusing to overwrite divergent source inventory attachment: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")


def invoke(command: list[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def attached(run: Path, attachment_id: str) -> bool:
    conn = sqlite3.connect(run / "atr.sqlite")
    try:
        return conn.execute("SELECT 1 FROM attachments WHERE attachment_id=?", (attachment_id,)).fetchone() is not None
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inventory", type=Path); parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--definitions-dir", type=Path, required=True); parser.add_argument("--atrctl", type=Path, required=True)
    parser.add_argument("--date", default="2026-07-19")
    args = parser.parse_args()
    inventory = args.inventory.resolve(); canonical = jsonl(inventory / "canonical-sources.jsonl")
    occurrences = jsonl(inventory / "source-occurrences.jsonl")
    programs = sorted({program for source in canonical for program in source.get("program_keys", [])})
    results = []
    for program in programs:
        program_sources = [source for source in canonical if program in source.get("program_keys", [])]
        canonical_ids = {source["canonical_source_id"] for source in program_sources}
        program_occurrences = [row for row in occurrences if row["canonical_source_id"] in canonical_ids and row["program_key"] == program]
        payload_sources = [{
            "source_id": source["canonical_source_id"], "title": source["title"], "url": source["url"],
            "kind": source["kind"], "access_status": source["access_status"], "access_route": source["access_route"],
            "supports": f"Historical inventory records {source['occurrence_count']} occurrence(s) across: " + ", ".join(source["runs"]),
            "does_not_establish": source["boundary"],
            "legacy_source_ids": source["legacy_source_ids"], "identity_review": source["identity_review"],
            "zotero_item_key": source["zotero_item_key"], "zotero_attachment_key": source["zotero_attachment_key"],
            "fulltext_attached": source["fulltext_attached"], "fulltext_inspected": source["fulltext_inspected"],
        } for source in program_sources]
        body = {
            "schema_version": "1.0", "artifact_type": "program-source-inventory", "program_key": program,
            "sources": payload_sources,
            "occurrence_count": len(program_occurrences), "canonical_source_count": len(program_sources),
            "identity_conflict_count": sum(source["identity_review"] != "EXACT_NORMALIZED_MATCH" for source in program_sources),
            "access_summary": {"metadata_only": len(program_sources), "fulltext_attached": 0, "fulltext_inspected": 0},
            "next_action": "Resolve/de-duplicate against the Zotero library, acquire permitted readable attachments, then inspect load-bearing spans with locators.",
            "controller_boundary": "This source inventory is an immutable metadata-only attachment. It does not itself advance lifecycle or establish bibliographic version identity, access, inspection, claim support, or a research gap.",
        }
        definition = args.definitions_dir.resolve() / program / "program-source-inventory.json"
        stable_write(definition, body)
        run_id = f"{args.date}-{program}-v2-intake"; run_dir = args.runs_root.resolve() / run_id
        subject = f"program:{program}"; attachment_id = f"ATT-{run_id}-SOURCE-INVENTORY"
        if attached(run_dir, attachment_id):
            results.append({"program": program, "attached": False, "reason": "ALREADY_ATTACHED"})
            continue
        artifact_id = invoke([
            "python3", str(args.atrctl.resolve()), "ingest", str(run_dir), str(definition),
            "--kind", "program-source-inventory", "--scope", "metadata-only source re-verification queue",
        ])
        invoke([
            "python3", str(args.atrctl.resolve()), "attach", str(run_dir),
            "--subject", subject, "--expected-version", "0", "--artifact", artifact_id,
            "--role", "SOURCE_REVERIFICATION_QUEUE", "--attachment-id", attachment_id,
            "--note", "Canonical bibliographic candidates; attachment and cited-span inspection remain pending.",
        ])
        check = json.loads(invoke(["python3", str(args.atrctl.resolve()), "check", str(run_dir)]))
        if not check.get("pass"):
            raise ValueError(f"controller check failed for {program}: {check}")
        results.append({"program": program, "attached": True, "artifact_id": artifact_id, "sources": len(program_sources)})
    print(json.dumps({"programs": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
