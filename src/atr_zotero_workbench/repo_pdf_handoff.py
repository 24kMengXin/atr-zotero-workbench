"""Verify repo-local reviewed PDFs for explicit Zotero stored-copy handoff."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any

STOP = {"the", "a", "an", "of", "for", "in", "on", "and", "to", "via", "with",
        "that", "do", "when", "not", "is", "at"}
ALLOWED_HOSTS = {"arxiv.org", "aclanthology.org"}


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tokens(title: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", title.casefold())
            if len(token) > 2 and token not in STOP}


def _identifier(url: str) -> str | None:
    for pattern in (r"arxiv\.org/(?:abs|pdf)/([^/?#]+)", r"aclanthology\.org/([^/?#]+)"):
        match = re.search(pattern, url, re.I)
        if match:
            return re.sub(r"\.pdf$", "", match.group(1), flags=re.I).casefold()
    return None


def verify_graph_pdf(node: dict[str, Any], graph_path: Path, repo_root: Path) -> dict[str, Any]:
    data = node.get("data", {})
    relative = data.get("local_cache_path")
    expected = str(data.get("content_digest") or "")
    url = str(data.get("url") or "")
    host = urllib.parse.urlsplit(url).netloc.casefold().removeprefix("www.")
    result = {"source_id": data.get("source_id"), "title": node.get("label"),
              "program_workspace": graph_path.parent.name, "canonical_url": url,
              "local_cache_path": relative, "content_digest": expected,
              "prior_identity_state": data.get("identity_state"),
              "prior_import_policy": data.get("local_cache_import_policy"),
              "status": "BLOCKED", "reasons": [], "identity_evidence": []}
    if not isinstance(relative, str) or not relative.endswith(".pdf"):
        result["reasons"].append("NO_REPO_PDF_PATH"); return result
    candidate = (repo_root / relative).resolve()
    try:
        candidate.relative_to(repo_root.resolve())
    except ValueError:
        result["reasons"].append("OUTSIDE_REPO"); return result
    if not candidate.is_file():
        result["reasons"].append("FILE_MISSING"); return result
    actual = _sha(candidate)
    if expected != "sha256:" + actual:
        result["reasons"].append("DIGEST_MISMATCH"); return result
    result["identity_evidence"].append({"signal": "BYTE_IDENTITY", "value": expected})
    if host not in ALLOWED_HOSTS:
        result["reasons"].append("NON_CANONICAL_SOURCE_HOST"); return result
    identifier = _identifier(url)
    if not identifier:
        result["reasons"].append("CANONICAL_IDENTIFIER_MISSING"); return result
    prior_evidence = data.get("identity_evidence", [])
    prior_signals = {row.get("signal") for row in prior_evidence if isinstance(row, dict)}
    if (data.get("identity_state") == "IDENTITY_VERIFIED"
            and data.get("local_cache_import_policy") == "ALLOW_ZOTERO_STORED_COPY_ON_EXPLICIT_READ"
            and {"BYTE_IDENTITY", "CANONICAL_IDENTIFIER_IN_LANDING_AND_PDF_ENDPOINT",
                 "FIRST_PAGE_TITLE_TOKEN_MATCH"} <= prior_signals
            and any(row.get("signal") == "BYTE_IDENTITY" and row.get("value") == expected
                    for row in prior_evidence if isinstance(row, dict))):
        result["identity_evidence"].extend(prior_evidence)
        result.update({"status": "IMPORT_READY", "identity_state": "IDENTITY_VERIFIED",
                       "local_cache_import_policy": "ALLOW_ZOTERO_STORED_COPY_ON_EXPLICIT_READ",
                       "fulltext_state": data.get("fulltext_state"),
                       "boundary": "A prior immutable identity handoff plus a fresh repo-boundary/digest check authorizes only an explicit-open Zotero stored copy; it does not establish new scholarly support."})
        return result
    text_result = subprocess.run(["pdftotext", "-f", "1", "-l", "2", str(candidate), "-"],
                                 capture_output=True, text=True, check=False)
    if text_result.returncode:
        result["reasons"].append("PDF_TEXT_EXTRACTION_FAILED"); return result
    text = text_result.stdout.casefold()
    expected_tokens = _tokens(str(node.get("label") or ""))
    matched = sorted(token for token in expected_tokens if token in text)
    coverage = len(matched) / max(1, len(expected_tokens))
    result["identity_evidence"].extend([
        {"signal": "CANONICAL_LOCATOR", "host": host, "identifier": identifier},
        {"signal": "FIRST_TWO_PAGES_TITLE_TOKEN_MATCH", "matched": matched,
         "expected_token_count": len(expected_tokens), "coverage": coverage},
        {"signal": "IDENTIFIER_VISIBLE_IN_FIRST_TWO_PAGES", "value": identifier,
         "observed": identifier in text},
    ])
    if len(expected_tokens) < 4 or coverage < 0.9:
        result["reasons"].append("TITLE_MATCH_INSUFFICIENT"); return result
    result.update({"status": "IMPORT_READY", "identity_state": "IDENTITY_VERIFIED",
                   "local_cache_import_policy": "ALLOW_ZOTERO_STORED_COPY_ON_EXPLICIT_READ",
                   "fulltext_state": data.get("fulltext_state"),
                   "boundary": "Identity/digest verification authorizes a Zotero stored copy only when the person explicitly opens this source; it does not establish scholarly support or new inspection."})
    return result


def audit_repo_pdfs(outputs: Path, repo_root: Path) -> dict[str, Any]:
    handoffs = []
    for graph_path in sorted(outputs.glob("*-v2-intake/graph.json")):
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        for node in graph.get("nodes", []):
            if node.get("kind") != "paper": continue
            data = node.get("data", {})
            if data.get("local_cache_state") != "REPO_RUNTIME_CACHE_NOT_ZOTERO_ATTACHMENT": continue
            handoffs.append(verify_graph_pdf(node, graph_path, repo_root))
    return {"schema_version": "1.0", "artifact_type": "repo-pdf-zotero-handoff-audit",
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "policy": {"explicit_human_open_required": True, "zotero_write_not_performed": True,
                       "repo_boundary_required": True, "digest_required": True,
                       "canonical_locator_and_title_required": True},
            "summary": {"repo_cached_pdfs": len(handoffs),
                        "import_ready": sum(row["status"] == "IMPORT_READY" for row in handoffs),
                        "blocked": sum(row["status"] != "IMPORT_READY" for row in handoffs),
                        "already_preverified": sum(row.get("prior_identity_state") == "IDENTITY_VERIFIED" for row in handoffs)},
            "handoffs": handoffs}


def write_handoff(report: dict[str, Any], out: Path, markdown_out: Path | None = None) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not markdown_out: return
    s = report["summary"]
    lines = ["# Repo PDF → Zotero 显式导入交接", "",
             f"- repo cached PDF：{s['repo_cached_pdfs']}；import ready：{s['import_ready']}；blocked：{s['blocked']}。",
             f"- 其中此前已有 identity handoff：{s['already_preverified']}。本审计没有向 Zotero 写入任何文件。", "",
             "只有路径位于 repo、SHA-256 与已记录摘要一致、来源为 canonical host、且首页标题 token 覆盖≥90% 的 PDF 才可在人的显式打开动作中复制为 Zotero stored attachment。", "",
             "| Source | Workspace | Status | Canonical locator | Digest |", "| --- | --- | --- | --- | --- |"]
    for row in report["handoffs"]:
        lines.append(f"| {row['source_id']} · {row['title']} | {row['program_workspace']} | {row['status']} | {row['canonical_url']} | `{row['content_digest']}` |")
    markdown_out.parent.mkdir(parents=True, exist_ok=True)
    markdown_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
