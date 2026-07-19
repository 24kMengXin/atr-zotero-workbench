"""Align a local Zotero run registry to one portfolio and its declared children."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .runs import validate_registry


def align_registry_to_portfolio(
    registry: dict[str, Any],
    program_registry: dict[str, Any],
    portfolio_run_id: str,
) -> dict[str, Any]:
    """Keep only declared portfolio children in the current v2 navigation set.

    Superseded v2 controllers remain registered and readable, but are demoted to
    historical navigation. Their controller data is never mutated.
    """
    child_run_ids = {
        str(row["run_id"])
        for row in program_registry.get("children", [])
        if isinstance(row, dict) and row.get("run_id")
    }
    if not child_run_ids:
        raise ValueError("program registry declares no child authorities")
    portfolio_matches = [
        row for row in registry.get("runs", []) if row.get("run_id") == portfolio_run_id
    ]
    if len(portfolio_matches) != 1:
        raise ValueError("portfolio run_id must resolve exactly once in the local registry")
    found_children: set[str] = set()
    demoted: list[str] = []
    for row in registry.get("runs", []):
        run_id = str(row.get("run_id") or "")
        if run_id == portfolio_run_id:
            row["view_role"] = "CURRENT_RUN"
            continue
        if run_id in child_run_ids:
            row["view_role"] = "REGISTERED_V2_RUN"
            found_children.add(run_id)
            continue
        if (row.get("controller_kind") == "ATR_V2_SQLITE"
                and row.get("view_role") in {"CURRENT_RUN", "REGISTERED_V2_RUN"}):
            row["view_role"] = "HISTORICAL_NAVIGATION"
            row["registry_disposition"] = "SUPERSEDED_BY_PROGRAM_PORTFOLIO"
            row["superseded_by"] = portfolio_run_id
            row["boundary"] = (
                "This v2 controller remains readable as history but is not a declared "
                "child authority of the current portfolio."
            )
            demoted.append(run_id)
    missing = sorted(child_run_ids - found_children)
    if missing:
        raise ValueError("declared child authorities missing from local registry: " + ", ".join(missing))
    portfolio_key = str(portfolio_matches[0]["key"])
    registry["active_run"] = portfolio_key
    registry["selection"] = {
        "mode": "EXPLICIT",
        "selected_key": portfolio_key,
        "reason": "Aligned to the declared portfolio authority and its exact child registry.",
    }
    errors = validate_registry(registry)
    if errors:
        raise ValueError("aligned registry is invalid: " + "; ".join(errors))
    return {
        "registry": registry,
        "summary": {
            "portfolio_run_id": portfolio_run_id,
            "registered_child_authorities": len(found_children),
            "demoted_v2_runs": sorted(demoted),
        },
    }


def align_registry_file(registry_path: Path, program_registry_path: Path, portfolio_run_id: str) -> dict[str, Any]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    programs = json.loads(program_registry_path.read_text(encoding="utf-8"))
    result = align_registry_to_portfolio(registry, programs, portfolio_run_id)
    registry_path.write_text(
        json.dumps(result["registry"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result["summary"]
