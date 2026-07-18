import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.check_installed_plugin_version import build_report


class InstalledPluginVersionTest(unittest.TestCase):
    def make_fixture(self, *, registered_version="0.5.2", global_updates=False,
                     addon_policy=1):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        profile = root / "profile"
        profile.mkdir()
        addon_id = "workbench@example.test"
        (profile / "extensions.json").write_text(json.dumps({"addons": [{
            "id": addon_id, "version": registered_version, "active": True,
            "userDisabled": False, "updateURL": "https://example.test/update.json",
            "applyBackgroundUpdates": addon_policy, "sourceURI": "file:///old.xpi",
        }]}), encoding="utf-8")
        (profile / "prefs.js").write_text(
            f'user_pref("extensions.update.autoUpdateDefault", {str(global_updates).lower()});\n',
            encoding="utf-8",
        )
        xpi = root / "candidate.xpi"
        with zipfile.ZipFile(xpi, "w") as archive:
            archive.writestr("manifest.json", json.dumps({
                "version": "0.6.6", "applications": {"zotero": {
                    "id": addon_id, "update_url": "https://example.test/update.json",
                }},
            }))
        return temp, xpi, profile

    def test_reports_profile_default_as_stale_update_reason(self):
        temp, xpi, profile = self.make_fixture()
        self.addCleanup(temp.cleanup)
        report = build_report(xpi, profile)
        self.assertFalse(report["effective_background_updates"])
        self.assertEqual(report["addon_background_update_policy"], "FOLLOW_GLOBAL")
        self.assertEqual(report["stale_reason"], "BACKGROUND_UPDATES_DISABLED_BY_PROFILE_DEFAULT")

    def test_explicit_addon_enable_overrides_global_default(self):
        temp, xpi, profile = self.make_fixture(addon_policy=2)
        self.addCleanup(temp.cleanup)
        report = build_report(xpi, profile)
        self.assertTrue(report["effective_background_updates"])
        self.assertIsNone(report["stale_reason"])


if __name__ == "__main__":
    unittest.main()
