"""Explicit registry for ATR workbench projections.

The registry is a small, user-reviewable index. It deliberately does not scan
directories: an ATR run appears in Zotero only after a build has registered it.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def describe_authority(run_dir: Path, graph: dict[str, Any]) -> dict[str, str]:
    """Describe where lifecycle truth lives without promoting a derived view."""
    if graph.get("projection") == "derived-read-only-v2-sqlite":
        return {
            "controller_kind": "ATR_V2_SQLITE",
            "authority_path": str((run_dir / "atr.sqlite").resolve()),
            "authority_scope": "LIFECYCLE_AND_ATTACHMENTS",
            "view_role": "CURRENT_RUN",
        }
    if graph.get("program"):
        return {
            "controller_kind": "DERIVED_PROGRAM_VIEW",
            "authority_path": str(run_dir.resolve()),
            "authority_scope": "NAVIGATION_ONLY",
            "view_role": "HISTORICAL_NAVIGATION",
        }
    return {
        "controller_kind": "ATR_V1_RUN_STATE",
        "authority_path": str((run_dir / "run-state.json").resolve()),
        "authority_scope": "LEGACY_LIFECYCLE",
        "view_role": "LEGACY_RUN",
    }


def validate_registry(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    runs = registry.get("runs")
    if not isinstance(runs, list) or not runs:
        return ["registry must contain at least one run"]
    keys = [row.get("key") for row in runs]
    if any(not key for key in keys):
        errors.append("every run needs a key")
    if len(keys) != len(set(keys)):
        errors.append("run keys must be unique")
    active = registry.get("active_run")
    if active not in keys:
        errors.append("active_run must resolve to one registered run")
    for row in runs:
        for field in ("workspace", "run_dir", "controller_kind", "authority_path", "authority_scope", "view_role"):
            if not row.get(field):
                errors.append(f"run {row.get('key')!r} missing {field}")
        if row.get("controller_kind") == "DERIVED_PROGRAM_VIEW" and row.get("authority_scope") != "NAVIGATION_ONLY":
            errors.append(f"derived program {row.get('key')!r} must be NAVIGATION_ONLY")
    selection = registry.get("selection") or {}
    if selection.get("mode") != "EXPLICIT":
        errors.append("selection.mode must be EXPLICIT")
    if selection.get("selected_key") != active:
        errors.append("selection.selected_key must equal active_run")
    return errors


def register_run(
    registry_path: Path,
    *,
    key: str,
    label: str,
    run_dir: Path,
    output: Path,
    graph: dict[str, Any],
    activate: bool = False,
    view_role: str | None = None,
) -> dict[str, Any]:
    registry = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {
        "schema_version": "0.2", "projection": "atr-workbench-run-registry", "runs": [], "active_run": None
    }
    authority = describe_authority(run_dir, graph)
    if view_role:
        authority["view_role"] = view_role
    record = {
        "key": key,
        "label": label,
        "run_id": graph.get("run"),
        "run_dir": str(run_dir.resolve()),
        "workspace": str(output.resolve()),
        **authority,
    }
    registry["runs"] = [item for item in registry.get("runs", []) if item.get("key") != key] + [record]
    registry["schema_version"] = "0.2"
    registry["selection_policy"] = "EXPLICIT_ACTIVATION_ONLY"
    # Building another projection must not silently change the research context
    # Zotero opens. The first record is a deterministic bootstrap; subsequent
    # changes require --activate or an explicit registry migration.
    if activate or not registry.get("active_run"):
        registry["active_run"] = key
    registry["selection"] = {
        "mode": "EXPLICIT",
        "selected_key": registry["active_run"],
        "reason": "Explicit Zotero workbench context; build order is not authority.",
    }
    errors = validate_registry(registry)
    if errors:
        raise ValueError("invalid ATR workbench registry: " + "; ".join(errors))
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")
    return registry
