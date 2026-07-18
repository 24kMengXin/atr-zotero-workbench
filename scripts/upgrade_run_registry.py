#!/usr/bin/env python3
"""Upgrade and explicitly select an ATR → Zotero projection registry.

This is a catalog migration only. It never changes an ATR controller, graph,
history snapshot, Zotero database, or lifecycle state.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from atr_zotero_workbench.runs import describe_authority, validate_registry  # noqa: E402


def parse_roles(values: list[str]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"invalid --role {value!r}; expected KEY=ROLE")
        key, role = value.split("=", 1)
        roles[key] = role
    return roles


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("registry", type=Path)
    parser.add_argument("--activate", required=True)
    parser.add_argument("--role", action="append", default=[])
    parser.add_argument("--repo-active-task", type=Path)
    args = parser.parse_args()

    registry_path = args.registry.resolve()
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    roles = parse_roles(args.role)
    runs = []
    for row in registry.get("runs", []):
        graph_path = Path(row["workspace"]) / "graph.json"
        if not graph_path.is_file():
            raise ValueError(f"registered graph missing: {graph_path}")
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        authority = describe_authority(Path(row["run_dir"]), graph)
        if row["key"] in roles:
            authority["view_role"] = roles[row["key"]]
        runs.append({**row, **authority})

    if args.activate not in {row["key"] for row in runs}:
        raise ValueError(f"--activate key is not registered: {args.activate}")

    observation = None
    if args.repo_active_task:
        pointer = args.repo_active_task.resolve()
        observation = {
            "path": str(pointer),
            "value": pointer.read_text(encoding="utf-8").strip() if pointer.is_file() else None,
            "role": "REPOSITORY_WIDE_OPERATIONAL_POINTER_NOT_ZOTERO_SELECTION",
        }

    upgraded = {
        "schema_version": "0.2",
        "projection": "atr-workbench-run-registry",
        "selection_policy": "EXPLICIT_ACTIVATION_ONLY",
        "runs": runs,
        "active_run": args.activate,
        "selection": {
            "mode": "EXPLICIT",
            "selected_key": args.activate,
            "reason": "Selected current ATR authority for Zotero; historical/program views remain navigation-only.",
            "repository_active_task_observation": observation,
        },
    }
    errors = validate_registry(upgraded)
    if errors:
        raise ValueError("invalid upgraded registry: " + "; ".join(errors))
    registry_path.write_text(json.dumps(upgraded, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "registry": str(registry_path),
        "active_run": args.activate,
        "runs": len(runs),
        "repository_active_task_differs": bool(observation and observation["value"] and args.activate not in observation["value"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
