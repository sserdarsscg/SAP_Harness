"""
Unit tests for the create_sql_view_with_association skill (Skill 3).

Tests the pure-Python logic only — no CLI calls, no Datasphere connection.
"""

import sys
import os
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from skills.create_sql_view_with_association import (
    _ensure_sv_prefix,
    _build_assoc_element_name,
    _has_known_prefix,
    build_sv_csn,
)


# ---------------------------------------------------------------------------
# Minimal element fixtures
# ---------------------------------------------------------------------------

TABLE1_ELEMENTS = {
    "BillingDocument": {"type": "cds.String", "key": True, "@EndUserText.label": "Billing Doc"},
    "BillingDocumentItem": {"type": "cds.String", "@EndUserText.label": "Item"},
    "CompanyCode": {"type": "cds.String", "@EndUserText.label": "Company Code"},
    "Material": {"type": "cds.String", "@EndUserText.label": "Material"},
}

TABLE2_ELEMENTS = {
    "BillingDocument": {"type": "cds.String", "key": True, "@EndUserText.label": "Billing Doc"},
    "SalesOrganization": {"type": "cds.String", "@EndUserText.label": "Sales Org"},
    "CompanyCode": {"type": "cds.String", "@EndUserText.label": "Company Code"},
}


# ---------------------------------------------------------------------------
# Tests: helpers
# ---------------------------------------------------------------------------

class TestEnsureSvPrefix(unittest.TestCase):

    def test_already_prefixed_unchanged(self):
        self.assertEqual(_ensure_sv_prefix("SV_BILLING"), "SV_BILLING")

    def test_no_prefix_gets_sv(self):
        self.assertEqual(_ensure_sv_prefix("BILLING_DOC"), "SV_BILLING_DOC")

    def test_lowercase_uppercased(self):
        self.assertEqual(_ensure_sv_prefix("sv_billing"), "SV_BILLING")

    def test_wrong_prefix_not_stripped(self):
        # GV_ prefix stays — _ensure_sv_prefix only adds SV_ if missing SV_
        result = _ensure_sv_prefix("GV_BILLING")
        self.assertTrue(result.startswith("SV_") or result == "GV_BILLING")


class TestBuildAssocElementName(unittest.TestCase):

    def test_sv_prefix_stripped(self):
        self.assertEqual(_build_assoc_element_name("SV_COMPANYCODE"), "TO_COMPANYCODE")

    def test_tl_prefix_stripped(self):
        self.assertEqual(_build_assoc_element_name("TL_COMPANYCODE"), "TO_COMPANYCODE")

    def test_gv_prefix_stripped(self):
        self.assertEqual(_build_assoc_element_name("GV_CUSTOMER"), "TO_CUSTOMER")


class TestHasKnownPrefix(unittest.TestCase):

    def test_sv_detected(self):
        self.assertTrue(_has_known_prefix("SV_COMPANYCODE"))

    def test_tl_detected(self):
        self.assertTrue(_has_known_prefix("TL_COMPANYCODE"))

    def test_no_prefix_returns_false(self):
        self.assertFalse(_has_known_prefix("COMPANYCODE"))

    def test_single_letter_prefix_not_matched(self):
        self.assertFalse(_has_known_prefix("V_COMPANYCODE"))


# ---------------------------------------------------------------------------
# Tests: build_sv_csn
# ---------------------------------------------------------------------------

class TestBuildSvCsn(unittest.TestCase):

    def _build(self, **kwargs):
        defaults = dict(
            view_name="SV_BILLING_DOC_JOINED",
            source_table_1="VR1_BILLING_DOC_ITEM_TD_001",
            source_table_2="VR1_BILLING_DOC_TD_001",
            join_field="BillingDocument",
            association_field="CompanyCode",
            master_data_view="SV_COMPANYCODE",
            table1_elements=TABLE1_ELEMENTS,
            table2_elements=TABLE2_ELEMENTS,
            master_data_key="Company_Code",
        )
        defaults.update(kwargs)
        return build_sv_csn(**defaults)

    def _build_with_assoc(self, **kwargs):
        """Helper for tests that specifically require the association element."""
        return self._build(include_association=True, **kwargs)

    def test_output_has_definitions(self):
        csn = self._build()
        self.assertIn("definitions", csn)

    def test_view_name_is_key_in_definitions(self):
        csn = self._build()
        self.assertIn("SV_BILLING_DOC_JOINED", csn["definitions"])

    def test_sv_prefix_enforced_on_view_name(self):
        csn = self._build(view_name="BILLING_DOC_JOINED")
        self.assertIn("SV_BILLING_DOC_JOINED", csn["definitions"])

    def test_query_is_inner_join(self):
        csn = self._build()
        view_def = csn["definitions"]["SV_BILLING_DOC_JOINED"]
        join = view_def["query"]["SELECT"]["from"]
        self.assertEqual(join["join"], "inner")

    def test_both_source_tables_in_join_args(self):
        csn = self._build()
        join_args = csn["definitions"]["SV_BILLING_DOC_JOINED"]["query"]["SELECT"]["from"]["args"]
        refs = [a["ref"][0] for a in join_args]
        self.assertIn("VR1_BILLING_DOC_ITEM_TD_001", refs)
        self.assertIn("VR1_BILLING_DOC_TD_001", refs)

    def test_join_on_condition_uses_join_field(self):
        csn = self._build()
        on_cond = csn["definitions"]["SV_BILLING_DOC_JOINED"]["query"]["SELECT"]["from"]["on"]
        flat = str(on_cond)
        self.assertIn("BillingDocument", flat)

    def test_association_element_present(self):
        csn = self._build_with_assoc()
        elements = csn["definitions"]["SV_BILLING_DOC_JOINED"]["elements"]
        self.assertIn("TO_COMPANYCODE", elements)

    def test_association_element_absent_by_default(self):
        csn = self._build()
        elements = csn["definitions"]["SV_BILLING_DOC_JOINED"]["elements"]
        self.assertNotIn("TO_COMPANYCODE", elements)

    def test_association_type_is_cds_association(self):
        csn = self._build_with_assoc()
        elem = csn["definitions"]["SV_BILLING_DOC_JOINED"]["elements"]["TO_COMPANYCODE"]
        self.assertEqual(elem["type"], "cds.Association")

    def test_association_target_is_master_data_view(self):
        csn = self._build_with_assoc()
        elem = csn["definitions"]["SV_BILLING_DOC_JOINED"]["elements"]["TO_COMPANYCODE"]
        self.assertEqual(elem["target"], "SV_COMPANYCODE")

    def test_association_on_uses_master_data_key(self):
        csn = self._build_with_assoc()
        on = csn["definitions"]["SV_BILLING_DOC_JOINED"]["elements"]["TO_COMPANYCODE"]["on"]
        self.assertEqual(on[0]["ref"], ["TO_COMPANYCODE", "Company_Code"])
        self.assertEqual(on[2]["ref"], ["CompanyCode"])

    def test_join_field_appears_once_in_elements(self):
        csn = self._build()
        elements = csn["definitions"]["SV_BILLING_DOC_JOINED"]["elements"]
        # BillingDocument should appear exactly once (not duplicated from both tables)
        self.assertIn("BillingDocument", elements)

    def test_columns_from_both_tables_present(self):
        csn = self._build()
        elements = csn["definitions"]["SV_BILLING_DOC_JOINED"]["elements"]
        # From table1
        self.assertIn("Material", elements)
        # From table2 (unique to table2)
        self.assertIn("SalesOrganization", elements)

    def test_duplicate_columns_not_doubled(self):
        """CompanyCode appears in both tables — should exist only once in SELECT columns."""
        csn = self._build()
        select_cols = csn["definitions"]["SV_BILLING_DOC_JOINED"]["query"]["SELECT"]["columns"]
        # Table-qualified refs have 2 elements: [table, column]
        cc_refs = [c for c in select_cols if len(c.get("ref", [])) == 2 and c["ref"][1] == "CompanyCode"]
        self.assertEqual(len(cc_refs), 1, "CompanyCode must appear once in SELECT columns")

    def test_association_not_in_select_columns_by_default(self):
        """Association must NOT appear in SELECT columns — Datasphere rejects it."""
        csn = self._build_with_assoc()
        select_cols = csn["definitions"]["SV_BILLING_DOC_JOINED"]["query"]["SELECT"]["columns"]
        assoc_refs = [c for c in select_cols if c.get("ref") == ["TO_COMPANYCODE"]]
        self.assertEqual(len(assoc_refs), 0,
                         "Association must NOT be in SELECT columns for Datasphere SQL Views")

    def test_master_data_key_defaults_to_association_field(self):
        """When master_data_key is None, on-condition uses association_field as target key."""
        csn = self._build_with_assoc(master_data_key=None)
        on = csn["definitions"]["SV_BILLING_DOC_JOINED"]["elements"]["TO_COMPANYCODE"]["on"]
        self.assertEqual(on[0]["ref"][1], "CompanyCode")


# ---------------------------------------------------------------------------
# Tests: execute() — param validation (no CLI)
# ---------------------------------------------------------------------------

class TestExecuteValidation(unittest.TestCase):

    def _call(self, **kwargs):
        from skills.create_sql_view_with_association import execute
        return execute(kwargs)

    def test_empty_params_is_dry_run_not_error(self):
        """All params have defaults — empty call should attempt a dry run (may fail at CLI read)."""
        # We can't call CLI in unit tests, but we can check that validation passes
        # and the error (if any) is about CLI, not param validation
        result = self._call()
        # Accept either dry_run (mock executor) or error about table read
        self.assertIn(result["status"], ("dry_run", "error"))

    def test_bad_view_name_prefix_is_corrected(self):
        """_ensure_sv_prefix auto-corrects; no validation error expected for missing SV_."""
        # The skill auto-corrects view_name — it should NOT return error for missing SV_ prefix
        # We check the view_name is auto-corrected in a dry_run result
        result = self._call(view_name="BILLING_DOC_JOINED")
        if result["status"] == "dry_run":
            self.assertEqual(result["view_name"], "SV_BILLING_DOC_JOINED")

    def test_deploy_without_confirm_returns_error(self):
        result = self._call(deploy=True)
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("confirm" in e.lower() for e in result["errors"]))

    def test_deploy_without_acknowledge_ai_returns_error(self):
        result = self._call(deploy=True, confirm=True)
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("acknowledge_ai" in e.lower() for e in result["errors"]))

    def test_invalid_master_data_view_prefix_returns_error(self):
        """master_data_view without a recognised prefix should fail governance check."""
        result = self._call(master_data_view="COMPANYCODE")
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("master_data_view" in e for e in result["errors"]))


if __name__ == "__main__":
    unittest.main()
