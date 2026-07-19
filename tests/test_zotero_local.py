import json
import tempfile
import unittest
import urllib.parse
from pathlib import Path

from atr_zotero_workbench.zotero_local import (
    LocalZoteroAPI, pull_local_feedback, pull_registry_feedback,
    snapshot_local_feedback, snapshot_registry_feedback,
)
from atr_zotero_workbench.human_input import impact_report


class FakeAPI(LocalZoteroAPI):
    def __init__(self):
        super().__init__(fetcher=lambda _url: None)
        self.notes = [{
            "key": "N1", "version": 1, "data": {"note": (
                "<h1>Knowledge</h1><p>ATR Knowledge Node: knowledge:K1</p>"
                "<p>ATR Review Stance: PENDING</p><h2>定义</h2><p>generated v1</p>"
                "<h2>我的理解与追问</h2><p>请写下判断。</p>"
            )},
        }]
        self.annotations = [{
            "key": "A1", "version": 1, "data": {"parentItem": "ATT1", "annotationType": "highlight",
                "annotationText": "quoted", "annotationComment": "", "annotationColor": "#ffd400",
                "annotationPageLabel": "2", "annotationPosition": '{"pageIndex":1}'},
            "library": {"type": "user", "id": 1},
        }]
        self.items = {
            "ATT1": {"key": "ATT1", "data": {"parentItem": "P1"}},
            "P1": {"key": "P1", "data": {"extra": "ATR source ID: SRC-1"}},
        }

    def list_items(self, item_type, *, query=None):
        return self.notes if item_type == "note" else self.annotations

    def item(self, key):
        return self.items[key]


class ZoteroLocalFeedbackTest(unittest.TestCase):
    def test_local_api_paginates_beyond_one_hundred_items(self):
        calls = []
        def fetch(url):
            calls.append(url)
            start = int(urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["start"][0])
            count = 100 if start == 0 else 5 if start == 100 else 0
            return [{"key": f"N{start + index}"} for index in range(count)]
        api = LocalZoteroAPI(fetcher=fetch)
        self.assertEqual(len(api.list_items("note", query="ATR")), 105)
        self.assertEqual(len(calls), 2)

    def workspace(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / "graph.json").write_text(json.dumps({
            "run": "run-1", "nodes": [
                {"id": "knowledge:K1", "kind": "knowledge_concept", "label": "K1", "data": {}},
                {"id": "paper:SRC-1", "kind": "paper", "label": "P1", "data": {"source_id": "SRC-1"}},
            ], "edges": [],
        }), encoding="utf-8")
        return temp, root

    def test_snapshot_then_append_note_and_annotation_deltas_once(self):
        temp, workspace = self.workspace()
        self.addCleanup(temp.cleanup)
        api = FakeAPI()
        baseline = snapshot_local_feedback(workspace, api)
        self.assertEqual(baseline["events_appended"], 0)
        api.notes[0]["version"] = 2
        api.notes[0]["data"]["note"] = api.notes[0]["data"]["note"].replace(
            "ATR Review Stance: PENDING", "ATR Review Stance: QUALIFIES").replace(
            "请写下判断。", "只在低资源语言成立。")
        api.annotations[0]["version"] = 2
        api.annotations[0]["data"]["annotationComment"] = "需要核对数据设置"
        report = pull_local_feedback(workspace, api)
        self.assertEqual(report["events_appended"], 2)
        rows = [json.loads(line) for line in (workspace / "human-input" / "inbox.jsonl").read_text().splitlines()]
        self.assertEqual({row["input_origin"] for row in rows}, {"ZOTERO_LOCAL_API_POLL"})
        self.assertEqual(next(row for row in rows if row["event"] == "human_note_modified")["review_stance"], "QUALIFIES")
        annotation = next(row for row in rows if row["event"] == "human_annotation_modified")
        self.assertEqual(annotation["zotero_open_uri"], "zotero://open-pdf/library/items/ATT1?page=2&annotation=A1")
        impact = impact_report(workspace)
        self.assertEqual(impact["latest_feedback_objects"], 2)
        self.assertEqual({row["review_target_type"] for row in impact["affected"]}, {"knowledge", "source"})
        self.assertEqual(pull_local_feedback(workspace, api)["events_appended"], 0)

    def test_new_mapped_annotation_after_baseline_is_feedback(self):
        temp, workspace = self.workspace()
        self.addCleanup(temp.cleanup)
        api = FakeAPI()
        api.annotations = []
        snapshot_local_feedback(workspace, api)
        api.annotations = [{
            "key": "A2", "version": 3, "library": {"type": "user", "id": 1},
            "data": {"parentItem": "ATT1", "annotationType": "highlight", "annotationText": "new",
                     "annotationComment": "human", "annotationColor": "#ffd400",
                     "annotationPageLabel": "3", "annotationPosition": '{"pageIndex":2}'},
        }]
        report = pull_local_feedback(workspace, api)
        self.assertEqual(report["events_appended"], 1)

    def test_generated_section_change_does_not_become_human_feedback(self):
        temp, workspace = self.workspace()
        self.addCleanup(temp.cleanup)
        api = FakeAPI()
        snapshot_local_feedback(workspace, api)
        api.notes[0]["version"] = 2
        api.notes[0]["data"]["note"] = api.notes[0]["data"]["note"].replace("generated v1", "generated v2")
        report = pull_local_feedback(workspace, api)
        self.assertEqual(report["events_appended"], 0)
        self.assertFalse((workspace / "human-input" / "inbox.jsonl").exists())

    def test_pull_refuses_without_explicit_baseline(self):
        temp, workspace = self.workspace()
        self.addCleanup(temp.cleanup)
        with self.assertRaisesRegex(ValueError, "snapshot"):
            pull_local_feedback(workspace, FakeAPI())

    def test_registry_snapshots_and_pulls_separate_workspaces(self):
        temp, workspace = self.workspace()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        second = root / "second"
        second.mkdir()
        (second / "graph.json").write_text(json.dumps({"run": "run-2", "nodes": [], "edges": []}))
        registry = root / "runs.json"
        registry.write_text(json.dumps({
            "schema_version": "0.2", "selection": {"mode": "EXPLICIT"},
            "runs": [{"key": "one", "workspace": str(workspace)},
                     {"key": "two", "workspace": str(second)}],
        }))
        api = FakeAPI()
        result = snapshot_registry_feedback(registry, api)
        self.assertEqual(result["counts"]["baselined"], 1)
        self.assertEqual(result["counts"]["not_materialized"], 1)
        api.notes[0]["version"] = 2
        api.notes[0]["data"]["note"] = api.notes[0]["data"]["note"].replace("PENDING", "CHALLENGES")
        pulled = pull_registry_feedback(registry, api)
        self.assertEqual(pulled["counts"]["events_appended"], 1)
        self.assertEqual(next(row for row in pulled["topics"] if row["key"] == "two")["status"], "MISSING_BASELINE")

    def test_portfolio_program_note_baselines_and_maps_to_exact_program_node(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "graph.json").write_text(json.dumps({
                "run": "portfolio-run", "nodes": [
                    {"id": "portfolio:P1", "kind": "research_portfolio", "label": "Portfolio", "data": {}},
                    {"id": "research_program:child", "kind": "research_program", "label": "Child", "data": {}},
                ], "edges": [],
            }))
            api = FakeAPI()
            api.annotations = []
            api.notes = [{"key": "NP", "version": 1, "data": {"note": (
                "<h1>Program</h1><p>ATR Research Program Node: research_program:child</p>"
                "<p>ATR Review Stance: PENDING</p><h2>我的审查与追问</h2><p>请写下判断。</p>"
            )}}]
            baseline = snapshot_local_feedback(workspace, api)
            self.assertEqual(baseline["notes"], 1)
            api.notes[0]["version"] = 2
            api.notes[0]["data"]["note"] = api.notes[0]["data"]["note"].replace(
                "PENDING", "CHALLENGES").replace("请写下判断。", "这个 program 边界过宽。")
            self.assertEqual(pull_local_feedback(workspace, api)["events_appended"], 1)
            impact = impact_report(workspace)
            self.assertEqual(impact["affected"][0]["annotation_graph_node_id"], "research_program:child")
            self.assertEqual(impact["affected"][0]["review_target_type"], "program")
            self.assertEqual(impact["affected"][0]["nearest_decision_objects"][0]["id"], "research_program:child")


if __name__ == "__main__":
    unittest.main()
