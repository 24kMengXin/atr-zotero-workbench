from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.build_multilingual_source_inventory import build, normalize_url


class SourceInventoryTest(unittest.TestCase):
    def test_arxiv_abs_pdf_and_versions_normalize_to_one_work(self):
        self.assertEqual(normalize_url("https://arxiv.org/pdf/2501.12345v2.pdf"), "https://arxiv.org/abs/2501.12345")
        self.assertEqual(normalize_url("https://arxiv.org/abs/2501.12345"), "https://arxiv.org/abs/2501.12345")
        self.assertEqual(normalize_url("https://aclanthology.org/2026.findings-acl.1.pdf"), "https://aclanthology.org/2026.findings-acl.1")

    def test_deduplicates_identity_but_preserves_occurrences_and_boundaries(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); catalog_dir = root / "catalog"; catalog_dir.mkdir()
            for name, url, support in (("a", "https://arxiv.org/abs/2501.12345", "A"), ("b", "https://arxiv.org/pdf/2501.12345v2.pdf", "B")):
                run = root / name; (run / "evidence").mkdir(parents=True)
                (run / "evidence" / "sources.jsonl").write_text(json.dumps({
                    "source_id": "S-" + name, "title": "Same Paper", "url": url,
                    "kind": "PRIMARY_PREPRINT", "supports": support, "does_not_support": "not all",
                }) + "\n")
            catalog = {"programs": [{"key": "p", "branches": [
                {"run": "../a", "disposition": "canonical_x", "role": "first"},
                {"run": "../b", "disposition": "merge_as_x", "role": "second"},
            ]}]}
            path = catalog_dir / "catalog.json"; path.write_text(json.dumps(catalog))
            result = build(path)
            self.assertEqual(result["summary"]["canonical_sources"], 1)
            self.assertEqual(result["summary"]["legacy_occurrences"], 2)
            self.assertEqual({row["supports"] for row in result["occurrences"]}, {"A", "B"})
            self.assertEqual(result["canonical_sources"][0]["access_status"], "METADATA_ONLY")

    def test_adds_only_new_sources_from_current_immutable_reviewed_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); catalog_dir = root / "catalog"; catalog_dir.mkdir()
            legacy = root / "legacy"; (legacy / "evidence").mkdir(parents=True)
            (legacy / "evidence" / "sources.jsonl").write_text(json.dumps({
                "source_id": "SRC-OLD", "title": "Old Paper", "url": "https://example.org/old",
                "kind": "PRIMARY_PAPER", "supports": "legacy",
            }) + "\n")
            catalog_path = catalog_dir / "catalog.json"
            catalog_path.write_text(json.dumps({"programs": [{"key": "p", "branches": [{
                "run": "../legacy", "disposition": "canonical_x", "role": "first",
            }]}]}))
            registry = root / "registry.json"
            registry.write_text(json.dumps({"programs": [{"program_key": "p", "run_id": "current"}]}))
            body_dir = root / "runs" / "current" / "artifacts" / "abc123"
            body_dir.mkdir(parents=True)
            (body_dir / "body.json").write_text(json.dumps({
                "artifact_type": "knowledge-map", "schema_version": "1.1", "created_at": "2026-01-01",
                "sources": [
                    {"source_id": "SRC-OLD", "title": "Old Paper", "url": "https://example.org/old",
                     "inspection_state": "FULLTEXT_INSPECTED"},
                    {"source_id": "SRC-NEW", "title": "New Paper", "url": "https://example.org/new",
                     "kind": "PRIMARY_PAPER", "inspection_state": "FULLTEXT_INSPECTED",
                     "inspection_spans": [{"locator": "p. 2", "observation": "bounded"}]},
                ],
            }))
            result = build(catalog_path, current_registry=registry, runs_root=root / "runs")
            self.assertEqual(result["summary"]["legacy_occurrences"], 1)
            self.assertEqual(result["summary"]["current_v2_reviewed_additions"], 1)
            self.assertEqual(result["summary"]["canonical_sources"], 2)
            current = next(row for row in result["canonical_sources"] if row["canonical_source_id"] == "SRC-NEW")
            self.assertEqual(current["origin_layers"], ["CURRENT_V2_REVIEWED_SOURCE"])
            self.assertTrue(current["fulltext_inspected"])
            self.assertEqual(current["inspected_locators"], ["p. 2"])
            occurrence = next(row for row in result["occurrences"] if row["canonical_source_id"] == "SRC-NEW")
            self.assertEqual(occurrence["artifact_digest"], "abc123")
            self.assertEqual(occurrence["origin_layer"], "CURRENT_V2_REVIEWED_SOURCE")
