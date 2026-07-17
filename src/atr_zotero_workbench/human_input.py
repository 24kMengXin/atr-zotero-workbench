"""Consume, never delete, human annotation events emitted by the Zotero companion."""
from __future__ import annotations
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

def _rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists(): return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

def impact_report(output: Path) -> dict[str, Any]:
    graph = json.loads((output / "graph.json").read_text(encoding="utf-8"))
    events = _rows(output / "human-input" / "inbox.jsonl")
    latest = {}
    for event in events:
        if event.get("event") == "human_note_modified": latest[event.get("zotero_note_key")] = event
    by_source = {n["data"].get("source_id"): n["id"] for n in graph["nodes"] if n["kind"] == "paper"}
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph["edges"]:
        adjacency[edge["source"]].add(edge["target"]); adjacency[edge["target"]].add(edge["source"])
    nodes = {n["id"]: n for n in graph["nodes"]}
    affected = []
    for event in latest.values():
        source = event.get("atr_source_id"); start = by_source.get(source)
        questions, queue, seen = [], deque([start] if start else []), {start} if start else set()
        while queue:
            current = queue.popleft()
            if nodes[current]["kind"] == "research_question": questions.append(nodes[current]["label"])
            for neighbor in adjacency[current]:
                if neighbor not in seen: seen.add(neighbor); queue.append(neighbor)
        affected.append({"event": event, "affected_research_questions": questions,
                         "codex_next_action": "请人工审阅该批注；若它挑战来源边界，创建新的 immutable ATR evidence artifact，再由 owner 决定是否重做 route/claim review。"})
    return {"schema_version":"0.1", "projection": "derived-human-input-review", "events_seen":len(events),
            "latest_notes":len(latest), "affected":affected}
