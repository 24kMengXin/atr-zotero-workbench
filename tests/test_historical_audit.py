from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_historical_programs import audit


class HistoricalAuditTest(unittest.TestCase):
    def test_keeps_history_read_only_and_reports_missing_current_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); catalog_dir = root / "catalog"; catalog_dir.mkdir(); run = root / "run"
            (run / "evidence").mkdir(parents=True); (run / "evidence" / "sources.jsonl").write_text('{"source_id":"P1"}\n')
            (run / "run-state.json").write_text(json.dumps({"schema_version":"1.0", "active_stage":"R0_INTAKE"}))
            catalog = {"policy":{"historical_runs_are_read_only":True}, "programs":[{"key":"p","label":"P","root_question":"Q","branches":[{"run":"../run","role":"history","disposition":"retain_as_history"}]}]}
            path = catalog_dir / "catalog.json"; path.write_text(json.dumps(catalog))
            report = audit(path); row = report["programs"][0]["runs"][0]
            self.assertEqual(report["summary"]["run_count"], 1)
            self.assertEqual(row["reusable_as_provenance_input"], ["source_ledger"])
            self.assertIn("missing concept_map", row["not_sufficient_for_current_continuation"])
            self.assertEqual((run / "evidence" / "sources.jsonl").read_text(), '{"source_id":"P1"}\n')
