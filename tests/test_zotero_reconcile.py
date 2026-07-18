import json
import tempfile
import unittest
from pathlib import Path

from atr_zotero_workbench.zotero_reconcile import _url, reconcile_sources


class ReconcileAPI:
    def __init__(self, pdf):
        self.pdf = pdf

    def top_items(self):
        return [
            {"key": "P1", "data": {"title": "Exact Paper", "DOI": "10.1000/exact",
                "url": "https://doi.org/10.1000/exact", "extra": "ATR source ID: SRC-EXACT"}},
            {"key": "P2", "data": {"title": "Title Candidate", "DOI": "", "url": "", "extra": ""}},
        ]

    def list_items(self, item_type):
        self.assert_annotation_type = item_type
        return [{"key": "A1", "data": {"parentItem": "PDF1"}}]

    def children(self, key):
        if key != "P1": return []
        return [{"key": "PDF1", "data": {"itemType": "attachment", "contentType": "application/pdf",
                 "filename": self.pdf.name, "linkMode": "imported_file"},
                 "links": {"enclosure": {"href": self.pdf.as_uri()}}}]


class ZoteroReconcileTest(unittest.TestCase):
    def test_openreview_forum_id_is_not_discarded(self):
        first = _url("https://openreview.net/forum?id=paperA")
        second = _url("https://openreview.net/forum?id=paperB&noteId=n&referrer=console")
        self.assertNotEqual(first, second)
        self.assertEqual(second, "https://openreview.net/forum?id=paperB")

    def test_exact_locator_with_conflicting_title_is_not_promoted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            inventory = root / "sources.jsonl"
            inventory.write_text(json.dumps({
                "canonical_source_id": "SRC-A", "title": "Expected Paper",
                "url": "https://openreview.net/forum?id=same", "program_keys": [],
                "identity_variants": {"titles": ["Expected Paper"], "urls": []},
            }))
            class API:
                def top_items(self): return [{"key": "P", "data": {"title": "Different Paper", "url": "https://openreview.net/forum?id=same", "extra": "", "DOI": ""}}]
                def list_items(self, _item_type): return []
                def children(self, _key): return []
            row = reconcile_sources(inventory, API())["sources"][0]
            self.assertEqual(row["identity_status"], "EXACT_LOCATOR_TITLE_CONFLICT_REQUIRES_REVIEW")
            self.assertEqual(row["access_status"], "IDENTITY_REVIEW_REQUIRED")

    def test_exact_identity_can_establish_local_pdf_but_not_inspection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            pdf = root / "paper.pdf"; pdf.write_bytes(b"%PDF-1.4\nfixture")
            inventory = root / "sources.jsonl"
            inventory.write_text("\n".join(json.dumps(row) for row in [
                {"canonical_source_id": "SRC-EXACT", "title": "Exact Paper",
                 "url": "https://doi.org/10.1000/exact", "normalized_url": "https://doi.org/10.1000/exact",
                 "program_keys": ["p"], "identity_variants": {"titles": ["Exact Paper"], "urls": []}},
                {"canonical_source_id": "SRC-TITLE", "title": "Title Candidate", "url": "",
                 "program_keys": ["p"], "identity_variants": {"titles": ["Title Candidate"], "urls": []}},
            ]))
            report = reconcile_sources(inventory, ReconcileAPI(pdf))
            self.assertEqual(report["summary"]["exact_identity_matches"], 1)
            self.assertEqual(report["summary"]["local_fulltext"], 1)
            self.assertEqual(report["summary"]["title_matches_requiring_review"], 1)
            exact = next(row for row in report["sources"] if row["canonical_source_id"] == "SRC-EXACT")
            self.assertEqual(exact["access_status"], "ZOTERO_LOCAL_FULLTEXT")
            self.assertEqual(exact["human_annotation_count"], 1)
            self.assertFalse(exact["fulltext_inspected"])
            self.assertEqual(len(exact["pdf_attachments"][0]["sha256"]), 64)
            self.assertNotIn("local_path", exact["pdf_attachments"][0])
            self.assertEqual(exact["pdf_attachments"][0]["zotero_open_uri"], "zotero://open-pdf/library/items/PDF1")
            self.assertEqual(report["summary"]["programs"]["p"]["local_fulltext"], 1)


if __name__ == "__main__":
    unittest.main()
