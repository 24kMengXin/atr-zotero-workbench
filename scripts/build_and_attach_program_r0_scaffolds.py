#!/usr/bin/env python3
"""Build six honest R0/FKS scaffolds and attach them without transition.

The selected historical sources remain metadata-only.  These artifacts expose
the hierarchy and verification questions to Zotero, but deliberately remain
draft inputs pending full-text inspection and independent route review.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from typing import Any


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def stable_json(path: Path, body: dict[str, Any]) -> None:
    encoded = json.dumps(body, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != encoded:
        raise ValueError(f"refusing to overwrite divergent R0 scaffold: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")


def stable_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    encoded = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    if path.exists() and path.read_text(encoding="utf-8") != encoded:
        raise ValueError(f"refusing to overwrite divergent R0 source snapshot: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(encoded, encoding="utf-8")


def invoke(command: list[str]) -> str:
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed: {' '.join(command)}\n{result.stdout}\n{result.stderr}")
    return result.stdout.strip()


def has_attachment(run_dir: Path, attachment_id: str) -> bool:
    connection = sqlite3.connect(run_dir / "atr.sqlite")
    try:
        return connection.execute(
            "SELECT 1 FROM attachments WHERE attachment_id=?", (attachment_id,)
        ).fetchone() is not None
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("definitions", type=Path)
    parser.add_argument("--inventory-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--atrctl", type=Path, required=True)
    parser.add_argument("--harness-root", type=Path, required=True)
    args = parser.parse_args()

    definitions = json.loads(args.definitions.read_text(encoding="utf-8"))
    boundary = definitions["evidence_boundary"]
    scripts = args.harness_root / "scripts"
    knowledge_context = load_module("knowledge_context", scripts / "knowledge_context.py")
    sys.path.insert(0, str(scripts))
    topic_route = load_module("topic_route", scripts / "topic_route.py")
    results = []

    for key, spec in definitions["programs"].items():
        inventory_path = args.inventory_root / key / "program-source-inventory.json"
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        by_id = {source["source_id"]: source for source in inventory["sources"]}
        source_ids = list(dict.fromkeys(
            source_id for tension in spec["tensions"] for source_id in tension["sources"]
        ))
        missing = sorted(set(source_ids) - set(by_id))
        if missing:
            raise ValueError(f"{key} scaffold references unknown source IDs: {missing}")
        sources = [by_id[source_id] for source_id in source_ids]
        root = args.output_root / key
        source_rows = [{
            "schema_version": "1.0", "source_id": source["source_id"],
            "title": source["title"], "url": source["url"], "kind": source["kind"],
            "access_status": source["access_status"], "access_route": source["access_route"],
            "supports": "Candidate anchor selected for verification because its recorded title/scope intersects this program.",
            "does_not_support": boundary,
        } for source in sources]
        stable_jsonl(root / "evidence" / "sources.jsonl", source_rows)

        frontier = {
            "schema_version": "1.0", "map_id": f"FKM-{key}.draft-v1",
            "domain": key, "scope": "Top-down verification scaffold, not an exhaustive survey or consensus map.",
            "frontier_as_of": "2026-07-19", "source_ledger_path": "evidence/sources.jsonl",
            "verification_status": "PENDING_ZOTERO_FULLTEXT_AND_LOCATOR_REVIEW",
            "evidence_boundary": boundary,
            "frontier_tensions": [{
                "tension_id": tension["id"], "question": tension["question"],
                "competing_explanations": tension["explanations"], "dimensions": tension["dimensions"],
                "anchor_source_ids": tension["sources"],
                "freshness": "Refresh after source attachment/inspection, a direct collision, or a relevant benchmark/workflow revision.",
                "does_not_establish": boundary,
            } for tension in spec["tensions"]],
            "update_policy": {
                "triggers": ["first inspected source span", "direct collision", "benchmark or workflow revision", "human Zotero review"],
                "refresh_cadence": "before independent topic-route review and before any problem-case transition",
                "owner": "research owner with Zotero-linked source review",
            },
        }
        frontier_path = root / "knowledge" / "frontier-map.json"
        stable_json(frontier_path, frontier)
        frontier_errors = knowledge_context.validate_frontier_map(root, frontier)
        if frontier_errors:
            raise ValueError(f"invalid frontier map for {key}: {frontier_errors}")

        concept_source_ids = [tension["sources"] for tension in spec["tensions"]]
        concepts = []
        for index, (concept_id, label, parent_id, definition) in enumerate(spec["concepts"]):
            selected = source_ids if parent_id is None else concept_source_ids[(index - 1) % len(concept_source_ids)]
            concepts.append({
                "concept_id": concept_id, "label": label, "parent_id": parent_id,
                "definition": definition, "source_ids": selected,
                "review_status": "AUTHORIAL_SCAFFOLD_PENDING_SOURCE_INSPECTION",
                "does_not_establish": boundary,
            })
        knowledge_map = {
            "schema_version": "1.0", "artifact_type": "knowledge-map",
            "map_id": f"KM-{key}.draft-v1", "topic": key,
            "definition": "A top-down hierarchy of concepts to verify while reading; definitions are provisional organizing statements.",
            "does_not_establish": boundary,
            "sources": [{
                "source_id": source["source_id"], "title": source["title"], "url": source["url"],
                "kind": source["kind"], "access_status": source["access_status"],
                "access_route": source["access_route"],
                "supports": "Candidate source for this concept scaffold; content-level support remains unverified.",
                "does_not_establish": boundary,
            } for source in sources],
            "concepts": concepts,
        }
        knowledge_path = root / "knowledge" / "knowledge-map.json"
        stable_json(knowledge_path, knowledge_map)

        count = inventory["canonical_source_count"]
        density = "DENSE" if count >= 80 else "MODERATE" if count >= 25 else "THIN"
        required_artifacts = [
            "verified source ledger with Zotero attachment/locator states",
            "source-reviewed frontier map", "counterevidence and coverage report",
            "independent route review",
        ]
        if spec["selected_track"] == "FULL_SURVEY":
            required_artifacts.extend([
                "source-grounded taxonomy with contradiction boundaries",
                "dated seed agenda with non-promotable outcomes retained",
            ])
        route = {
            "schema_version": "1.1", "package_id": f"TRP-{key}.draft-v1",
            "topic": json.loads((args.output_root.parent / "programs" / key / "program-intake.json").read_text(encoding="utf-8"))["root_question"],
            "domain_bindings": ([{
                "binding_id": "language-axis",
                "activation_condition": "The program asks how multilingual or cross-lingual surfaces affect an agent or data decision.",
                "ambiguity_resolved": "Separates the focal natural-language/data surface from tool, schema, reasoning, evaluator, and programming-language surfaces.",
                "extra_evidence_required": ["parallel or controlled language-surface comparisons", "explicit mapping of every language-bearing surface"],
                "false_positive_prevented": "Prevents programming-language, translation, or benchmark coverage from being misreported as the focal multilingual mechanism.",
                "deactivation_condition": "Deactivate only if the final construct and all load-bearing conditions are language independent.",
            }] if spec.get("language_axis") else []),
            **({"language_axis": spec["language_axis"]} if spec.get("language_axis") else {}),
            "input_class": "BROAD_DIRECTION", "searched_through": "2026-07-19 metadata inventory; full-text verification pending",
            "corpus_assessment": {
                "density_band": density, "taxonomy_feasible": count >= 25,
                "existing_survey_status": "UNCERTAIN", "evidence_refs": source_ids,
                "does_not_support": boundary,
            },
            "selected_track": spec["selected_track"],
            "next_stage": {"FULL_SURVEY": "R2_SURVEY", "FOCUSED_REVIEW": "R2_FOCUSED_REVIEW", "EMERGING_DIRECTION": "R1_LANDSCAPE"}[spec["selected_track"]],
            "knowledge_build_plan": {
                "required_artifacts": required_artifacts,
                "artifact_paths": ["evidence/sources.jsonl", "knowledge/frontier-map.json", "knowledge/knowledge-map.json"],
                "question_generation_source": "Only source-inspected tensions and counterexamples surviving independent route review may generate problem cases.",
                "exit_condition": "Candidate anchors are inspected with locators, the frontier scaffold is revised, counterevidence is recorded, and an independent reviewer selects or rejects the route.",
            },
            "family_policy": {
                "max_live_candidates": 2, "max_total_candidates_before_pivot": 4,
                "required_distinction_dimensions": ["actor and decision", "causal mechanism", "measurement boundary"],
                "pivot_rule": "After two unchanged blockers, change source channel or causal fingerprint; after the total cap, merge at a higher construct or park rather than minting setting-only siblings.",
            },
            "forbidden_shortcuts": ["Do not treat metadata or titles as inspected evidence.", "Do not treat the frontier scaffold as novelty or a gap certificate.", "Do not create a problem-case before independent route review."],
            "rationale": f"The inventory contains {count} canonical candidates, but none records inspected full text. The selected track is a proportional draft for verification and remains unauthorized until an independent reviewer reads the cited spans.",
            "created_at": "2026-07-19T00:00:00+08:00", "valid_until": "2026-08-19T00:00:00+08:00",
        }
        route_path = root / "knowledge" / "topic-routing-package.json"
        stable_json(route_path, route)
        route_errors = topic_route.validate(route, None)
        if route_errors:
            raise ValueError(f"invalid topic route draft for {key}: {route_errors}")

        run_id = f"2026-07-19-{key}-v2-intake"
        run_dir = args.runs_root / run_id
        subject = f"program:{key}"
        attachments = [
            (frontier_path, "frontier-map", "DRAFT_FKS_FRONTIER", "FKS frontier questions; metadata-only anchors pending Zotero full-text review."),
            (knowledge_path, "knowledge-map", "DRAFT_KNOWLEDGE_SCAFFOLD", "Top-down concept hierarchy for human source verification; not consensus."),
            (route_path, "topic-routing-package", "PENDING_TOPIC_ROUTE_REVIEW", "Structurally valid route draft; no transition before independent evidence review."),
        ]
        attached = []
        for suffix, (path, kind, role, note) in enumerate(attachments, start=1):
            attachment_id = f"ATT-{run_id}-R0-{suffix:02d}"
            if has_attachment(run_dir, attachment_id):
                attached.append({"attachment_id": attachment_id, "attached": False, "reason": "ALREADY_ATTACHED"})
                continue
            artifact_id = invoke([
                "python3", str(args.atrctl), "ingest", str(run_dir), str(path),
                "--kind", kind, "--scope", "R0 draft context; no lifecycle authorization",
            ])
            invoke([
                "python3", str(args.atrctl), "attach", str(run_dir), "--subject", subject,
                "--expected-version", "0", "--artifact", artifact_id, "--role", role,
                "--attachment-id", attachment_id, "--note", note,
            ])
            attached.append({"attachment_id": attachment_id, "attached": True, "artifact_id": artifact_id})
        check = json.loads(invoke(["python3", str(args.atrctl), "check", str(run_dir)]))
        if not check.get("pass"):
            raise ValueError(f"controller check failed for {key}: {check}")
        results.append({
            "program": key, "source_candidates": len(sources), "concept_count": len(concepts),
            "tension_count": len(spec["tensions"]), "selected_track_draft": spec["selected_track"],
            "controller_state": "INTAKE", "attachments": attached,
        })
    print(json.dumps({"programs": results}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
