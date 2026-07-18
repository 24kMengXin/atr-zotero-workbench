"""Reconcile canonical ATR sources with real Zotero items and local PDFs."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import unicodedata
import urllib.parse
from collections import defaultdict
from pathlib import Path
from typing import Any

from .zotero_local import LocalZoteroAPI


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _title(value: str | None) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return re.sub(r"[^\w]+", " ", value).strip()


def _doi(value: str | None) -> str | None:
    match = re.search(r"10\.\d{4,9}/[^\s?#]+", urllib.parse.unquote(value or ""), re.I)
    return match.group(0).rstrip(".,)").casefold() if match else None


def _arxiv(value: str | None) -> str | None:
    value = urllib.parse.unquote(value or "")
    match = re.search(r"(?:arxiv(?:\.org/(?:abs|pdf)/|:))([a-z-]+/\d{7}|\d{4}\.\d{4,5})(?:v\d+)?", value, re.I)
    return match.group(1).casefold() if match else None


def _url(value: str | None) -> str | None:
    if not value or not re.match(r"https?://", value, re.I):
        return None
    parsed = urllib.parse.urlsplit(value)
    host = parsed.netloc.casefold().removeprefix("www.")
    path = parsed.path.rstrip("/")
    query_rows = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    if host == "openreview.net" and path == "/forum":
        # The forum id is the scholarly-work identity. noteId/referrer are UI
        # state and must not collapse different submissions to /forum.
        query_rows = [(key, val) for key, val in query_rows if key == "id"]
    else:
        query_rows = [(key, val) for key, val in query_rows
                      if not key.casefold().startswith("utm_")
                      and key.casefold() not in {"ref", "referrer", "source"}]
    query = urllib.parse.urlencode(sorted(query_rows))
    return urllib.parse.urlunsplit(("https", host, path, query, ""))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_pdf(attachment: dict[str, Any]) -> dict[str, Any] | None:
    data = attachment.get("data", {})
    if data.get("itemType") != "attachment" or data.get("contentType") != "application/pdf":
        return None
    href = attachment.get("links", {}).get("enclosure", {}).get("href")
    if not href or not href.startswith("file://"):
        return None
    path = Path(urllib.parse.unquote(urllib.parse.urlsplit(href).path))
    if not path.is_file():
        return None
    return {"attachment_key": attachment.get("key"), "filename": data.get("filename"),
            "link_mode": data.get("linkMode"),
            "zotero_open_uri": f"zotero://open-pdf/library/items/{attachment.get('key')}",
            "size_bytes": path.stat().st_size, "sha256": _sha256(path)}


def reconcile_sources(inventory: Path, api: LocalZoteroAPI | None = None) -> dict[str, Any]:
    api = api or LocalZoteroAPI()
    sources = _rows(inventory)
    items = api.top_items()
    annotations = api.list_items("annotation")
    annotations_by_attachment: dict[str, int] = defaultdict(int)
    for annotation in annotations:
        parent = annotation.get("data", {}).get("parentItem")
        if parent:
            annotations_by_attachment[str(parent)] += 1

    indices: dict[str, dict[str, set[str]]] = {
        "source_id": defaultdict(set), "doi": defaultdict(set), "arxiv": defaultdict(set),
        "url": defaultdict(set), "title": defaultdict(set),
    }
    by_key = {str(item["key"]): item for item in items}
    for item in items:
        key, data = str(item["key"]), item.get("data", {})
        extra = data.get("extra", "") or ""
        for match in re.findall(r"(?:^|\n)ATR source ID:\s*([^\s]+)", extra, re.I):
            indices["source_id"][match].add(key)
        for candidate in (data.get("DOI"), data.get("url"), extra):
            if _doi(candidate): indices["doi"][_doi(candidate)].add(key)
            if _arxiv(candidate): indices["arxiv"][_arxiv(candidate)].add(key)
        if _url(data.get("url")): indices["url"][_url(data.get("url"))].add(key)
        if _title(data.get("title")): indices["title"][_title(data.get("title"))].add(key)

    reconciled = []
    for source in sources:
        source_id = str(source["canonical_source_id"])
        variants = source.get("identity_variants", {})
        urls = [source.get("url"), source.get("normalized_url"), *variants.get("urls", [])]
        titles = [source.get("title"), *variants.get("titles", [])]
        exact: dict[str, set[str]] = defaultdict(set)
        exact["EXACT_ATR_SOURCE_ID"] |= indices["source_id"].get(source_id, set())
        for value in urls:
            if _doi(value): exact["EXACT_DOI"] |= indices["doi"].get(_doi(value), set())
            if _arxiv(value): exact["EXACT_ARXIV_ID"] |= indices["arxiv"].get(_arxiv(value), set())
            if _url(value): exact["EXACT_NORMALIZED_URL"] |= indices["url"].get(_url(value), set())
        exact_keys = set().union(*exact.values()) if exact else set()
        title_keys = set().union(*(indices["title"].get(_title(value), set()) for value in titles if _title(value)))
        if len(exact_keys) == 1:
            item_key = next(iter(exact_keys))
            methods = sorted(method for method, keys in exact.items() if item_key in keys)
            item_title = _title(by_key.get(item_key, {}).get("data", {}).get("title"))
            source_titles = {_title(value) for value in titles if _title(value)}
            status = ("EXACT_IDENTITY_MATCH" if not source_titles or item_title in source_titles
                      else "EXACT_LOCATOR_TITLE_CONFLICT_REQUIRES_REVIEW")
        elif len(exact_keys) > 1:
            item_key, methods, status = None, sorted(exact), "AMBIGUOUS_EXACT_MATCH"
        elif len(title_keys) == 1:
            item_key, methods, status = next(iter(title_keys)), ["EXACT_NORMALIZED_TITLE"], "TITLE_MATCH_REQUIRES_REVIEW"
        elif len(title_keys) > 1:
            item_key, methods, status = None, ["EXACT_NORMALIZED_TITLE"], "AMBIGUOUS_TITLE_MATCH"
        else:
            item_key, methods, status = None, [], "NOT_FOUND_IN_ZOTERO"
        pdfs: list[dict[str, Any]] = []
        if item_key and status == "EXACT_IDENTITY_MATCH":
            pdfs = [pdf for child in api.children(item_key) if (pdf := _local_pdf(child))]
            for pdf in pdfs:
                pdf["annotation_count"] = annotations_by_attachment.get(str(pdf["attachment_key"]), 0)
        access = ("ZOTERO_LOCAL_FULLTEXT" if pdfs else "ZOTERO_ITEM_NO_LOCAL_FULLTEXT"
                  if item_key and status == "EXACT_IDENTITY_MATCH" else "IDENTITY_REVIEW_REQUIRED"
                  if item_key or "AMBIGUOUS" in status else "NOT_FOUND_IN_ZOTERO")
        item = by_key.get(item_key or "", {})
        reconciled.append({
            "canonical_source_id": source_id, "title": source.get("title"),
            "program_keys": source.get("program_keys", []), "identity_status": status,
            "match_methods": methods, "zotero_item_key": item_key,
            "zotero_item_title": item.get("data", {}).get("title"),
            "access_status": access, "local_fulltext": bool(pdfs), "pdf_attachments": pdfs,
            "human_annotation_count": sum(pdf["annotation_count"] for pdf in pdfs),
            "fulltext_inspected": False,
            "boundary": "A Zotero item/PDF match establishes local availability only; it does not establish that a worker inspected load-bearing spans or that any scholarly claim is valid.",
        })
    item_to_exact_sources: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in reconciled:
        if row["identity_status"] == "EXACT_IDENTITY_MATCH" and row.get("zotero_item_key"):
            item_to_exact_sources[row["zotero_item_key"]].append(row)
    for item_key, rows in item_to_exact_sources.items():
        if len(rows) <= 1:
            continue
        for row in rows:
            row["identity_status"] = "ZOTERO_ITEM_COLLISION_REQUIRES_REVIEW"
            row["access_status"] = "IDENTITY_REVIEW_REQUIRED"
            row["local_fulltext"] = False
            row["pdf_attachments"] = []
            row["human_annotation_count"] = 0
    counts = defaultdict(int)
    for row in reconciled:
        counts[row["identity_status"]] += 1
    programs: dict[str, dict[str, int]] = {}
    for row in reconciled:
        for program in row.get("program_keys", []):
            bucket = programs.setdefault(program, {"canonical_sources": 0, "exact_identity_matches": 0,
                "local_fulltext": 0, "identity_review_required": 0, "not_found": 0})
            bucket["canonical_sources"] += 1
            bucket["exact_identity_matches"] += row["identity_status"] == "EXACT_IDENTITY_MATCH"
            bucket["local_fulltext"] += row["local_fulltext"]
            bucket["identity_review_required"] += row["access_status"] == "IDENTITY_REVIEW_REQUIRED"
            bucket["not_found"] += row["identity_status"] == "NOT_FOUND_IN_ZOTERO"
    return {"schema_version": "1.0", "artifact_type": "zotero-local-source-reconciliation",
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "inventory": str(inventory.resolve()), "zotero_api": "http://127.0.0.1:23119/api/users/0",
            "policy": {"zotero_read_only": True, "no_download": True,
                       "availability_is_not_inspection": True, "title_only_requires_review": True},
            "summary": {"canonical_sources": len(sources), "zotero_top_items": len(items),
                        "exact_identity_matches": counts["EXACT_IDENTITY_MATCH"],
                        "local_fulltext": sum(row["local_fulltext"] for row in reconciled),
                        "items_without_local_fulltext": sum(row["access_status"] == "ZOTERO_ITEM_NO_LOCAL_FULLTEXT" for row in reconciled),
                        "title_matches_requiring_review": counts["TITLE_MATCH_REQUIRES_REVIEW"],
                        "identity_conflicts_requiring_review": counts["EXACT_LOCATOR_TITLE_CONFLICT_REQUIRES_REVIEW"] + counts["ZOTERO_ITEM_COLLISION_REQUIRES_REVIEW"],
                        "ambiguous_matches": counts["AMBIGUOUS_EXACT_MATCH"] + counts["AMBIGUOUS_TITLE_MATCH"],
                        "not_found": counts["NOT_FOUND_IN_ZOTERO"],
                        "matched_human_annotations": sum(row["human_annotation_count"] for row in reconciled),
                        "fulltext_inspected": 0, "programs": dict(sorted(programs.items()))},
            "sources": reconciled}


def write_reconciliation(report: dict[str, Any], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_reconciliation_markdown(report: dict[str, Any], out: Path) -> None:
    summary = report["summary"]
    lines = ["# Canonical sources × Zotero 本地文库对账", "",
        f"- canonical source：{summary['canonical_sources']}；Zotero 顶层条目：{summary['zotero_top_items']}。",
        f"- 严格身份匹配：{summary['exact_identity_matches']}；其中确认存在本地 PDF：{summary['local_fulltext']}；只有书目无本地 PDF：{summary['items_without_local_fulltext']}。",
        f"- 仅标题候选：{summary['title_matches_requiring_review']}；身份冲突：{summary['identity_conflicts_requiring_review']}；Zotero 未找到：{summary['not_found']}。",
        f"- 匹配 PDF 上已有人的 annotation：{summary['matched_human_annotations']}；按 ATR load-bearing span 合同完成全文检查：{summary['fulltext_inspected']}。", "",
        "`ZOTERO_LOCAL_FULLTEXT` 只证明 Zotero 中存在可读 PDF，并由文件摘要确认；不证明 worker 已读全文，不证明来源支持任何 claim。标题匹配不升级 access/fulltext 状态。", "",
        "## 按 program", "", "| Program | canonical | exact | local PDF | identity review | not found |",
        "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for program, row in summary["programs"].items():
        lines.append(f"| {program} | {row['canonical_sources']} | {row['exact_identity_matches']} | {row['local_fulltext']} | {row['identity_review_required']} | {row['not_found']} |")
    lines.extend(["", "## 已确认的 Zotero 本地全文", "",
                  "| Source | Zotero item | PDF attachment | annotations | SHA-256 |", "| --- | --- | --- | ---: | --- |"])
    for row in report["sources"]:
        for pdf in row.get("pdf_attachments", []):
            lines.append(f"| {row['canonical_source_id']} · {row['title']} | {row['zotero_item_key']} | {pdf['attachment_key']} · {pdf.get('filename') or ''} | {pdf['annotation_count']} | `{pdf['sha256']}` |")
    lines.extend(["", "## 仍需身份复核的标题候选", "", "| Source | Zotero item | Title |", "| --- | --- | --- |"])
    for row in report["sources"]:
        if row["access_status"] == "IDENTITY_REVIEW_REQUIRED":
            lines.append(f"| {row['canonical_source_id']} | {row.get('zotero_item_key') or '—'} | {row['title']} |")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
