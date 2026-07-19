#!/usr/bin/env python3
"""Attach verified repo-PDF-to-Zotero handoffs without changing v2 lifecycle."""
from __future__ import annotations
import argparse, hashlib, json, sqlite3, subprocess, sys
from pathlib import Path
from typing import Any


def ctl(path: Path, *args: str) -> str:
    result = subprocess.run([sys.executable, str(path), *args], capture_output=True, text=True)
    if result.returncode: raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def active(run: Path) -> tuple[str, int, str]:
    with sqlite3.connect(run / "atr.sqlite") as db:
        row = db.execute("SELECT subject_id,version,state FROM subjects WHERE active=1").fetchone()
    if not row: raise ValueError(f"no active subject: {run}")
    return str(row[0]), int(row[1]), str(row[2])


def persist(directory: Path, label: str, payload: dict[str, Any]) -> tuple[Path, str]:
    body = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    digest = hashlib.sha256(body.encode()).hexdigest()
    target = directory / f"{label}.{digest[:12]}.json"; target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.read_text(encoding="utf-8") != body: raise ValueError(f"divergent payload: {target}")
    target.write_text(body, encoding="utf-8")
    return target, digest


def attach(atrctl: Path, run: Path, subject: str, artifact: Path, digest: str) -> dict[str, Any]:
    actual, version, state = active(run)
    if actual != subject: raise ValueError(f"subject mismatch: {run}: {actual} != {subject}")
    attachment_id = f"ATT-{run.name}-REPO-PDF-HANDOFF-{digest[:12]}"
    with sqlite3.connect(run / "atr.sqlite") as db:
        exists = db.execute("SELECT 1 FROM attachments WHERE attachment_id=?", (attachment_id,)).fetchone()
    if exists: return {"run_id": run.name, "status": "ALREADY_ATTACHED", "state": state}
    artifact_id = ctl(atrctl, "ingest", str(run), str(artifact), "--kind", "repo-pdf-zotero-handoff-audit",
                      "--scope", "verified repo PDF; Zotero copy only on explicit human open")
    ctl(atrctl, "attach", str(run), "--subject", subject, "--expected-version", str(version),
        "--artifact", artifact_id, "--role", "REPO_PDF_ZOTERO_HANDOFF_REVIEW_ONLY",
        "--attachment-id", attachment_id,
        "--note", "Identity/digest handoff permits explicit-open stored copy only; no lifecycle or scholarly effect.")
    if active(run) != (actual, version, state): raise ValueError(f"handoff changed authority: {run}")
    check = json.loads(ctl(atrctl, "check", str(run)))
    if not check.get("pass"): raise ValueError(f"controller check failed: {run}")
    return {"run_id": run.name, "status": "ATTACHED", "state": state, "artifact_id": artifact_id}


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("audit", type=Path)
    parser.add_argument("--registry", type=Path, required=True); parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--definitions-dir", type=Path, required=True); parser.add_argument("--atrctl", type=Path, required=True)
    args = parser.parse_args(); audit = json.loads(args.audit.read_text(encoding="utf-8"))
    registry = json.loads(args.registry.read_text(encoding="utf-8")); handoffs = audit["handoffs"]
    common = {"schema_version": "1.0", "artifact_type": "repo-pdf-zotero-handoff-audit",
              "captured_at": audit["generated_at"], "policy": audit["policy"],
              "controller_boundary": "This operational handoff can only authorize a stored copy after explicit human open. It cannot create evidence, inspection, claim support, gate, route, or lifecycle change."}
    portfolio = {**common, "scope": "portfolio", "summary": audit["summary"], "handoffs": []}
    path, digest = persist(args.definitions_dir.resolve(), "portfolio", portfolio)
    results = [attach(args.atrctl.resolve(), args.runs_root.resolve() / "2026-07-19-multilingual-program-portfolio-v2",
                      "portfolio:multilingual-aaai", path, digest)]
    for child in registry["children"]:
        program = child["program_key"]; workspace = program + "-v2-intake"
        rows = [row for row in handoffs if row["program_workspace"] == workspace]
        payload = {**common, "scope": "program", "program_key": program,
                   "summary": {"repo_cached_pdfs": len(rows),
                               "import_ready": sum(row["status"] == "IMPORT_READY" for row in rows),
                               "blocked": sum(row["status"] != "IMPORT_READY" for row in rows)},
                   "handoffs": rows}
        path, digest = persist(args.definitions_dir.resolve(), program, payload)
        results.append(attach(args.atrctl.resolve(), args.runs_root.resolve() / child["run_id"],
                              child["subject_id"], path, digest))
    print(json.dumps({"attachments": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
