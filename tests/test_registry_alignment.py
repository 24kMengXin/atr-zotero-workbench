import unittest

from atr_zotero_workbench.registry_alignment import align_registry_to_portfolio


def record(key, run_id, role):
    return {
        "key": key, "run_id": run_id, "workspace": "/w/" + key, "run_dir": "/r/" + key,
        "controller_kind": "ATR_V2_SQLITE", "authority_path": "/r/" + key + "/atr.sqlite",
        "authority_scope": "LIFECYCLE_AND_ATTACHMENTS", "view_role": role,
    }


class RegistryAlignmentTest(unittest.TestCase):
    def test_only_declared_children_remain_current_v2_runs(self):
        registry = {
            "runs": [record("old", "old-run", "REGISTERED_V2_RUN"),
                     record("child", "child-run", "HISTORICAL_NAVIGATION"),
                     record("portfolio", "portfolio-run", "REGISTERED_V2_RUN")],
            "active_run": "old", "selection": {"mode": "EXPLICIT", "selected_key": "old"},
        }
        programs = {"children": [{"run_id": "child-run"}]}
        result = align_registry_to_portfolio(registry, programs, "portfolio-run")
        roles = {row["key"]: row["view_role"] for row in result["registry"]["runs"]}
        self.assertEqual(roles, {
            "old": "HISTORICAL_NAVIGATION",
            "child": "REGISTERED_V2_RUN",
            "portfolio": "CURRENT_RUN",
        })
        self.assertEqual(result["registry"]["active_run"], "portfolio")
        self.assertEqual(result["summary"]["demoted_v2_runs"], ["old-run"])

    def test_missing_declared_child_is_rejected(self):
        registry = {
            "runs": [record("portfolio", "portfolio-run", "CURRENT_RUN")],
            "active_run": "portfolio",
            "selection": {"mode": "EXPLICIT", "selected_key": "portfolio"},
        }
        with self.assertRaisesRegex(ValueError, "missing from local registry"):
            align_registry_to_portfolio(
                registry, {"children": [{"run_id": "missing-child"}]}, "portfolio-run"
            )


if __name__ == "__main__":
    unittest.main()
