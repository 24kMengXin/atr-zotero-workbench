"""Derived program views over multiple immutable ATR historical runs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .core import load_legacy_run, project_graph


def load_program(catalog_path: Path, key: str) -> dict[str, Any]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    for program in catalog.get("programs", []):
        if program.get("key") == key:
            return program
    raise ValueError(f"Program {key!r} is absent from {catalog_path}")


def project_program(catalog_path: Path, key: str) -> dict[str, Any]:
    """Create a read-only program projection without merging historical facts.

    Paper nodes with the same stable source ID are shared so researchers can
    see evidence reuse. Every other node stays branch-namespaced; a claim,
    question, or concept from one historical run is never silently treated as
    identical to a similarly named object from another run.
    """
    program = load_program(catalog_path, key)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    timeline: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    program_id = f"program:{key}"
    nodes.append({"id": program_id, "kind": "research_program", "label": program["label"], "data": {
        "program_key": key, "root_question": program["root_question"], "role": program.get("role", ""),
        "catalog": str(catalog_path), "historical_runs_are_read_only": True,
    }})
    known_node_ids: set[str] = {program_id}
    known_edges: set[tuple[str, str, str]] = set()

    def add_edge(source: str, target: str, relation: str, data: dict[str, Any]) -> None:
        identity = (source, target, relation)
        if identity not in known_edges:
            edges.append({"source": source, "target": target, "relation": relation, "data": data})
            known_edges.add(identity)

    for branch in program.get("branches", []):
        run_path = (catalog_path.parent / branch["run"]).resolve()
        graph = project_graph(load_legacy_run(run_path))
        branch_id = f"branch:{run_path.name}"
        id_map: dict[str, str] = {}
        for node in graph["nodes"]:
            if node["kind"] == "paper" and node["data"].get("source_id"):
                new_id = f"paper:{node['data']['source_id']}"
            else:
                new_id = f"{branch_id}:{node['id']}"
            id_map[node["id"]] = new_id
            if new_id in known_node_ids:
                continue
            copied = {"id": new_id, "kind": node["kind"], "label": node["label"], "data": dict(node.get("data", {}))}
            copied["data"].update({"historical_run": run_path.name, "program_branch_role": branch.get("role", ""), "program_disposition": branch.get("disposition", "")})
            nodes.append(copied); known_node_ids.add(new_id)
        run_node = next((node for node in graph["nodes"] if node["kind"] == "run"), None)
        if run_node:
            add_edge(program_id, id_map[run_node["id"]], "contains_historical_branch", {
                "role": branch.get("role", ""), "disposition": branch.get("disposition", ""), "source_run": run_path.name,
            })
        for edge in graph["edges"]:
            add_edge(id_map[edge["source"]], id_map[edge["target"]], edge["relation"], dict(edge.get("data", {})))
        for item in graph.get("timeline", []):
            copied = dict(item); copied["historical_run"] = run_path.name; copied["program_branch_role"] = branch.get("role", "")
            timeline.append(copied)
        diagnostics.extend(f"{run_path.name}: {message}" for message in graph.get("diagnostics", []))
    timeline.sort(key=lambda item: str(item.get("at", "")))
    return {
        "schema_version": "0.1", "projection": "derived-program-read-only", "run": key,
        "program": {"key": key, "label": program["label"], "root_question": program["root_question"]},
        "diagnostics": diagnostics, "timeline": timeline, "nodes": nodes, "edges": edges,
    }
