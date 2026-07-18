from html.parser import HTMLParser
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PROTOTYPE = ROOT / "docs" / "prototypes" / "zotero-native-coreading.html"


class ContractParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.mode_buttons = set()
        self.atr_panels = set()
        self.contract_sections = set()
        self.contract_surfaces = set()
        self.selected_contract = None

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if values.get("data-mode-button"):
            self.mode_buttons.add(values["data-mode-button"])
        if values.get("data-atr-dock-key"):
            self.atr_panels.add(values["data-atr-dock-key"])
        if values.get("data-contract-section"):
            self.contract_sections.add(values["data-contract-section"])
        if values.get("data-contract-surface"):
            self.contract_surfaces.add(values["data-contract-surface"])
        if values.get("data-selected-contract"):
            self.selected_contract = values["data-selected-contract"]


class UIPrototypeTest(unittest.TestCase):
    def test_native_coreading_contract_is_repo_local_and_complete(self):
        text = PROTOTYPE.read_text(encoding="utf-8")
        parser = ContractParser()
        parser.feed(text)
        self.assertEqual(parser.mode_buttons, {"dashboard", "note", "reader"})
        self.assertEqual(parser.selected_contract, "native-reader-two-sections")
        self.assertEqual(parser.contract_sections, {"human-note", "atr-context"})
        self.assertEqual(parser.contract_surfaces, {"portable-atr-context"})
        self.assertEqual(parser.atr_panels, {"knowledge", "problem", "detail", "process"})
        self.assertNotIn("fetch(", text)
        self.assertNotIn("http://", text)
        self.assertNotIn("https://", text)


if __name__ == "__main__":
    unittest.main()
