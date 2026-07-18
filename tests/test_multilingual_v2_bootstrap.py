from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.bootstrap_multilingual_v2_portfolio import stable_write


class MultilingualV2BootstrapTest(unittest.TestCase):
    def test_stable_write_refuses_divergent_definition(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "definition.json"
            stable_write(path, {"a": 1})
            stable_write(path, {"a": 1})
            self.assertEqual(json.loads(path.read_text()), {"a": 1})
            with self.assertRaises(ValueError):
                stable_write(path, {"a": 2})
