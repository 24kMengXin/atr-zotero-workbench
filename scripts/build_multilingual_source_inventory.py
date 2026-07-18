#!/usr/bin/env python3
"""Build a lossless canonical source inventory from audited legacy runs.

Canonicalization merges bibliographic identity only.  Every legacy occurrence,
support statement, boundary, and program/run origin remains in a separate
record.  The output never claims that a URL resolved, a PDF was attached, or a
source span was inspected.
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


def build(catalog_path: Path) -> dict[str, Any]:
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
                    "normalized_url": normalize_url(str(source.get("url") or "")),
                    "normalized_title": normalize_title(str(source.get("title") or "")),
                })

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
            "access_status": "METADATA_ONLY", "access_route": "NONE",
            "zotero_item_key": None, "zotero_attachment_key": None,
            "fulltext_attached": False, "fulltext_inspected": False, "inspected_locators": [],
            "next_action": "RESOLVE_IN_ZOTERO_THEN_INSPECT_LOAD_BEARING_SPANS",
            "boundary": "Canonicalization establishes only probable bibliographic identity; it does not establish version identity, access, attachment, inspection, support, or scholarly correctness.",
        }
        canonical_sources.append(canonical)
        for member in members:
            source = member["source"]
            occurrence_rows.append({
                "schema_version": "1.0", "occurrence_id": member["occurrence_id"],
                "canonical_source_id": canonical_id, "program_key": member["program_key"], "run": member["run"],
                "catalog_disposition": member["catalog_disposition"], "catalog_role": member["catalog_role"],
                "legacy_source_id": member["legacy_source_id"], "title": source.get("title"), "url": source.get("url"),
                "kind": source.get("kind"), "supports": source.get("supports"),
                "does_not_support": source.get("does_not_support") or source.get("does_not_establish"),
                "verified_at_legacy": source.get("verified_at"),
                "reuse_boundary": "Historical interpretation only; reverify source identity and cited span before current use.",
            })

    canonical_sources.sort(key=lambda item: (item["canonical_source_id"], item["title"])); occurrence_rows.sort(key=lambda item: item["occurrence_id"])
    queue = sorted(canonical_sources, key=lambda item: (
        0 if any("canonical_" in str(o["catalog_disposition"]) for o in occurrence_rows if o["canonical_source_id"] == item["canonical_source_id"]) else 1,
        -item["occurrence_count"], item["canonical_source_id"],
    ))
    summary = {
        "legacy_occurrences": len(occurrences), "canonical_sources": len(canonical_sources),
        "merged_occurrences": len(occurrences) - len(canonical_sources),
        "identity_conflicts": sum(item["identity_review"] != "EXACT_NORMALIZED_MATCH" for item in canonical_sources),
        "legacy_id_collisions": sum(item["legacy_id_collision"] for item in canonical_sources),
        "metadata_only": sum(item["access_status"] == "METADATA_ONLY" for item in canonical_sources),
        "fulltext_attached": 0, "fulltext_inspected": 0,
        "program_counts": dict(sorted(Counter(o["program_key"] for o in occurrence_rows).items())),
    }
    return {"summary": summary, "canonical_sources": canonical_sources, "occurrences": occurrence_rows, "queue": queue}


def write_jsonl(path: Path, data: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in data), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("catalog", type=Path); parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(); result = build(args.catalog.resolve()); out = args.out.resolve(); out.mkdir(parents=True, exist_ok=True)
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
