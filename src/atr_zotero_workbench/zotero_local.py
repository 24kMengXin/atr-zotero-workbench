"""Recover ATR human feedback through Zotero's read-only local HTTP API.

The plugin notifier remains the low-latency path.  This module is a polling
backstop: it snapshots only the human-owned portion of ATR Notes and mapped
annotations, then appends changed records to the same REVIEW_INPUT_ONLY inbox.
It never writes Zotero or its SQLite database.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

DEFAULT_LOCAL_API = "http://127.0.0.1:23119/api/users/0"
HUMAN_HEADING = re.compile(r"<h2[^>]*>\s*我的[^<]*</h2>", re.I)
NEXT_HEADING = re.compile(r"<h[12][^>]*>", re.I)
STANCE = re.compile(r"ATR Review Stance:\s*(SUPPORTS|QUALIFIES|CHALLENGES|UNSURE|NEW_QUESTION|PENDING|HISTORICAL_REFERENCE_ONLY)")
OWNER_INPUT = re.compile(r"ATR Owner Route Input:\s*(PENDING|ACCEPT_REFRAME|REQUEST_MORE_EVIDENCE|PARK_TOPIC|RETIRE_CANDIDATE)")
MARKERS = {
    "atr_source_id": r"ATR Source ID:\s*([^\s<]+)",
    "atr_claim_id": r"ATR Claim ID:\s*([^\s<]+)",
    "atr_problem_id": r"ATR Problem ID:\s*([^\s<]+)",
    "atr_knowledge_node_id": r"ATR Knowledge Node:\s*([^\s<]+)",
    "atr_tension_node_id": r"ATR Tension Node:\s*([^\s<]+)",
    "atr_reality_signal_gap_node_id": r"ATR Reality Signal Gap:\s*([^\s<]+)",
    "atr_research_question_node_id": r"ATR Research Question Node:\s*([^\s<]+)",
    "atr_derived_question_node_id": r"ATR Derived Question Node:\s*([^\s<]+)",
    "atr_topic_route_node_id": r"ATR Topic Route Node:\s*([^\s<]+)",
    "atr_collision_review_id": r"ATR Collision Review:\s*([^\s<]+)",
    "atr_portfolio_node_id": r"ATR Portfolio Node:\s*([^\s<]+)",
    "atr_program_node_id": r"ATR Research Program Node:\s*([^\s<]+)",
    "atr_legacy_run_node_id": r"ATR Legacy Run Node:\s*([^\s<]+)",
    "atr_alignment_audit_node_id": r"ATR Alignment Audit Node:\s*([^\s<]+)",
    "atr_graph_node_id": r"ATR Graph Node:\s*([^\s<]+)",
}


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def plain_note(note_html: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", note_html))).strip()


def human_review_fragment(note_html: str) -> str:
    """Return only explicit human input plus typed stance/route controls."""
    text = plain_note(note_html)
    controls = " | ".join(filter(None, [
        STANCE.search(text).group(0) if STANCE.search(text) else None,
        OWNER_INPUT.search(text).group(0) if OWNER_INPUT.search(text) else None,
        re.search(r"ATR Owner Route Rationale:\s*(.*?)(?=\s+可选输入：|$)", text).group(0)
        if re.search(r"ATR Owner Route Rationale:\s*(.*?)(?=\s+可选输入：|$)", text) else None,
    ]))
    match = HUMAN_HEADING.search(note_html)
    if not match:
        return controls
    tail = note_html[match.end():]
    next_heading = NEXT_HEADING.search(tail)
    owned = plain_note(tail[:next_heading.start()] if next_heading else tail)
    return controls + "\n" + owned


def note_markers(note_html: str) -> dict[str, str | None]:
    text = plain_note(note_html)
    result = {field: (re.search(pattern, text).group(1) if re.search(pattern, text) else None)
              for field, pattern in MARKERS.items()}
    result["atr_graph_node_id"] = result["atr_graph_node_id"] or next((result[field] for field in (
        "atr_knowledge_node_id", "atr_tension_node_id", "atr_research_question_node_id",
        "atr_derived_question_node_id", "atr_collision_review_id",
        "atr_reality_signal_gap_node_id", "atr_topic_route_node_id",
        "atr_portfolio_node_id", "atr_program_node_id",
        "atr_legacy_run_node_id", "atr_alignment_audit_node_id",
    ) if result[field]), None)
    return result


class LocalZoteroAPI:
    def __init__(self, base_url: str = DEFAULT_LOCAL_API,
                 fetcher: Callable[[str], Any] | None = None):
        self.base_url = base_url.rstrip("/")
        self.fetcher = fetcher or self._fetch
        self._list_cache: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
        self._item_cache: dict[str, dict[str, Any]] = {}
        self._endpoint_cache: dict[str, list[dict[str, Any]]] = {}

    @staticmethod
    def _fetch(url: str) -> Any:
        with urllib.request.urlopen(url, timeout=5) as response:
            return json.load(response)

    def list_items(self, item_type: str, *, query: str | None = None) -> list[dict[str, Any]]:
        cache_key = (item_type, query)
        if cache_key in self._list_cache:
            return self._list_cache[cache_key]
        params = {"itemType": item_type, "limit": 100, "sort": "dateModified", "direction": "desc"}
        if query:
            params.update({"q": query, "qmode": "everything"})
        items: list[dict[str, Any]] = []
        start = 0
        while True:
            page_params = {**params, "start": start}
            page = self.fetcher(self.base_url + "/items?" + urllib.parse.urlencode(page_params))
            if not isinstance(page, list):
                raise ValueError("Zotero local API item list did not return a JSON array")
            items.extend(page)
            if len(page) < 100:
                break
            start += len(page)
        self._list_cache[cache_key] = items
        return items

    def item(self, key: str) -> dict[str, Any]:
        if key not in self._item_cache:
            self._item_cache[key] = self.fetcher(self.base_url + "/items/" + urllib.parse.quote(key))
        return self._item_cache[key]

    def paged_endpoint(self, endpoint: str, **params: Any) -> list[dict[str, Any]]:
        cache_key = endpoint + "?" + urllib.parse.urlencode(sorted(params.items()))
        if cache_key in self._endpoint_cache:
            return self._endpoint_cache[cache_key]
        base_params = {"limit": 100, **params}
        items: list[dict[str, Any]] = []
        start = 0
        while True:
            page = self.fetcher(self.base_url + endpoint + "?" + urllib.parse.urlencode({**base_params, "start": start}))
            if not isinstance(page, list):
                raise ValueError("Zotero local API paged endpoint did not return a JSON array")
            items.extend(page)
            if len(page) < 100:
                break
            start += len(page)
        self._endpoint_cache[cache_key] = items
        return items

    def top_items(self) -> list[dict[str, Any]]:
        return self.paged_endpoint("/items/top", sort="dateModified", direction="desc")

    def children(self, key: str) -> list[dict[str, Any]]:
        return self.paged_endpoint("/items/" + urllib.parse.quote(key) + "/children")

    def refresh(self) -> None:
        self._list_cache.clear()
        self._item_cache.clear()
        self._endpoint_cache.clear()


def _workspace_scope(workspace: Path) -> tuple[dict[str, Any], set[str], set[str]]:
    graph = json.loads((workspace / "graph.json").read_text(encoding="utf-8"))
    node_ids = {str(node["id"]) for node in graph.get("nodes", [])}
    source_ids = {str(node.get("data", {}).get("source_id")) for node in graph.get("nodes", [])
                  if node.get("kind") == "paper" and node.get("data", {}).get("source_id")}
    return graph, node_ids, source_ids


def _note_in_scope(markers: dict[str, Any], node_ids: set[str], source_ids: set[str]) -> bool:
    return bool((markers.get("atr_graph_node_id") in node_ids)
                or (markers.get("atr_source_id") in source_ids)
                or (markers.get("atr_claim_id") and any(markers["atr_claim_id"] == node.rsplit(":", 1)[-1]
                                                         for node in node_ids)))


def _source_id_for_annotation(api: LocalZoteroAPI, annotation: dict[str, Any]) -> tuple[str | None, str | None]:
    attachment_key = annotation.get("data", {}).get("parentItem")
    if not attachment_key:
        return None, None
    attachment = api.item(attachment_key)
    parent_key = attachment.get("data", {}).get("parentItem")
    source_item = api.item(parent_key) if parent_key else attachment
    extra = source_item.get("data", {}).get("extra", "")
    match = re.search(r"(?:^|\n)ATR source ID:\s*([^\s]+)", extra, re.I)
    return (match.group(1) if match else None), attachment_key


def _snapshot(api: LocalZoteroAPI, workspace: Path) -> dict[str, Any]:
    graph, node_ids, source_ids = _workspace_scope(workspace)
    notes: dict[str, Any] = {}
    for item in api.list_items("note", query="ATR"):
        note_html = item.get("data", {}).get("note", "")
        markers = note_markers(note_html)
        if not _note_in_scope(markers, node_ids, source_ids):
            continue
        fragment = human_review_fragment(note_html)
        notes[item["key"]] = {"version": item.get("version"), "review_digest": _digest(fragment)}
    annotations: dict[str, Any] = {}
    for item in api.list_items("annotation"):
        source_id, attachment_key = _source_id_for_annotation(api, item)
        if source_id not in source_ids:
            continue
        data = item.get("data", {})
        annotations[item["key"]] = {
            "version": item.get("version"), "source_id": source_id,
            "attachment_key": attachment_key,
            "digest": _digest(json.dumps({key: data.get(key) for key in (
                "annotationType", "annotationText", "annotationComment", "annotationColor",
                "annotationPageLabel", "annotationPosition")}, sort_keys=True, ensure_ascii=False)),
        }
    return {"schema_version": "0.1", "projection": "zotero-local-api-feedback-cursor",
            "boundary": "READ_ONLY_ZOTERO__REVIEW_INPUT_ONLY_ATR", "workspace_run": graph.get("run"),
            "captured_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "notes": notes, "annotations": annotations}


def _cursor_path(workspace: Path) -> Path:
    return workspace / "human-input" / "local-zotero-api-cursor.json"


def snapshot_local_feedback(workspace: Path, api: LocalZoteroAPI | None = None) -> dict[str, Any]:
    api = api or LocalZoteroAPI()
    cursor = _snapshot(api, workspace)
    if not cursor["notes"]:
        raise ValueError("workspace has no materialized ATR Notes in Zotero; import/open the topic before creating a feedback baseline")
    path = _cursor_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cursor, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"written": str(path), "notes": len(cursor["notes"]),
            "annotations": len(cursor["annotations"]), "events_appended": 0}


def pull_local_feedback(workspace: Path, api: LocalZoteroAPI | None = None) -> dict[str, Any]:
    api = api or LocalZoteroAPI()
    cursor_path = _cursor_path(workspace)
    if not cursor_path.exists():
        raise ValueError("local Zotero cursor is missing; run zotero-local-snapshot after materialization and before human reading")
    previous = json.loads(cursor_path.read_text(encoding="utf-8"))
    current = _snapshot(api, workspace)
    graph, node_ids, source_ids = _workspace_scope(workspace)
    events: list[dict[str, Any]] = []
    note_items = {item["key"]: item for item in api.list_items("note", query="ATR")}
    for key, state in current["notes"].items():
        old = previous.get("notes", {}).get(key)
        if not old or old.get("review_digest") == state["review_digest"]:
            continue
        item = note_items[key]
        note_html = item.get("data", {}).get("note", "")
        markers = note_markers(note_html)
        if not _note_in_scope(markers, node_ids, source_ids):
            continue
        text = plain_note(note_html)
        events.append({
            "schema_version": "0.2", "event": "human_note_modified",
            "input_origin": "ZOTERO_LOCAL_API_POLL", "at": current["captured_at"],
            "atr_run": graph.get("run"), **markers,
            "atr_research_node_id": markers.get("atr_tension_node_id")
                or markers.get("atr_reality_signal_gap_node_id")
                or markers.get("atr_research_question_node_id")
                or markers.get("atr_derived_question_node_id"),
            "review_stance": STANCE.search(text).group(1) if STANCE.search(text) else "UNSPECIFIED",
            "owner_route_input": OWNER_INPUT.search(text).group(1) if OWNER_INPUT.search(text) else None,
            "zotero_note_key": key, "zotero_item_version": item.get("version"),
            "note_html": note_html,
        })
    annotation_items = {item["key"]: item for item in api.list_items("annotation")}
    for key, state in current["annotations"].items():
        old = previous.get("annotations", {}).get(key)
        # An annotation created after the explicit baseline is itself a human
        # reading action. Existing annotations require a content delta.
        if old and old.get("digest") == state["digest"]:
            continue
        item = annotation_items[key]
        data = item.get("data", {})
        library = item.get("library", {})
        scope = (f"groups/{library.get('id')}" if library.get("type") == "group" else "library")
        page = None
        position = data.get("annotationPosition")
        if isinstance(position, str):
            try:
                position = json.loads(position)
            except json.JSONDecodeError:
                position = None
        if isinstance(position, dict) and isinstance(position.get("pageIndex"), int):
            page = position["pageIndex"] + 1
        query = ((f"page={page}&" if page else "") + "annotation=" + urllib.parse.quote(key))
        events.append({
            "schema_version": "0.2", "event": "human_annotation_modified",
            "input_origin": "ZOTERO_LOCAL_API_POLL", "at": current["captured_at"],
            "atr_run": graph.get("run"), "atr_source_id": state["source_id"],
            "zotero_annotation_key": key, "zotero_attachment_key": state["attachment_key"],
            "zotero_item_version": item.get("version"),
            "zotero_library_scope": scope,
            "zotero_open_uri": f"zotero://open-pdf/{scope}/items/{state['attachment_key']}?{query}",
            "annotation_type": data.get("annotationType"), "annotation_text": data.get("annotationText"),
            "annotation_comment": data.get("annotationComment"), "annotation_color": data.get("annotationColor"),
            "annotation_page_label": data.get("annotationPageLabel"),
            "annotation_position": data.get("annotationPosition"),
        })
    inbox = workspace / "human-input" / "inbox.jsonl"
    existing = inbox.read_text(encoding="utf-8").splitlines() if inbox.exists() else []
    seen = {(row.get("event"), row.get("zotero_note_key") or row.get("zotero_annotation_key"),
             row.get("zotero_item_version")) for line in existing if line.strip() for row in [json.loads(line)]}
    appended = [event for event in events if (event["event"], event.get("zotero_note_key")
                or event.get("zotero_annotation_key"), event.get("zotero_item_version")) not in seen]
    if appended:
        inbox.parent.mkdir(parents=True, exist_ok=True)
        with inbox.open("a", encoding="utf-8") as stream:
            for event in appended:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
    cursor_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"written": str(cursor_path), "events_detected": len(events),
            "events_appended": len(appended), "inbox": str(inbox)}


def _registry_workspaces(registry_path: Path) -> list[tuple[str, Path]]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if registry.get("schema_version") != "0.2" or registry.get("selection", {}).get("mode") != "EXPLICIT":
        raise ValueError("registry must use schema 0.2 and EXPLICIT selection")
    rows = []
    for run in registry.get("runs", []):
        if not run.get("key") or not run.get("workspace"):
            raise ValueError("registry run lacks key/workspace")
        rows.append((str(run["key"]), Path(run["workspace"])))
    return rows


def snapshot_registry_feedback(registry_path: Path, api: LocalZoteroAPI | None = None) -> dict[str, Any]:
    api = api or LocalZoteroAPI()
    topics = []
    for key, workspace in _registry_workspaces(registry_path):
        if not (workspace / "graph.json").is_file():
            topics.append({"key": key, "workspace": str(workspace), "status": "MISSING_PROJECTION"})
            continue
        try:
            topics.append({"key": key, "workspace": str(workspace), "status": "BASELINED",
                           **snapshot_local_feedback(workspace, api)})
        except ValueError as error:
            if "no materialized ATR Notes" not in str(error):
                raise
            topics.append({"key": key, "workspace": str(workspace),
                           "status": "NOT_MATERIALIZED_IN_ZOTERO", "reason": str(error)})
    return {"schema_version": "0.1", "projection": "zotero-local-api-registry-snapshot",
            "registry": str(registry_path.resolve()), "lifecycle_effect": "NONE",
            "topics": topics, "counts": {
                "registered": len(topics),
                "baselined": sum(row["status"] == "BASELINED" for row in topics),
                "not_materialized": sum(row["status"] == "NOT_MATERIALIZED_IN_ZOTERO" for row in topics),
                "missing_projection": sum(row["status"] == "MISSING_PROJECTION" for row in topics),
            }}


def pull_registry_feedback(registry_path: Path, api: LocalZoteroAPI | None = None) -> dict[str, Any]:
    api = api or LocalZoteroAPI()
    api.refresh()
    topics = []
    for key, workspace in _registry_workspaces(registry_path):
        if not (workspace / "graph.json").is_file():
            topics.append({"key": key, "workspace": str(workspace), "status": "MISSING_PROJECTION"})
        elif not _cursor_path(workspace).is_file():
            topics.append({"key": key, "workspace": str(workspace), "status": "MISSING_BASELINE"})
        else:
            topics.append({"key": key, "workspace": str(workspace), "status": "PULLED",
                           **pull_local_feedback(workspace, api)})
    return {"schema_version": "0.1", "projection": "zotero-local-api-registry-pull",
            "registry": str(registry_path.resolve()), "lifecycle_effect": "REVIEW_INPUT_ONLY",
            "topics": topics, "counts": {
                "registered": len(topics),
                "pulled": sum(row["status"] == "PULLED" for row in topics),
                "missing_baseline": sum(row["status"] == "MISSING_BASELINE" for row in topics),
                "missing_projection": sum(row["status"] == "MISSING_PROJECTION" for row in topics),
                "events_detected": sum(row.get("events_detected", 0) for row in topics),
                "events_appended": sum(row.get("events_appended", 0) for row in topics),
            }}
