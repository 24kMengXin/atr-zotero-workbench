#!/usr/bin/env python3
"""Upgrade six metadata scaffolds to located, partially source-reviewed maps."""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAFFOLDS = ROOT / "programs" / "v2-intakes" / "r0-scaffolds"
REDUCTIONS = ROOT / "programs" / "v2-intakes" / "pilot-reductions"
OUT = ROOT / "programs" / "v2-intakes" / "source-reviewed-knowledge"

# tuple: source id, inspection-span index, relation, optional more precise observation
MAPPINGS = {
    "multilingual-agent-action-attribution": {
        "action-attribution": ("CHALLENGED_BY_COLLISION_REVIEW", [("SRC-MLCL-2026", 0, "DISTINGUISHES"), ("SRC-UNITOOLCALL-2026", 0, "CHALLENGES")]),
        "language-surfaces": ("BOUNDED_SOURCE_REVIEWED", [("SRC-MLCL-2026", 0, "DISTINGUISHES"), ("SRC-MLCL-2026", 1, "EXEMPLIFIES")]),
        "action-selection": ("PARTIALLY_SOURCE_REVIEWED", [("SRC-MLCL-2026", 0, "DISTINGUISHES"), ("SRC-MASSIVE-AGENTS-2025", 0, "EXEMPLIFIES")]),
        "interface-contract": ("BOUNDED_SOURCE_REVIEWED", [("SRC-MLCL-2026", 0, "DEFINES"), ("SRC-UNITOOLCALL-2026", 0, "DEFINES")]),
        "execution-outcome": ("PARTIALLY_SOURCE_REVIEWED", [("SRC-MLCL-2026", 0, "EXEMPLIFIES")]),
        "evaluation-attribution": ("CHALLENGED_BY_COLLISION_REVIEW", [("SRC-MASSIVE-AGENTS-2025", 1, "LIMITS"), ("SRC-UNITOOLCALL-2026", 0, "CHALLENGES")]),
    },
    "multilingual-agent-authorization-safety": {
        "authorization-safety": ("PARTIALLY_SOURCE_REVIEWED", [("SRC-AGENTABSTAIN-2026", 0, "DISTINGUISHES"), ("SRC-VERIFIABLY-SAFE-TOOL-USE-2026", 0, "DEFINES")]),
        "intent-and-authority": ("PARTIALLY_SOURCE_REVIEWED", [("SRC-VERIFIABLY-SAFE-TOOL-USE-2026", 0, "DEFINES")]),
        "ambiguity-and-clarification": ("PARTIALLY_SOURCE_REVIEWED", [("SRC-AGENTABSTAIN-2026", 0, "DISTINGUISHES"), ("SRC-AGENTABSTAIN-2026", 1, "EXEMPLIFIES")]),
        "indirect-instruction": ("PENDING_ADDITIONAL_SOURCE_REVIEW", [("SRC-XSafety-2024", 1, "LIMITS", "The inspected multilingual text-safety evidence does not examine retrieved indirect instructions or tool-observation authority conflicts.")]),
        "policy-grounding": ("BOUNDED_SOURCE_REVIEWED", [("SRC-VERIFIABLY-SAFE-TOOL-USE-2026", 0, "DEFINES")]),
        "trajectory-safety": ("PARTIALLY_SOURCE_REVIEWED", [("SRC-AGENTABSTAIN-2026", 0, "DISTINGUISHES"), ("SRC-AGENTABSTAIN-2026", 1, "EXEMPLIFIES")]),
    },
    "multilingual-agent-state-continuity": {
        "state-continuity": ("CHALLENGED_BY_COLLISION_REVIEW", [("SRC-POLYWORKBENCH-2026", 0, "EXEMPLIFIES"), ("SRC-STATEFUL-TOOL-USE-2025", 0, "CHALLENGES")]),
        "state-encoding": ("BOUNDED_SOURCE_REVIEWED", [("SRC-HINDSIGHT-2026", 0, "DEFINES")]),
        "memory-storage": ("BOUNDED_SOURCE_REVIEWED", [("SRC-HINDSIGHT-2026", 0, "DEFINES")]),
        "crosslingual-retrieval": ("PENDING_ADDITIONAL_SOURCE_REVIEW", [("SRC-HINDSIGHT-2026", 1, "LIMITS", "The inspected memory architecture is evaluated only in English and therefore does not establish cross-lingual retrieval.")]),
        "language-control-plane": ("BOUNDED_SOURCE_REVIEWED", [("SRC-MS-COPILOT-LANGUAGE-CONTROL-2026", 0, "DEFINES"), ("SRC-GOOGLE-DIALOGFLOW-AUTODETECT-2026", 0, "DISTINGUISHES"), ("SRC-GOOGLE-DIALOGFLOW-AUTODETECT-2026", 1, "LIMITS")]),
        "long-horizon-evaluation": ("PARTIALLY_SOURCE_REVIEWED", [("SRC-POLYWORKBENCH-2026", 0, "EXEMPLIFIES"), ("SRC-POLYWORKBENCH-2026", 1, "LIMITS"), ("SRC-STATEFUL-TOOL-USE-2025", 0, "LIMITS")]),
    },
    "multilingual-representation-and-data-decisions": {
        "representation-data": ("PARTIALLY_SOURCE_REVIEWED", [("SRC-QE-QUALITY-GATE-ROUTING-2021", 0, "EXEMPLIFIES"), ("SRC-USER-RELIANCE-MT-2025", 0, "EXEMPLIFIES")]),
        "data-composition": ("PENDING_ADDITIONAL_SOURCE_REVIEW", [("SRC-AI-ASSISTED-MT-EVAL-2024", 0, "LIMITS", "The inspected evaluation-assistance study does not establish multilingual training or retrieval data-composition decisions.")]),
        "tokenization-representation": ("PENDING_ADDITIONAL_SOURCE_REVIEW", [("SRC-QE-QUALITY-GATE-ROUTING-2021", 1, "LIMITS", "The inspected workflow evidence varies by language and use case but does not examine tokenization or internal representation.")]),
        "adaptation-allocation": ("PENDING_ADDITIONAL_SOURCE_REVIEW", [("SRC-USER-RELIANCE-MT-2025", 1, "LIMITS", "The bounded user study does not examine model-capacity, data-budget, or transfer allocation.")]),
        "inference-and-reasoning": ("PARTIALLY_SOURCE_REVIEWED", [("SRC-USER-RELIANCE-MT-2025", 0, "EXEMPLIFIES"), ("SRC-USER-RELIANCE-MT-2025", 1, "LIMITS")]),
        "quality-and-reliance": ("BOUNDED_SOURCE_REVIEWED", [("SRC-QE-QUALITY-GATE-ROUTING-2021", 0, "DEFINES"), ("SRC-USER-RELIANCE-MT-2025", 0, "EXEMPLIFIES"), ("SRC-EC-ETRANSLATION-WORKFLOW-2026", 0, "EXEMPLIFIES"), ("SRC-AI-ASSISTED-MT-EVAL-2024", 0, "LIMITS")]),
    },
    "agent-infrastructure-and-evaluation-contracts": {
        "agent-infrastructure": ("CHALLENGED_BY_COLLISION_REVIEW", [("SRC-AGENTBEATS-2026", 0, "DISTINGUISHES"), ("SRC-HARNESS-BENCH-2026", 0, "CHALLENGES")]),
        "tool-and-skill-contract": ("PARTIALLY_SOURCE_REVIEWED", [("SRC-CLAWBENCH-DRIFT-2026", 0, "EXEMPLIFIES"), ("SRC-HARNESS-BENCH-2026", 0, "LIMITS")]),
        "runtime-and-harness": ("BOUNDED_SOURCE_REVIEWED", [("SRC-AGENTBEATS-2026", 0, "DISTINGUISHES"), ("SRC-AGENTBEATS-2026", 2, "EXEMPLIFIES"), ("SRC-CLAWBENCH-DRIFT-2026", 0, "EXEMPLIFIES")]),
        "environment-drift": ("BOUNDED_SOURCE_REVIEWED", [("SRC-AGENTLAB-REPRO-2026", 0, "DEFINES"), ("SRC-AGENTLAB-REPRO-2026", 1, "LIMITS")]),
        "reproducibility-contract": ("BOUNDED_SOURCE_REVIEWED", [("SRC-AGENTLAB-REPRO-2026", 0, "DEFINES"), ("SRC-CLAWBENCH-DRIFT-2026", 0, "EXEMPLIFIES"), ("SRC-AGENTBEATS-2026", 1, "EXEMPLIFIES")]),
        "evaluation-attribution": ("CHALLENGED_BY_COLLISION_REVIEW", [("SRC-CAR-2026", 0, "DISTINGUISHES"), ("SRC-AGENTEVAL-2026", 0, "CHALLENGES"), ("SRC-HARNESS-BENCH-2026", 0, "LIMITS")]),
    },
    "atr-research-governance": {
        "research-governance": ("CHALLENGED_BY_COLLISION_REVIEW", [("SRC-HEP-2026", 0, "DEFINES"), ("SRC-LLM-AUDIT-TRAILS-2026", 0, "CHALLENGES")]),
        "evidence-provenance": ("BOUNDED_SOURCE_REVIEWED", [("SRC-HEP-2026", 0, "DEFINES"), ("SRC-HEP-2026", 1, "EXEMPLIFIES"), ("SRC-LLM-AUDIT-TRAILS-2026", 0, "EXEMPLIFIES")]),
        "hypothesis-portfolio": ("BOUNDED_SOURCE_REVIEWED", [("SRC-ARBOR-2026", 0, "DEFINES"), ("SRC-HEP-2026", 1, "EXEMPLIFIES")]),
        "gate-route-transition": ("PARTIALLY_SOURCE_REVIEWED", [("SRC-HEP-2026", 1, "DISTINGUISHES")]),
        "human-review": ("PARTIALLY_SOURCE_REVIEWED", [("SRC-AUTORESEARCHBENCH-2026--6ca54095", 1, "EXEMPLIFIES"), ("SRC-AUTORESEARCHBENCH-2026--6ca54095", 2, "LIMITS")]),
        "system-learning": ("PENDING_ADDITIONAL_SOURCE_REVIEW", [("SRC-ARBOR-2026", 2, "LIMITS", "The inspected autonomous optimization evidence does not establish prospective human-process learning or route-level effects."), ("SRC-LLM-AUDIT-TRAILS-2026", 0, "LIMITS")]),
    },
}


def invoke(command: list[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def load_sources(program: str) -> dict[str, dict]:
    reduction = REDUCTIONS / program
    packet = json.loads((reduction / "source-inspection-packet.json").read_text(encoding="utf-8"))
    collision = json.loads((reduction / "collision-review.json").read_text(encoding="utf-8"))
    handoff = json.loads((reduction / "source-acquisition-handoff.json").read_text(encoding="utf-8"))
    handoff_by_id = {row["source_id"]: row for row in handoff["sources"]}
    sources: dict[str, dict] = {}
    for row in packet["sources"]:
        spans = [{**span, "does_not_establish": span.get("does_not_establish") or row["does_not_establish"]}
                 for span in row["inspection_spans"]]
        sources[row["source_id"]] = {
            key: value for key, value in row.items()
            if key not in {"fulltext_state", "inspection_spans", "zotero_attachment_state", "zotero_snapshot_state"}
        } | {"inspection_state": row["fulltext_state"], "inspection_spans": spans}
    for row in collision["inspected_sources"]:
        acquired = handoff_by_id[row["source_id"]]
        sources[row["source_id"]] = {
            "source_id": row["source_id"], "title": row["title"], "url": acquired["url"],
            "pdf_url": acquired.get("pdf_url"), "kind": acquired.get("kind", "PRIMARY_PAPER"),
            "access_status": acquired.get("access_status"), "access_route": acquired.get("access_route"),
            "identity_state": acquired.get("identity_state"), "content_digest": acquired.get("content_digest"),
            "inspection_state": "FULLTEXT_INSPECTED",
            "inspection_spans": [{"locator": row["locator"], "observation": row["finding"],
                                  "does_not_establish": row["does_not_establish"]}],
            "supports": row["finding"], "does_not_establish": row["does_not_establish"],
        }
    return sources


def stable_write(path: Path, body: dict) -> None:
    rendered = json.dumps(body, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != rendered:
        raise ValueError(f"refusing divergent source-reviewed map: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def build_map(program: str) -> dict:
    scaffold = json.loads((SCAFFOLDS / program / "knowledge" / "knowledge-map.json").read_text(encoding="utf-8"))
    sources = load_sources(program)
    mappings = MAPPINGS[program]
    concepts = []
    used_sources: set[str] = set()
    for concept in scaffold["concepts"]:
        status, rows = mappings[concept["concept_id"]]
        evidence = []
        for row in rows:
            source_id, span_index, relation, *override = row
            used_sources.add(source_id)
            span = sources[source_id]["inspection_spans"][span_index]
            evidence.append({
                "source_id": source_id, "locator": span["locator"], "relation": relation,
                "observation": override[0] if override else span["observation"],
                "does_not_establish": span["does_not_establish"],
            })
        concepts.append({
            "concept_id": concept["concept_id"], "label": concept["label"],
            "parent_id": concept.get("parent_id"), "definition": concept["definition"],
            "source_ids": sorted({row["source_id"] for row in evidence}),
            "review_status": status, "evidence_spans": evidence,
            "does_not_establish": concept["does_not_establish"],
        })
    return {
        "artifact_type": "knowledge-map", "schema_version": "1.1",
        "map_id": scaffold["map_id"], "topic": program,
        "scope": "A versioned learning hierarchy upgraded only where located worker-inspected spans support, limit, or challenge a bounded definition.",
        "created_at": "2026-07-19T16:00:00+08:00", "map_review_status": "PARTIALLY_SOURCE_REVIEWED",
        "does_not_establish": "This map is a reading aid, not a universal ontology, field consensus, novelty certificate, causal hierarchy, human inspection record, route decision, or lifecycle transition.",
        "sources": [sources[source_id] for source_id in sorted(used_sources)], "concepts": concepts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--atrctl", type=Path, required=True)
    args = parser.parse_args()
    reports = []
    for program in MAPPINGS:
        body = build_map(program)
        target = OUT / program / "knowledge-map.json"
        stable_write(target, body)
        run = args.runs_root / f"2026-07-19-{program}-v2-intake"
        subject = f"program:{program}"
        attachment_id = f"ATT-2026-07-19-{program}-SOURCE-REVIEWED-KNOWLEDGE-1-1"
        with sqlite3.connect(run / "atr.sqlite") as connection:
            before = connection.execute("SELECT state,version FROM subjects WHERE subject_id=?", (subject,)).fetchone()
            exists = connection.execute("SELECT 1 FROM attachments WHERE attachment_id=?", (attachment_id,)).fetchone()
        if not exists:
            artifact_id = invoke(["python3", str(args.atrctl), "ingest", str(run), str(target),
                                  "--kind", "knowledge-map", "--scope", "located partial source review; learning map only"])
            invoke(["python3", str(args.atrctl), "attach", str(run), "--subject", subject,
                    "--expected-version", "0", "--artifact", artifact_id,
                    "--role", "SOURCE_REVIEWED_KNOWLEDGE_MAP_V1_1", "--attachment-id", attachment_id,
                    "--note", "Located source-review upgrade of the provisional knowledge scaffold; no lifecycle effect."])
        check = json.loads(invoke(["python3", str(args.atrctl), "check", str(run)]))
        with sqlite3.connect(run / "atr.sqlite") as connection:
            after = connection.execute("SELECT state,version FROM subjects WHERE subject_id=?", (subject,)).fetchone()
        if before != after or after != ("INTAKE", 0) or not check.get("pass"):
            raise ValueError({"program": program, "before": before, "after": after, "check": check})
        reports.append({"program": program, "concepts": len(body["concepts"]),
                        "bounded": sum(row["review_status"] == "BOUNDED_SOURCE_REVIEWED" for row in body["concepts"]),
                        "partial": sum(row["review_status"] == "PARTIALLY_SOURCE_REVIEWED" for row in body["concepts"]),
                        "challenged": sum(row["review_status"] == "CHALLENGED_BY_COLLISION_REVIEW" for row in body["concepts"]),
                        "pending": sum(row["review_status"] == "PENDING_ADDITIONAL_SOURCE_REVIEW" for row in body["concepts"]),
                        "status": "ALREADY_ATTACHED" if exists else "ATTACHED", "authority": after})
    print(json.dumps({"knowledge_maps": reports}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
