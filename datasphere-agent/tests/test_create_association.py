"""
Unit tests for the create_association skill.

Tests the pure-Python logic only — no CLI calls, no Datasphere connection.
"""

import sys
import os
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from skills.create_association import _build_association_name, build_association_extension


# ---------------------------------------------------------------------------
# Minimal CSN fixture
# ---------------------------------------------------------------------------

def _make_csn(view_name: str, fields: list[str]) -> dict:
    """Build a minimal valid CSN dict with the given view and string fields."""
    return {
        "definitions": {
            view_name: {
                "kind": "entity",
                "elements": {f: {"type": "cds.String"} for f in fields},
            }
        }
    }


# ---------------------------------------------------------------------------
# Tests: _build_association_name
# ---------------------------------------------------------------------------

class TestBuildAssociationName(unittest.TestCase):

    def test_sv_prefix_stripped(self):
        self.assertEqual(_build_association_name("SV_COMPANYCODE"), "TO_COMPANYCODE")

    def test_gv_prefix_stripped(self):
        self.assertEqual(_build_association_name("GV_CUSTOMER"), "TO_CUSTOMER")

    def test_tl_prefix_stripped(self):
        self.assertEqual(_build_association_name("TL_COMPANYCODE"), "TO_COMPANYCODE")

    def test_lowercase_input_normalised(self):
        self.assertEqual(_build_association_name("sv_companycode"), "TO_COMPANYCODE")

    def test_no_prefix_returns_to_name(self):
        # Names without a known 2-letter prefix — TO_ prepended to full name
        self.assertEqual(_build_association_name("COMPANYCODE"), "TO_COMPANYCODE")


# ---------------------------------------------------------------------------
# Tests: build_association_extension
# ---------------------------------------------------------------------------

class TestBuildAssociationExtension(unittest.TestCase):

    def setUp(self):
        self.source_view = "SV_BILLING_DOC_JOINED"
        self.target_view = "SV_COMPANYCODE"
        self.csn = _make_csn(self.source_view, ["BillingDocument", "CompanyCode"])

    def test_association_element_added(self):
        updated, assoc_name, _ = build_association_extension(
            existing_view_csn=self.csn,
            source_view=self.source_view,
            target_view=self.target_view,
            join_field_source="CompanyCode",
            join_field_target="Company_Code",
        )
        elements = updated["definitions"][self.source_view]["elements"]
        self.assertIn(assoc_name, elements)

    def test_association_name_is_to_companycode(self):
        _, assoc_name, _ = build_association_extension(
            existing_view_csn=self.csn,
            source_view=self.source_view,
            target_view=self.target_view,
            join_field_source="CompanyCode",
            join_field_target="Company_Code",
        )
        self.assertEqual(assoc_name, "TO_COMPANYCODE")

    def test_association_type_is_cds_association(self):
        updated, assoc_name, _ = build_association_extension(
            existing_view_csn=self.csn,
            source_view=self.source_view,
            target_view=self.target_view,
            join_field_source="CompanyCode",
            join_field_target="Company_Code",
        )
        elem = updated["definitions"][self.source_view]["elements"][assoc_name]
        self.assertEqual(elem["type"], "cds.Association")

    def test_association_target_is_correct(self):
        updated, assoc_name, _ = build_association_extension(
            existing_view_csn=self.csn,
            source_view=self.source_view,
            target_view=self.target_view,
            join_field_source="CompanyCode",
            join_field_target="Company_Code",
        )
        elem = updated["definitions"][self.source_view]["elements"][assoc_name]
        self.assertEqual(elem["target"], self.target_view)

    def test_on_condition_references_correct_fields(self):
        _, assoc_name, join_condition = build_association_extension(
            existing_view_csn=self.csn,
            source_view=self.source_view,
            target_view=self.target_view,
            join_field_source="CompanyCode",
            join_field_target="Company_Code",
        )
        # join_condition: [{ref: [assoc_name, target_key]}, "=", {ref: [source_fk]}]
        self.assertEqual(join_condition[0]["ref"], [assoc_name, "Company_Code"])
        self.assertEqual(join_condition[1], "=")
        self.assertEqual(join_condition[2]["ref"], ["CompanyCode"])

    def test_cardinality_max_1(self):
        updated, assoc_name, _ = build_association_extension(
            existing_view_csn=self.csn,
            source_view=self.source_view,
            target_view=self.target_view,
            join_field_source="CompanyCode",
            join_field_target="Company_Code",
        )
        elem = updated["definitions"][self.source_view]["elements"][assoc_name]
        self.assertEqual(elem["cardinality"], {"max": 1})

    def test_original_elements_preserved(self):
        updated, _, _ = build_association_extension(
            existing_view_csn=self.csn,
            source_view=self.source_view,
            target_view=self.target_view,
            join_field_source="CompanyCode",
            join_field_target="Company_Code",
        )
        elements = updated["definitions"][self.source_view]["elements"]
        self.assertIn("BillingDocument", elements)
        self.assertIn("CompanyCode", elements)

    def test_missing_source_view_raises(self):
        csn = _make_csn("SV_OTHER_VIEW", ["ID"])
        with self.assertRaises(ValueError) as ctx:
            build_association_extension(
                existing_view_csn=csn,
                source_view="SV_BILLING_DOC_JOINED",
                target_view="SV_COMPANYCODE",
                join_field_source="CompanyCode",
                join_field_target="Company_Code",
            )
        self.assertIn("SV_BILLING_DOC_JOINED", str(ctx.exception))

    def test_csn_mutated_in_place(self):
        """build_association_extension mutates and returns the same dict object."""
        original = _make_csn(self.source_view, ["CompanyCode"])
        updated, assoc_name, _ = build_association_extension(
            existing_view_csn=original,
            source_view=self.source_view,
            target_view=self.target_view,
            join_field_source="CompanyCode",
            join_field_target="Company_Code",
        )
        self.assertIs(updated, original)
        self.assertIn(assoc_name, original["definitions"][self.source_view]["elements"])


# ---------------------------------------------------------------------------
# Tests: execute() — param validation (no CLI)
# ---------------------------------------------------------------------------

class TestExecuteValidation(unittest.TestCase):

    def _call(self, **kwargs):
        from skills.create_association import execute
        return execute(kwargs)

    def test_missing_source_view_returns_error(self):
        result = self._call(
            target_view="SV_COMPANYCODE",
            join_field_source="CompanyCode",
            join_field_target="Company_Code",
        )
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("source_view" in e for e in result["errors"]))

    def test_missing_target_view_returns_error(self):
        result = self._call(
            source_view="SV_BILLING_DOC_JOINED",
            join_field_source="CompanyCode",
            join_field_target="Company_Code",
        )
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("target_view" in e for e in result["errors"]))

    def test_deploy_without_confirm_returns_error(self):
        result = self._call(
            source_view="SV_BILLING_DOC_JOINED",
            target_view="SV_COMPANYCODE",
            join_field_source="CompanyCode",
            join_field_target="Company_Code",
            deploy=True,
            # confirm and acknowledge_ai deliberately omitted
        )
        self.assertEqual(result["status"], "error")
        errors_text = " ".join(result["errors"])
        self.assertIn("confirm", errors_text.lower())

    def test_deploy_without_acknowledge_ai_returns_error(self):
        result = self._call(
            source_view="SV_BILLING_DOC_JOINED",
            target_view="SV_COMPANYCODE",
            join_field_source="CompanyCode",
            join_field_target="Company_Code",
            deploy=True,
            confirm=True,
            # acknowledge_ai deliberately omitted
        )
        self.assertEqual(result["status"], "error")
        errors_text = " ".join(result["errors"])
        self.assertIn("acknowledge_ai", errors_text.lower())


if __name__ == "__main__":
    unittest.main()
