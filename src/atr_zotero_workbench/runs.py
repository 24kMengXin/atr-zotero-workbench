"""Explicit registry for ATR workbench projections.

The registry is a small, user-reviewable index. It deliberately does not scan
directories: an ATR run appears in Zotero only after a build has registered it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def register_run(registry_path: Path, *, key: str, label: str, run_dir: Path, output: Path, graph: dict[str, Any]) -> dict[str, Any]:
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {
        "schema_version": "0.1", "projection": "atr-workbench-run-registry", "runs": [], "active_run": None
    }
    record = {
        "key": key,
        "label": label,
        "run_id": graph.get("run"),
        "run_dir": str(run_dir.resolve()),
        "workspace": str(output.resolve()),
    }
    registry["runs"] = [item for item in registry.get("runs", []) if item.get("key") != key] + [record]
    registry["active_run"] = key
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return registry
