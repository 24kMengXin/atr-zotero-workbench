"""Safe Zotero export and opt-in Web API writer. No local database access."""
from __future__ import annotations

import json, os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def export_bundle(graph: dict, out: Path) -> None:
    zotero = out / "zotero"; cards = zotero / "reading-cards"
    cards.mkdir(parents=True, exist_ok=True)
    items = []
    for node in graph["nodes"]:
        if node["kind"] != "paper": continue
        data = node["data"]; sid = data["source_id"]
        items.append({"id": sid, "type": "article-journal", "title": node["label"], "URL": data["url"],
                      "keyword": ["ATR", "atr-source-id:" + sid, "atr-source-kind:" + data["source_kind"]],
                      "note": f"ATR source ID: {sid}\nEvidence boundary recorded in reading card."})
        (cards / f"{sid}.md").write_text(
            f"# {node['label']}\n\nATR source ID: `{sid}`\n\n## 来源支持的内容\n\n{data['supports']}\n\n"
            f"## 来源不支持 / 不能推出的内容\n\n{data['does_not_support']}\n\n"
            "## 我的阅读与反驳\n\n- [ ] 我核对了原文的相关段落：\n- [ ] 我不同意或需要澄清的地方：\n- [ ] 这对哪个研究问题有影响：\n", encoding="utf-8")
    (zotero / "items.csl.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def sync_web_api(graph: dict, audit_path: Path) -> dict:
    """Create a dedicated collection then source items and child notes. Requires explicit env credentials."""
    required = {key: os.getenv(key) for key in ("ZOTERO_LIBRARY_TYPE", "ZOTERO_LIBRARY_ID", "ZOTERO_API_KEY")}
    missing = [k for k, v in required.items() if not v]
    if missing: raise RuntimeError("Refusing Zotero write: missing " + ", ".join(missing))
    base = f"https://api.zotero.org/{required['ZOTERO_LIBRARY_TYPE']}s/{required['ZOTERO_LIBRARY_ID']}"
    headers = {"Zotero-API-Key": required["ZOTERO_API_KEY"], "Content-Type": "application/json"}
    def post(path: str, body: list[dict]) -> dict:
        req = Request(base + path, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urlopen(req, timeout=30) as response: return json.loads(response.read() or b"{}")
        except HTTPError as e: raise RuntimeError(f"Zotero API {e.code}: {e.read().decode()}") from e
    collection = post("/collections", [{"name": f"ATR · {graph['run']}"}])
    collection_key = collection["successful"]["0"]["key"]
    records = []
    for node in graph["nodes"]:
        if node["kind"] == "paper":
            d = node["data"]
            records.append({"itemType":"journalArticle", "title":node["label"], "url":d["url"],
                            "extra":f"ATR source ID: {d['source_id']}", "tags":[{"tag":"ATR"}], "collections":[collection_key]})
    item_result = post("/items", records) if records else {}
    notes = []
    for index, node in enumerate(n for n in graph["nodes"] if n["kind"] == "paper"):
        item = item_result.get("successful", {}).get(str(index), {})
        key = item.get("key") if isinstance(item, dict) else None
        if key:
            d = node["data"]
            notes.append({"itemType": "note", "parentItem": key,
                          "note": f"<h1>ATR 阅读卡</h1><p>Source ID: {d['source_id']}</p>"
                                  f"<h2>来源支持的内容</h2><p>{d['supports']}</p>"
                                  f"<h2>来源不支持的内容</h2><p>{d['does_not_support']}</p>"
                                  "<h2>我的阅读与反驳</h2><p></p>"})
    result = {"collection": collection, "items": item_result, "notes": post("/items", notes) if notes else {}}
    audit_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
