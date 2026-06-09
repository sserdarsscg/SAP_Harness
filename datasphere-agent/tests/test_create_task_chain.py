"""
Unit tests for the create_task_chain skill (Skill 7).

Tests the pure-Python logic only — no CLI calls, no Datasphere connection.
"""

import sys
import os
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from skills.create_task_chain import (
    build_task_chain_csn,
    derive_tc_name,
    execute,
)


# ---------------------------------------------------------------------------
# Tests: derive_tc_name
# ---------------------------------------------------------------------------

class TestDeriveTcName(unittest.TestCase):

    def test_standard_tf_name(self):
        self.assertEqual(derive_tc_name("TF_BILLING_DOC_JOINED"), "TC_TF_BILLING_DOC_JOINED")

    def test_short_tf_name(self):
        self.assertEqual(derive_tc_name("TF_TEST"), "TC_TF_TEST")

    def test_tf_test_copy(self):
        """Matches reference JSON example name."""
        self.assertEqual(derive_tc_name("TF_TEST_COPY"), "TC_TF_TEST_COPY")

    def test_1_to_1_relationship(self):
        """Every distinct TF name produces a distinct TC name."""
        names = ["TF_A", "TF_B", "TF_C"]
        derived = [derive_tc_name(n) for n in names]
        self.assertEqual(len(set(derived)), 3)


# ---------------------------------------------------------------------------
# Tests: build_task_chain_csn — structure
# ---------------------------------------------------------------------------

class TestBuildTaskChainCsn(unittest.TestCase):

    def setUp(self):
        self.csn = build_task_chain_csn(
            tc_name="TC_TF_BILLING_DOC_JOINED",
            tf_name="TF_BILLING_DOC_JOINED",
        )

    def test_top_level_keys(self):
        """CSN must have version, meta, $version, and taskchains top-level keys."""
        self.assertIn("version", self.csn)
        self.assertIn("meta", self.csn)
        self.assertIn("$version", self.csn)
        self.assertIn("taskchains", self.csn)

    def test_no_definitions_key(self):
        """Task chains use the taskchains key, not definitions."""
        self.assertNotIn("definitions", self.csn)

    def test_tc_name_is_key_in_taskchains(self):
        self.assertIn("TC_TF_BILLING_DOC_JOINED", self.csn["taskchains"])

    def test_kind_is_task_chain(self):
        tc_def = self.csn["taskchains"]["TC_TF_BILLING_DOC_JOINED"]
        self.assertEqual(tc_def["kind"], "sap.dwc.taskChain")

    def test_label_matches_tc_name(self):
        tc_def = self.csn["taskchains"]["TC_TF_BILLING_DOC_JOINED"]
        self.assertEqual(tc_def["@EndUserText.label"], "TC_TF_BILLING_DOC_JOINED")

    def test_schema_version_is_2(self):
        tc_def = self.csn["taskchains"]["TC_TF_BILLING_DOC_JOINED"]
        self.assertEqual(tc_def["schemaVersion"], 2)

    def test_options_layout_vertical(self):
        tc_def = self.csn["taskchains"]["TC_TF_BILLING_DOC_JOINED"]
        self.assertEqual(tc_def["options"]["layout"], "VERTICAL")


# ---------------------------------------------------------------------------
# Tests: nodes
# ---------------------------------------------------------------------------

class TestTaskChainNodes(unittest.TestCase):

    def setUp(self):
        csn = build_task_chain_csn(
            tc_name="TC_TF_TEST",
            tf_name="TF_TEST",
        )
        self.tc_def = csn["taskchains"]["TC_TF_TEST"]
        self.nodes = self.tc_def["nodes"]

    def test_exactly_two_nodes(self):
        self.assertEqual(len(self.nodes), 2)

    def test_node_0_is_start(self):
        start = next(n for n in self.nodes if n["id"] == 0)
        self.assertEqual(start["type"], "START")

    def test_node_1_is_task(self):
        task = next(n for n in self.nodes if n["id"] == 1)
        self.assertEqual(task["type"], "TASK")

    def test_task_node_application_id(self):
        task = next(n for n in self.nodes if n["id"] == 1)
        self.assertEqual(task["taskIdentifier"]["applicationId"], "TRANSFORMATION_FLOWS")

    def test_task_node_activity(self):
        task = next(n for n in self.nodes if n["id"] == 1)
        self.assertEqual(task["taskIdentifier"]["activity"], "EXECUTE")

    def test_task_node_object_id_matches_tf_name(self):
        task = next(n for n in self.nodes if n["id"] == 1)
        self.assertEqual(task["taskIdentifier"]["objectId"], "TF_TEST")

    def test_task_node_ignore_error_false(self):
        task = next(n for n in self.nodes if n["id"] == 1)
        self.assertFalse(task["ignoreError"])


# ---------------------------------------------------------------------------
# Tests: links
# ---------------------------------------------------------------------------

class TestTaskChainLinks(unittest.TestCase):

    def setUp(self):
        csn = build_task_chain_csn(tc_name="TC_TF_TEST", tf_name="TF_TEST")
        self.links = csn["taskchains"]["TC_TF_TEST"]["links"]

    def test_exactly_one_link(self):
        self.assertEqual(len(self.links), 1)

    def test_link_start_node_id_is_0(self):
        self.assertEqual(self.links[0]["startNode"]["nodeId"], 0)

    def test_link_status_required_any(self):
        self.assertEqual(self.links[0]["startNode"]["statusRequired"], "ANY")

    def test_link_end_node_id_is_1(self):
        self.assertEqual(self.links[0]["endNode"]["nodeId"], 1)

    def test_link_id_is_0(self):
        self.assertEqual(self.links[0]["id"], 0)


# ---------------------------------------------------------------------------
# Tests: folder / _meta
# ---------------------------------------------------------------------------

class TestFolderAssignment(unittest.TestCase):

    def test_meta_absent_when_no_folder(self):
        csn = build_task_chain_csn(tc_name="TC_TF_TEST", tf_name="TF_TEST")
        tc_def = csn["taskchains"]["TC_TF_TEST"]
        self.assertNotIn("_meta", tc_def)

    def test_meta_present_when_folder_given(self):
        csn = build_task_chain_csn(
            tc_name="TC_TF_TEST",
            tf_name="TF_TEST",
            folder="Folder_KJTYBRLA",
        )
        tc_def = csn["taskchains"]["TC_TF_TEST"]
        self.assertIn("_meta", tc_def)
        self.assertEqual(
            tc_def["_meta"]["dependencies"]["folderAssignment"],
            "Folder_KJTYBRLA",
        )

    def test_meta_absent_when_folder_none(self):
        csn = build_task_chain_csn(tc_name="TC_TF_TEST", tf_name="TF_TEST", folder=None)
        tc_def = csn["taskchains"]["TC_TF_TEST"]
        self.assertNotIn("_meta", tc_def)


# ---------------------------------------------------------------------------
# Tests: execute() — dry-run
# ---------------------------------------------------------------------------

class TestExecuteDryRun(unittest.TestCase):

    def test_dry_run_status(self):
        result = execute({"tf_name": "TF_BILLING_DOC_JOINED"})
        self.assertEqual(result["status"], "dry_run")

    def test_dry_run_tc_name_derived(self):
        result = execute({"tf_name": "TF_BILLING_DOC_JOINED"})
        self.assertEqual(result["tc_name"], "TC_TF_BILLING_DOC_JOINED")

    def test_dry_run_tf_name_uppercased(self):
        result = execute({"tf_name": "tf_billing_doc_joined"})
        self.assertEqual(result["tf_name"], "TF_BILLING_DOC_JOINED")

    def test_dry_run_csn_present(self):
        result = execute({"tf_name": "TF_BILLING_DOC_JOINED"})
        self.assertIn("tc_csn", result)
        self.assertIn("taskchains", result["tc_csn"])

    def test_dry_run_space_defaults(self):
        result = execute({"tf_name": "TF_BILLING_DOC_JOINED"})
        self.assertEqual(result["space_id"], "ZZ_BDC_HARNESS_1")

    def test_dry_run_folder_none_by_default(self):
        result = execute({"tf_name": "TF_BILLING_DOC_JOINED"})
        self.assertIsNone(result["folder"])

    def test_dry_run_with_folder(self):
        result = execute({"tf_name": "TF_TEST", "folder": "Folder_KJTYBRLA"})
        self.assertEqual(result["folder"], "Folder_KJTYBRLA")
        tc_def = result["tc_csn"]["taskchains"]["TC_TF_TEST"]
        self.assertIn("_meta", tc_def)

    def test_dry_run_tc_name_override(self):
        result = execute({"tf_name": "TF_TEST", "tc_name": "TC_MY_CUSTOM_NAME"})
        self.assertEqual(result["tc_name"], "TC_MY_CUSTOM_NAME")

    def test_dry_run_next_step_hint(self):
        result = execute({"tf_name": "TF_TEST"})
        self.assertIn("next_step", result)
        self.assertIn("deploy=true", result["next_step"])


# ---------------------------------------------------------------------------
# Tests: execute() — validation errors
# ---------------------------------------------------------------------------

class TestExecuteValidation(unittest.TestCase):

    def test_missing_tf_name_returns_error(self):
        result = execute({})
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("tf_name" in e for e in result["errors"]))

    def test_invalid_tf_prefix_returns_error(self):
        result = execute({"tf_name": "SV_BILLING_DOC_JOINED"})
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("TF_" in e for e in result["errors"]))

    def test_invalid_tc_override_prefix_returns_error(self):
        result = execute({"tf_name": "TF_TEST", "tc_name": "BADNAME"})
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("TC_" in e for e in result["errors"]))

    def test_deploy_without_confirm_returns_error(self):
        result = execute({
            "tf_name": "TF_TEST",
            "deploy": True,
            "confirm": False,
            "acknowledge_ai": True,
        })
        self.assertEqual(result["status"], "error")

    def test_deploy_without_acknowledge_ai_returns_error(self):
        result = execute({
            "tf_name": "TF_TEST",
            "deploy": True,
            "confirm": True,
            "acknowledge_ai": False,
        })
        self.assertEqual(result["status"], "error")


if __name__ == "__main__":
    unittest.main()
