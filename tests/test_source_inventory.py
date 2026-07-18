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
