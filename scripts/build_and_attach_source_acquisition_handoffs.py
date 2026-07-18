#!/usr/bin/env python3
"""Build and attach identity-verified local-PDF handoffs for collision sources."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
import sqlite3
import subprocess


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".runtime" / "collision-review"
OUT = ROOT / "programs" / "v2-intakes" / "pilot-reductions"
SOURCES = {
    "multilingual-agent-action-attribution": [
        ("SRC-UNITOOLCALL-2026", "UniToolCall: Unified Tool Calling via Question-Answer-Observation-Answer", "2604.11557", "https://arxiv.org/abs/2604.11557", "https://arxiv.org/pdf/2604.11557", "unitoolcall.pdf", "OPEN_REPOSITORY"),
    ],
    "multilingual-agent-authorization-safety": [
        ("SRC-VERIFIABLY-SAFE-TOOL-USE-2026", "Towards Verifiably Safe Tool Use for LLM Agents", "2601.08012", "https://arxiv.org/abs/2601.08012", "https://arxiv.org/pdf/2601.08012", "safe-tool-use.pdf", "OPEN_REPOSITORY"),
    ],
    "multilingual-representation-and-data-decisions": [
        ("SRC-AI-ASSISTED-MT-EVAL-2024", "AI-Assisted Human Evaluation of Machine Translation", "2406.12419", "https://arxiv.org/abs/2406.12419", "https://arxiv.org/pdf/2406.12419", "ai-assisted-mt-eval.pdf", "OPEN_REPOSITORY"),
    ],
    "multilingual-agent-state-continuity": [
        ("SRC-STATEFUL-TOOL-USE-2025", "Rethinking Stateful Tool Use in Multi-Turn LLM Agents", "2025.findings-acl.1249", "https://aclanthology.org/2025.findings-acl.1249/", "https://aclanthology.org/2025.findings-acl.1249.pdf", "stateful-tool-use.pdf", "EXPLICIT_PDF_URL"),
    ],
    "agent-infrastructure-and-evaluation-contracts": [
        ("SRC-HARNESS-BENCH-2026", "Harness-Bench: Evaluating Agent Harnesses for Large Language Models", "2605.27922", "https://arxiv.org/abs/2605.27922", "https://arxiv.org/pdf/2605.27922", "harness-bench.pdf", "OPEN_REPOSITORY"),
        ("SRC-AGENTEVAL-2026", "AgentEval: A Step-Level Evaluation Framework for LLM Agents", "2604.23581", "https://arxiv.org/abs/2604.23581", "https://arxiv.org/pdf/2604.23581", "agent-eval.pdf", "OPEN_REPOSITORY"),
    ],
    "atr-research-governance": [
        ("SRC-LLM-AUDIT-TRAILS-2026", "Audit Trails for Accountability in Large Language Models", "2601.20727", "https://arxiv.org/abs/2601.20727", "https://arxiv.org/pdf/2601.20727", "audit-trails.pdf", "OPEN_REPOSITORY"),
    ],
}
STOP = {"the", "a", "an", "of", "for", "in", "on", "via", "to", "and", "with"}


def invoke(command: list[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def title_tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 2 and token not in STOP}


def verified_source(row: tuple[str, str, str, str, str, str, str], collision: dict) -> dict:
    source_id, title, identifier, url, pdf_url, filename, access_route = row
    path = CACHE / filename
    first_page = invoke(["pdftotext", "-f", "1", "-l", "1", str(path), "-"])
    expected = title_tokens(title)
    observed = title_tokens(first_page[:5000])
    matched = expected & observed
    if len(matched) < max(3, int(len(expected) * 0.6)):
        raise ValueError(f"PDF identity mismatch for {source_id}: matched={sorted(matched)} expected={sorted(expected)}")
    collision_source = next(item for item in collision["inspected_sources"] if item["source_id"] == source_id)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if collision_source["content_digest"] != f"sha256:{digest}":
        raise ValueError(f"collision digest mismatch: {source_id}")
    if identifier not in url or identifier not in pdf_url:
        raise ValueError(f"canonical identifier missing from acquisition endpoints: {source_id}")
    return {
        "source_id": source_id,
        "title": title,
        "url": url,
        "pdf_url": pdf_url,
        "kind": "PRIMARY_PAPER",
        "source_function": "SCIENTIFIC_FRONTIER",
        "content_form": "PDF",
        "content_digest": f"sha256:{digest}",
        "local_cache_state": "REPO_RUNTIME_CACHE_NOT_ZOTERO_ATTACHMENT",
        "local_cache_path": str(path.relative_to(ROOT)),
        "cache_role": "VERIFIED_ACQUISITION_CACHE",
        "identity_state": "IDENTITY_VERIFIED",
        "identity_evidence": [
            {"signal": "CANONICAL_IDENTIFIER_IN_LANDING_AND_PDF_ENDPOINT", "value": identifier},
            {"signal": "FIRST_PAGE_TITLE_TOKEN_MATCH", "matched": sorted(matched), "expected_token_count": len(expected)},
            {"signal": "BYTE_IDENTITY", "value": f"sha256:{digest}"},
        ],
        "access_status": "EXPLICIT_OPEN_PDF",
        "access_route": access_route,
        "local_cache_import_policy": "ALLOW_ZOTERO_STORED_COPY_ON_EXPLICIT_READ",
        "zotero_attachment_state": "NOT_ATTACHED_AT_ARTIFACT_CREATION",
        "fulltext_state": "FULLTEXT_INSPECTED_BY_WORKER_NOT_HUMAN",
        "inspection_spans": [{
            "locator": collision_source["locator"],
            "observation": collision_source["finding"],
            "does_not_establish": collision_source["does_not_establish"],
        }],
        "does_not_establish": collision_source["does_not_establish"],
    }


def stable_write(path: Path, body: dict) -> None:
    rendered = json.dumps(body, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"refusing divergent handoff: {path}")
    path.write_text(rendered, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--atrctl", type=Path, required=True)
    args = parser.parse_args()
    reports = []
    for program, source_rows in SOURCES.items():
        root = OUT / program
        collision = json.loads((root / "collision-review.json").read_text(encoding="utf-8"))
        sources = [verified_source(row, collision) for row in source_rows]
        slug = program.upper().replace("-", "-")
        body = {
            "artifact_type": "source-acquisition-handoff",
            "schema_version": "1.0",
            "artifact_id": f"ARH-{slug}-R0-SRC-002.v1",
            "program_key": program,
            "input_collision_review_id": collision["artifact_id"],
            "sources": sources,
            "handoff_policy": "Zotero may create a stored child attachment only after an explicit human read action; runtime item/attachment keys remain outside this immutable artifact.",
            "does_not_authorize": "Identity and byte verification do not establish cited-version equivalence, human inspection, claim support, novelty, a route, or a lifecycle transition.",
        }
        target = root / "source-acquisition-handoff.json"
        stable_write(target, body)
        run = args.runs_root / f"2026-07-19-{program}-v2-intake"
        subject = f"program:{program}"
        attachment_id = f"ATT-2026-07-19-{program}-v2-intake-SOURCE-ACQUISITION-HANDOFF"
        with sqlite3.connect(run / "atr.sqlite") as connection:
            before = connection.execute("SELECT state,version FROM subjects WHERE subject_id=?", (subject,)).fetchone()
            exists = connection.execute("SELECT 1 FROM attachments WHERE attachment_id=?", (attachment_id,)).fetchone()
        if not exists:
            artifact_id = invoke(["python3", str(args.atrctl), "ingest", str(run), str(target), "--kind", "source-acquisition-handoff", "--scope", "identity-verified Zotero stored-copy handoff; explicit read only"])
            invoke(["python3", str(args.atrctl), "attach", str(run), "--subject", subject, "--expected-version", "0", "--artifact", artifact_id, "--role", "SOURCE_ACQUISITION_TO_ZOTERO_HANDOFF", "--attachment-id", attachment_id, "--note", "Identity-verified local cache may become a Zotero stored copy only on explicit read; no lifecycle effect."])
        check = json.loads(invoke(["python3", str(args.atrctl), "check", str(run)]))
        with sqlite3.connect(run / "atr.sqlite") as connection:
            after = connection.execute("SELECT state,version FROM subjects WHERE subject_id=?", (subject,)).fetchone()
        if before != after or after != ("INTAKE", 0) or not check.get("pass"):
            raise ValueError({"program": program, "before": before, "after": after, "check": check})
        reports.append({"program": program, "source_count": len(sources), "status": "ALREADY_ATTACHED" if exists else "ATTACHED", "authority": after})
    print(json.dumps({"handoffs": reports}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
