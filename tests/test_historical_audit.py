from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.audit_historical_programs import audit

_REPO_TEST_TMP = Path(__file__).resolve().parents[1] / ".runtime" / "tests"
_REPO_TEST_TMP.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(_REPO_TEST_TMP)


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
            self.assertIn("source access/fulltext state undeclared", row["not_sufficient_for_current_continuation"])
            self.assertEqual(row["alignment_disposition"], "LEGACY_MAP_INPUT_ONLY")
            self.assertEqual(row["artifact_dispositions"][0]["decision"], "REUSE_AFTER_SOURCE_REVERIFICATION")
            self.assertEqual(report["summary"]["source_records_with_access_status"], 0)
            self.assertEqual((run / "evidence" / "sources.jsonl").read_text(), '{"source_id":"P1"}\n')

    def test_sidecar_index_closes_only_the_manifest_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); catalog_dir = root / "catalog"; catalog_dir.mkdir(); run = root / "run"
            (run / "evidence").mkdir(parents=True); (run / "evidence" / "sources.jsonl").write_text('{"source_id":"P1"}\n')
            (run / "run-state.json").write_text(json.dumps({"schema_version":"1.0", "active_stage":"R0_INTAKE"}))
            catalog_path = catalog_dir / "catalog.json"
            catalog_path.write_text(json.dumps({"programs":[{"key":"p","label":"P","root_question":"Q","branches":[{"run":"../run"}]}]}))
            mapping_path = root / "mapping.json"
            mapping_path.write_text(json.dumps({
                "summary":{"manifest_count":2,"run_count":1},
                "manifests":[
                    {"run_id":"run","artifact_id":"A1","original_path":"run/evidence/sources.jsonl"},
                    {"run_id":"run","artifact_id":"A2","original_path":"run/run-state.json"},
                ],
            }))
            report = audit(catalog_path, legacy_mapping_index=mapping_path)
            row = report["programs"][0]["runs"][0]
            self.assertEqual(report["summary"]["runs_with_legacy_manifests"], 1)
            self.assertEqual(report["summary"]["legacy_mapped_sidecar_count"], 2)
            self.assertEqual(row["artifacts"]["legacy_mapped_sidecars"], 2)
            self.assertNotIn("no LEGACY_MAPPED artifact manifests", row["not_sufficient_for_current_continuation"])
            self.assertIn("source access/fulltext state undeclared", row["not_sufficient_for_current_continuation"])
