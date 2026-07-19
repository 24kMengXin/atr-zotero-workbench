#!/usr/bin/env python3
"""Build a lossless canonical source inventory from legacy and current v2 evidence.

Canonicalization merges bibliographic identity only.  Every legacy occurrence,
support statement, boundary, and program/run origin remains in a separate
record. Current v2 supplements are read only from immutable, source-reviewed
artifact bodies; graph/UI projections are never treated as authority.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit
from typing import Any


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[\w]+", value, flags=re.UNICODE))


def normalize_url(value: str) -> str:
    if not value:
        return ""
    try:
        parts = urlsplit(value.strip())
    except ValueError:
        return value.strip()
    host = parts.netloc.casefold().removeprefix("www.")
    path = re.sub(r"/+", "/", parts.path).rstrip("/")
    # arXiv abs/pdf and versioned URLs refer to one bibliographic work here;
    # cited-version identity remains an occurrence-level review obligation.
    if host == "arxiv.org":
        match = re.match(r"/(?:abs|pdf)/([^/]+?)(?:\.pdf)?$", path)
        if match:
            identifier = re.sub(r"v\d+$", "", match.group(1))
            return f"https://arxiv.org/abs/{identifier}"
    if host == "aclanthology.org" and path.endswith(".pdf"):
        path = path[:-4]
    return urlunsplit((parts.scheme.casefold() or "https", host, path, parts.query, ""))


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, value: int) -> int:
        while self.parent[value] != value:
            self.parent[value] = self.parent[self.parent[value]]
            value = self.parent[value]
        return value

    def union(self, left: int, right: int) -> None:
        left, right = self.find(left), self.find(right)
        if left != right:
            self.parent[max(left, right)] = min(left, right)


def current_reviewed_sources(registry_path: Path, runs_root: Path) -> list[dict[str, Any]]:
    """Return one authoritative reviewed occurrence for each current source.

    The program registry selects the current children.  Within each controller,
    the newest source-reviewed knowledge-map artifact supplies the bibliography
    and inspection boundary.  Content-addressed artifact bodies are used rather
    than the mutable Zotero graph projection.
    """
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    found: list[dict[str, Any]] = []
    programs = registry.get("children", registry.get("programs", []))
    if not programs:
        raise ValueError(f"current registry declares no child programs: {registry_path}")
    for program in programs:
        run_id = str(program["run_id"])
        run_path = (runs_root / run_id).resolve()
        candidates: list[tuple[str, str, Path, dict[str, Any]]] = []
        for body_path in sorted((run_path / "artifacts").glob("*/body.json")):
            body = json.loads(body_path.read_text(encoding="utf-8"))
            if body.get("artifact_type") != "knowledge-map" or not body.get("sources"):
                continue
            if not any("INSPECTED" in str(row.get("inspection_state") or row.get("fulltext_state") or "")
                       for row in body["sources"]):
                continue
            candidates.append((str(body.get("created_at") or ""), str(body.get("schema_version") or ""), body_path, body))
        if not candidates:
            raise ValueError(f"no source-reviewed immutable knowledge-map found: {run_id}")
        _, _, body_path, body = sorted(candidates)[-1]
        artifact_digest = body_path.parent.name
        for source in body["sources"]:
            state = str(source.get("inspection_state") or source.get("fulltext_state") or "")
            if "INSPECTED" not in state:
                continue
            found.append({
                "program_key": str(program["program_key"]),
                "run": run_id,
                "artifact_digest": artifact_digest,
                "source": {**source, "fulltext_state": state},
            })
    return found


def build(catalog_path: Path, *, current_registry: Path | None = None,
          runs_root: Path | None = None) -> dict[str, Any]:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    occurrences = []
    for program in catalog.get("programs", []):
        for branch in program.get("branches", []):
            run_path = (catalog_path.parent / branch["run"]).resolve()
            for source in rows(run_path / "evidence" / "sources.jsonl"):
                occurrences.append({
                    "occurrence_id": f"{run_path.name}:{source.get('source_id')}",
                    "program_key": program["key"], "run": run_path.name,
                    "catalog_disposition": branch.get("disposition"), "catalog_role": branch.get("role"),
                    "legacy_source_id": source.get("source_id"), "source": source,
                    "origin_layer": "LEGACY_AUDITED_OCCURRENCE",
                    "artifact_digest": None,
                    "normalized_url": normalize_url(str(source.get("url") or "")),
                    "normalized_title": normalize_title(str(source.get("title") or "")),
                })

    legacy_occurrence_count = len(occurrences)
    if current_registry is not None:
        if runs_root is None:
            raise ValueError("runs_root is required with current_registry")
        reviewed = current_reviewed_sources(current_registry.resolve(), runs_root.resolve())
        known_ids = {str(item.get("legacy_source_id") or "") for item in occurrences}
        known_urls = {item["normalized_url"] for item in occurrences if item["normalized_url"]}
        known_titles = {item["normalized_title"] for item in occurrences if item["normalized_title"]}
        # The historical occurrence ledger remains lossless. Current v2 adds a
        # supplement only when the reviewed bibliographic identity is genuinely
        # absent; an already-known work is not manufactured into another legacy
        # occurrence merely because a later worker inspected it.
        for item in reviewed:
            source = item["source"]
            source_id = str(source.get("source_id") or "")
            normalized_url = normalize_url(str(source.get("url") or ""))
            normalized_title = normalize_title(str(source.get("title") or ""))
            if (source_id and source_id in known_ids) or (normalized_url and normalized_url in known_urls) or (
                    normalized_title and normalized_title in known_titles):
                continue
            occurrences.append({
                "occurrence_id": f"{item['run']}:CURRENT_V2_REVIEWED:{source_id}",
                "program_key": item["program_key"], "run": item["run"],
                "catalog_disposition": "current_v2_reviewed_supplement",
                "catalog_role": "current_source_inventory_closure",
                "legacy_source_id": source_id, "source": source,
                "origin_layer": "CURRENT_V2_REVIEWED_SOURCE",
                "artifact_digest": item["artifact_digest"],
                "normalized_url": normalized_url, "normalized_title": normalized_title,
            })
            known_ids.add(source_id)
            if normalized_url:
                known_urls.add(normalized_url)
            if normalized_title:
                known_titles.add(normalized_title)

    uf = UnionFind(len(occurrences)); seen_url: dict[str, int] = {}; seen_title: dict[str, int] = {}
    for index, occurrence in enumerate(occurrences):
        for key, seen in ((occurrence["normalized_url"], seen_url), (occurrence["normalized_title"], seen_title)):
            if not key:
                continue
            if key in seen:
                uf.union(index, seen[key])
            else:
                seen[key] = index
    groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for index, occurrence in enumerate(occurrences):
        groups[uf.find(index)].append(occurrence)

    canonical_sources = []
    occurrence_rows = []
    priority = {"canonical": 0, "merge": 1, "retain": 2}
    def rank(member: dict[str, Any]) -> tuple[int, str, str]:
        disposition = str(member.get("catalog_disposition") or "")
        bucket = next((value for prefix, value in priority.items() if disposition.startswith(prefix)), 3)
        return bucket, member["run"], str(member.get("legacy_source_id") or "")

    ordered_groups = sorted(groups.values(), key=lambda members: rank(sorted(members, key=rank)[0]))
    preferred_ids = [str(sorted(members, key=rank)[0].get("legacy_source_id") or "") for members in ordered_groups]
    preferred_id_counts = Counter(preferred_ids)
    for members in ordered_groups:
        representative = sorted(members, key=rank)[0]
        source_ids = sorted({str(item.get("legacy_source_id")) for item in members if item.get("legacy_source_id")})
        urls = sorted({str(item["source"].get("url")) for item in members if item["source"].get("url")})
        titles = sorted({str(item["source"].get("title")) for item in members if item["source"].get("title")})
        kinds = sorted({str(item["source"].get("kind")) for item in members if item["source"].get("kind")})
        preferred_id = str(representative.get("legacy_source_id") or f"SRC-CANONICAL-{len(canonical_sources)+1:04d}")
        legacy_id_collision = preferred_id_counts[preferred_id] > 1
        if legacy_id_collision:
            identity_seed = representative["normalized_url"] or representative["normalized_title"] or representative["occurrence_id"]
            canonical_id = preferred_id + "--" + hashlib.sha256(identity_seed.encode()).hexdigest()[:8]
        else:
            canonical_id = preferred_id
        current_member = next((item for item in members if item["origin_layer"] == "CURRENT_V2_REVIEWED_SOURCE"), None)
        current_source = current_member["source"] if current_member else None
        inspection_state = str((current_source or {}).get("fulltext_state") or "")
        inspected_spans = (current_source or {}).get("inspection_spans") or []
        canonical = {
            "schema_version": "1.0", "canonical_source_id": canonical_id,
            "title": representative["source"].get("title") or titles[0],
            "url": representative["source"].get("url") or (urls[0] if urls else ""),
            "normalized_url": representative["normalized_url"],
            "kind": representative["source"].get("kind") or (kinds[0] if kinds else "SOURCE_NEEDS_REVIEW"),
            "legacy_source_ids": source_ids,
            "program_keys": sorted({item["program_key"] for item in members}),
            "runs": sorted({item["run"] for item in members}),
            "occurrence_count": len(members),
            "identity_variants": {"titles": titles, "urls": urls, "kinds": kinds},
            "legacy_id_collision": legacy_id_collision,
            "identity_review": "LEGACY_ID_COLLISION_REQUIRES_REVIEW" if legacy_id_collision else (
                "CONFLICT_REQUIRES_REVIEW" if len(titles) > 1 or len(urls) > 1 else "EXACT_NORMALIZED_MATCH"
            ),
            "origin_layers": sorted({item["origin_layer"] for item in members}),
            "access_status": (current_source or {}).get("access_status") or "METADATA_ONLY",
            "access_route": (current_source or {}).get("access_route") or "NONE",
            "zotero_item_key": None, "zotero_attachment_key": None,
            "fulltext_attached": False, "fulltext_inspected": "INSPECTED" in inspection_state,
            "inspected_locators": [span.get("locator") for span in inspected_spans if span.get("locator")],
            "worker_inspection_state": inspection_state or "NOT_RECORDED",
            "human_inspection_state": "NOT_RECORDED",
            "next_action": ("MATERIALIZE_OR_RESOLVE_IN_ZOTERO_FOR_HUMAN_READING" if current_source
                            else "RESOLVE_IN_ZOTERO_THEN_INSPECT_LOAD_BEARING_SPANS"),
            "boundary": ("Current v2 inspection records located worker review only; it does not establish human reading, Zotero attachment, a gate, or scholarly correctness."
                         if current_source else
                         "Canonicalization establishes only probable bibliographic identity; it does not establish version identity, access, attachment, inspection, support, or scholarly correctness."),
        }
        canonical_sources.append(canonical)
        for member in members:
            source = member["source"]
            occurrence_rows.append({
                "schema_version": "1.0", "occurrence_id": member["occurrence_id"],
                "canonical_source_id": canonical_id, "program_key": member["program_key"], "run": member["run"],
                "catalog_disposition": member["catalog_disposition"], "catalog_role": member["catalog_role"],
                "origin_layer": member["origin_layer"], "artifact_digest": member["artifact_digest"],
                "legacy_source_id": member["legacy_source_id"], "title": source.get("title"), "url": source.get("url"),
                "kind": source.get("kind"), "supports": source.get("supports"),
                "does_not_support": source.get("does_not_support") or source.get("does_not_establish"),
                "verified_at_legacy": source.get("verified_at"),
                "fulltext_state": source.get("fulltext_state") or source.get("inspection_state"),
                "inspection_spans": source.get("inspection_spans", []),
                "reuse_boundary": ("Located worker review only; human reading and Zotero attachment remain independent."
                                   if member["origin_layer"] == "CURRENT_V2_REVIEWED_SOURCE" else
                                   "Historical interpretation only; reverify source identity and cited span before current use."),
            })

    canonical_sources.sort(key=lambda item: (item["canonical_source_id"], item["title"])); occurrence_rows.sort(key=lambda item: item["occurrence_id"])
    queue = sorted(canonical_sources, key=lambda item: (
        0 if any("canonical_" in str(o["catalog_disposition"]) for o in occurrence_rows if o["canonical_source_id"] == item["canonical_source_id"]) else 1,
        -item["occurrence_count"], item["canonical_source_id"],
    ))
    summary = {
        "legacy_occurrences": legacy_occurrence_count,
        "current_v2_reviewed_additions": len(occurrences) - legacy_occurrence_count,
        "total_occurrences": len(occurrences), "canonical_sources": len(canonical_sources),
        "merged_occurrences": legacy_occurrence_count - (len(canonical_sources) - (len(occurrences) - legacy_occurrence_count)),
        "identity_conflicts": sum(item["identity_review"] != "EXACT_NORMALIZED_MATCH" for item in canonical_sources),
        "legacy_id_collisions": sum(item["legacy_id_collision"] for item in canonical_sources),
        "metadata_only": sum(item["access_status"] == "METADATA_ONLY" for item in canonical_sources),
        "fulltext_attached": sum(item["fulltext_attached"] for item in canonical_sources),
        "fulltext_inspected": sum(item["fulltext_inspected"] for item in canonical_sources),
        "program_counts": dict(sorted(Counter(o["program_key"] for o in occurrence_rows).items())),
    }
    return {"summary": summary, "canonical_sources": canonical_sources, "occurrences": occurrence_rows, "queue": queue}


def write_jsonl(path: Path, data: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in data), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("catalog", type=Path); parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--current-registry", type=Path); parser.add_argument("--runs-root", type=Path)
    args = parser.parse_args(); result = build(args.catalog.resolve(), current_registry=args.current_registry,
                                                runs_root=args.runs_root)
    out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "canonical-sources.jsonl", result["canonical_sources"])
    write_jsonl(out / "source-occurrences.jsonl", result["occurrences"])
    (out / "zotero-acquisition-queue.json").write_text(json.dumps({
        "schema_version": "1.0", "artifact_type": "zotero-source-acquisition-queue",
        "summary": result["summary"],
        "policy": "Resolve existing Zotero item/attachment first; canonicalization and URLs are not fulltext evidence.",
        "items": result["queue"],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
