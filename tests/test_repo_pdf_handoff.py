import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from atr_zotero_workbench.repo_pdf_handoff import verify_graph_pdf


class RepoPDFHandoffTest(unittest.TestCase):
    def fixture(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        runtime = root / ".runtime"; runtime.mkdir()
        pdf = runtime / "paper.pdf"; pdf.write_bytes(b"pdf-fixture")
        digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        node = {"kind": "paper", "label": "Agent Memory Retains and Reflects",
                "data": {"source_id": "SRC-1", "url": "https://arxiv.org/abs/2601.12345",
                         "local_cache_path": ".runtime/paper.pdf", "content_digest": "sha256:" + digest,
                         "local_cache_state": "REPO_RUNTIME_CACHE_NOT_ZOTERO_ATTACHMENT",
                         "fulltext_state": "FULLTEXT_INSPECTED"}}
        return temp, root, node

    @patch("atr_zotero_workbench.repo_pdf_handoff.subprocess.run")
    def test_verified_repo_pdf_becomes_explicit_open_handoff(self, run):
        temp, root, node = self.fixture(); self.addCleanup(temp.cleanup)
        run.return_value.returncode = 0
        run.return_value.stdout = "Agent Memory Retains and Reflects arXiv:2601.12345"
        result = verify_graph_pdf(node, root / "output/topic/graph.json", root)
        self.assertEqual(result["status"], "IMPORT_READY")
        self.assertEqual(result["identity_state"], "IDENTITY_VERIFIED")
        self.assertEqual(result["local_cache_import_policy"], "ALLOW_ZOTERO_STORED_COPY_ON_EXPLICIT_READ")

    @patch("atr_zotero_workbench.repo_pdf_handoff.subprocess.run")
    def test_digest_mismatch_blocks_handoff_before_text_claim(self, run):
        temp, root, node = self.fixture(); self.addCleanup(temp.cleanup)
        node["data"]["content_digest"] = "sha256:" + "0" * 64
        result = verify_graph_pdf(node, root / "output/topic/graph.json", root)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("DIGEST_MISMATCH", result["reasons"])
        run.assert_not_called()

    @patch("atr_zotero_workbench.repo_pdf_handoff.subprocess.run")
    def test_prior_immutable_identity_handoff_is_respected_after_fresh_digest_check(self, run):
        temp, root, node = self.fixture(); self.addCleanup(temp.cleanup)
        digest = node["data"]["content_digest"]
        node["data"].update({
            "identity_state": "IDENTITY_VERIFIED",
            "local_cache_import_policy": "ALLOW_ZOTERO_STORED_COPY_ON_EXPLICIT_READ",
            "identity_evidence": [
                {"signal": "CANONICAL_IDENTIFIER_IN_LANDING_AND_PDF_ENDPOINT", "value": "2601.12345"},
                {"signal": "FIRST_PAGE_TITLE_TOKEN_MATCH", "matched": ["agent"]},
                {"signal": "BYTE_IDENTITY", "value": digest},
            ],
        })
        result = verify_graph_pdf(node, root / "output/topic/graph.json", root)
        self.assertEqual(result["status"], "IMPORT_READY")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
