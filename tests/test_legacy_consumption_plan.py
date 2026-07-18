from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_legacy_consumption_plan.py"
SPEC = importlib.util.spec_from_file_location("legacy_plan", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class LegacyConsumptionPlanTest(unittest.TestCase):
    def test_plan_declares_semantic_consumers_without_mutating_run(self):
        with tempfile.TemporaryDirectory(dir=ROOT / ".runtime") as tmp:
            root = Path(tmp)
            run = root / "run-a"
            (run / "evidence").mkdir(parents=True)
            (run / "knowledge").mkdir()
            (run / "run-state.json").write_text(json.dumps({"active_stage": "R2_FOCUSED_REVIEW"}))
            (run / "evidence" / "sources.jsonl").write_text('{"source_id":"S1"}\n')
            (run / "evidence" / "edges.jsonl").write_text("")
            (run / "evidence" / "claims.jsonl").write_text("")
            (run / "knowledge" / "frontier-map.json").write_text("{}")
            catalog = root / "catalog.json"
            catalog.write_text(json.dumps({"programs": [{
                "key": "program-a", "branches": [{"run": "run-a"}],
            }]}))
            registry = root / "registry.json"
            registry.write_text(json.dumps({"programs": [{
                "program_key": "program-a", "run_id": "current-a",
            }]}))
            before = {path.relative_to(run).as_posix(): path.read_bytes() for path in run.rglob("*") if path.is_file()}
            plan = MODULE.build(catalog, registry, root)
            after = {path.relative_to(run).as_posix(): path.read_bytes() for path in run.rglob("*") if path.is_file()}
            self.assertEqual(before, after)
            self.assertEqual(plan["expected_run_count"], 1)
            by_path = {entry["path"]: entry for entry in plan["entries"]}
            self.assertIn("run-a/evidence/sources.jsonl", by_path)
            self.assertIn("multilingual-source-inventory:v1.0", by_path["run-a/evidence/sources.jsonl"]["consumed_by"])
            self.assertEqual(by_path["run-a/knowledge/frontier-map.json"]["decision"], "REUSE_AS_HISTORICAL_FRONTIER_INPUT")
            self.assertNotIn("run-a/evidence/claims.jsonl", by_path)


if __name__ == "__main__":
    unittest.main()
