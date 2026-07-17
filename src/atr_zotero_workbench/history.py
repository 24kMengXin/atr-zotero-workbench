"""Append-only history for derived graph projections.

History is for review, not an alternate authority: each snapshot is a copy of
an earlier projection and points back to the ATR artifacts from which it came.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _canonical(graph: dict[str, Any]) -> str:
    # History metadata must not make a semantically unchanged graph appear new.
    payload = {key: value for key, value in graph.items() if key != "history"}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def archive_previous_projection(output: Path, graph: dict[str, Any]) -> dict[str, Any]:
    """Archive a changed previous graph and return review-facing metadata."""
    current_path = output / "graph.json"
    history_dir = output / "history" / "projections"
    index_path = output / "history" / "index.json"
    previous: dict[str, Any] | None = None
    if current_path.exists():
        previous = json.loads(current_path.read_text(encoding="utf-8"))
    if previous is None:
        return {"snapshots": [], "previous_projection": None}

    previous_text = _canonical(previous)
    if previous_text == _canonical(graph):
        return previous.get("history", {"snapshots": [], "previous_projection": None})

    snapshot_id = hashlib.sha256(previous_text.encode("utf-8")).hexdigest()[:16]
    history_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = history_dir / f"{snapshot_id}.json"
    if not snapshot_path.exists():
        snapshot_path.write_text(json.dumps(previous, ensure_ascii=False, indent=2), encoding="utf-8")

    entries = []
    if index_path.exists():
        entries = json.loads(index_path.read_text(encoding="utf-8")).get("snapshots", [])
    if not any(entry["id"] == snapshot_id for entry in entries):
        entries.append({
            "id": snapshot_id,
            "archived_at": datetime.now(timezone.utc).isoformat(),
            "path": str(snapshot_path.relative_to(output)),
            "run": previous.get("run"),
            "node_count": len(previous.get("nodes", [])),
            "edge_count": len(previous.get("edges", [])),
        })
        index_path.parent.mkdir(parents=True, exist_ok=True)
        index_path.write_text(json.dumps({"schema_version": "0.1", "snapshots": entries}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"snapshots": entries, "previous_projection": snapshot_id}
