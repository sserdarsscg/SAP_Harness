"""
Unit tests for the create_association skill (four-step CSN protocol).

Tests the pure-Python logic only -- no CLI calls, no Datasphere connection.
"""

import sys
import os
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from skills.create_association import (
    _build_association_name,
    _build_on_condition,
    build_association_extension,
)


# ---------------------------------------------------------------------------
# Minimal CSN fixture
# ---------------------------------------------------------------------------

def _make_csn(view_name: str, fields: dict | None = None, with_select: bool = True) -> dict:
    """Build a minimal valid CSN dict."""
    if fields is None:
        fields = {
            "CompanyCode": {"@EndUserText.label": "Company code", "type": "cds.String", "length": 4, "key": True, "notNull": True},
            "FiscalYear": {"@EndUserText.label": "Fiscal year", "type": "cds.String", "length": 4},
        }
    defn = {
        "kind": "entity",
        "@EndUserText.label": "ZZ ASSOCIATION TEST",
        "elements": dict(fields),
    }
    if with_select:
        defn["query"] = {
            "SELECT": {
                "from": {"ref": ["SOME_SPACE.SOME_TABLE"]},
                "columns": [{"ref": [f]} for f in fields],
            }
        }
    return {"definitions": {view_name: defn}}


# ---------------------------------------------------------------------------
# Tests: _build_association_name
# ---------------------------------------------------------------------------

class TestBuildAssociationName(unittest.TestCase):

    def test_vi_companycode(self):
        self.assertEqual(_build_association_name("V_I_COMPANYCODE"), "_V_I_COMPA")

    def test_vi_fiscalyear_truncated(self):
        self.assertEqual(_build_association_name("V_I_FISCALYEARPERIODFORVARIANT"), "_V_I_FISCA")

    def test_result_max_10_chars(self):
        # Any input: result must be <= 10 chars
        name = _build_association_name("V_I_GLACCOUNTINCHARTOFACCOUNTS")
        self.assertLessEqual(len(name), 10)
        self.assertTrue(name.startswith("_"))

    def test_short_name_unchanged(self):
        self.assertEqual(_build_association_name("ABC"), "_ABC")

    def test_exactly_nine_chars_after_underscore(self):
        result = _build_association_name("ABCDEFGHIJKLMNOP")
        self.assertEqual(result, "_ABCDEFGHI")
        self.assertEqual(len(result), 10)


# ---------------------------------------------------------------------------
# Tests: _build_on_condition
# ---------------------------------------------------------------------------

class TestBuildOnCondition(unittest.TestCase):

    SINGLE = [{"source_field": "CompanyCode", "target_field": "CompanyCode"}]
    COMPOUND = [
        {"source_field": "FiscalYearVariant", "target_field": "FiscalYearVariant"},
        {"source_field": "FiscalYearPeriod",  "target_field": "FiscalYearPeriod"},
    ]

    def test_single_key_bare_refs(self):
        cond = _build_on_condition("_V_I_COMPA", self.SINGLE, use_projection=False)
        self.assertEqual(cond, [
            {"ref": ["CompanyCode"]},
            "=",
            {"ref": ["_V_I_COMPA", "CompanyCode"]},
        ])

    def test_single_key_projection_refs(self):
        cond = _build_on_condition("_V_I_COMPA", self.SINGLE, use_projection=True)
        self.assertEqual(cond, [
            {"ref": ["$projection", "CompanyCode"]},
            "=",
            {"ref": ["_V_I_COMPA", "CompanyCode"]},
        ])

    def test_compound_key_bare_refs(self):
        cond = _build_on_condition("_V_I_FISCA", self.COMPOUND, use_projection=False)
        self.assertEqual(cond, [
            {"ref": ["FiscalYearVariant"]},
            "=",
            {"ref": ["_V_I_FISCA", "FiscalYearVariant"]},
            "and",
            {"ref": ["FiscalYearPeriod"]},
            "=",
            {"ref": ["_V_I_FISCA", "FiscalYearPeriod"]},
        ])

    def test_compound_key_projection_refs(self):
        cond = _build_on_condition("_V_I_FISCA", self.COMPOUND, use_projection=True)
        self.assertEqual(cond[0], {"ref": ["$projection", "FiscalYearVariant"]})
        self.assertIn("and", cond)
        self.assertEqual(cond[4], {"ref": ["$projection", "FiscalYearPeriod"]})


# ---------------------------------------------------------------------------
# Tests: build_association_extension -- single-key
# ---------------------------------------------------------------------------

class TestBuildAssociationExtensionSingleKey(unittest.TestCase):

    SOURCE = "ZZ_ASSOCIATION_TEST"
    TARGET = "V_I_COMPANYCODE"
    JOIN   = [{"source_field": "CompanyCode", "target_field": "CompanyCode"}]

    def setUp(self):
        self.csn = _make_csn(self.SOURCE)

    def test_returns_same_dict(self):
        updated, _ = build_association_extension(
            self.csn, self.SOURCE, self.TARGET, self.JOIN,
            source_label="ZZ ASSOCIATION TEST", target_label="Company code",
        )
        self.assertIs(updated, self.csn)

    def test_association_name_derived_correctly(self):
        _, assoc_name = build_association_extension(
            self.csn, self.SOURCE, self.TARGET, self.JOIN,
        )
        self.assertEqual(assoc_name, "_V_I_COMPA")

    # Step 1: FK annotation
    def test_step1_fk_annotation_added(self):
        build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        elem = self.csn["definitions"][self.SOURCE]["elements"]["CompanyCode"]
        self.assertIn("@ObjectModel.foreignKey.association", elem)
        self.assertEqual(elem["@ObjectModel.foreignKey.association"], {"=": "_V_I_COMPA"})

    # Step 2: Association element in elements
    def test_step2_assoc_element_added_to_elements(self):
        build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        elements = self.csn["definitions"][self.SOURCE]["elements"]
        self.assertIn("_V_I_COMPA", elements)

    def test_step2_assoc_element_type(self):
        build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        elem = self.csn["definitions"][self.SOURCE]["elements"]["_V_I_COMPA"]
        self.assertEqual(elem["type"], "cds.Association")

    def test_step2_assoc_element_target(self):
        build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        elem = self.csn["definitions"][self.SOURCE]["elements"]["_V_I_COMPA"]
        self.assertEqual(elem["target"], self.TARGET)

    def test_step2_assoc_element_on_uses_bare_refs(self):
        build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        on_cond = self.csn["definitions"][self.SOURCE]["elements"]["_V_I_COMPA"]["on"]
        # Source ref must NOT start with $projection
        self.assertEqual(on_cond[0]["ref"], ["CompanyCode"])
        self.assertEqual(on_cond[2]["ref"], ["_V_I_COMPA", "CompanyCode"])

    def test_step2_assoc_label_format(self):
        build_association_extension(
            self.csn, self.SOURCE, self.TARGET, self.JOIN,
            source_label="ZZ ASSOCIATION TEST", target_label="Company code",
        )
        elem = self.csn["definitions"][self.SOURCE]["elements"]["_V_I_COMPA"]
        self.assertEqual(elem["@EndUserText.label"], "ZZ ASSOCIATION TEST to Company code")

    # Step 3: column appended
    def test_step3_assoc_ref_in_columns(self):
        build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        columns = self.csn["definitions"][self.SOURCE]["query"]["SELECT"]["columns"]
        self.assertIn({"ref": ["_V_I_COMPA"]}, columns)

    def test_step3_regular_columns_still_present(self):
        build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        columns = self.csn["definitions"][self.SOURCE]["query"]["SELECT"]["columns"]
        self.assertIn({"ref": ["CompanyCode"]}, columns)

    def test_step3_assoc_ref_not_duplicated(self):
        build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        columns = self.csn["definitions"][self.SOURCE]["query"]["SELECT"]["columns"]
        assoc_refs = [c for c in columns if c == {"ref": ["_V_I_COMPA"]}]
        self.assertEqual(len(assoc_refs), 1)

    # Step 4: mixin entry
    def test_step4_mixin_exists(self):
        build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        select = self.csn["definitions"][self.SOURCE]["query"]["SELECT"]
        self.assertIn("mixin", select)

    def test_step4_mixin_contains_assoc(self):
        build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        mixin = self.csn["definitions"][self.SOURCE]["query"]["SELECT"]["mixin"]
        self.assertIn("_V_I_COMPA", mixin)

    def test_step4_mixin_uses_projection_ref(self):
        build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        mixin_on = self.csn["definitions"][self.SOURCE]["query"]["SELECT"]["mixin"]["_V_I_COMPA"]["on"]
        self.assertEqual(mixin_on[0]["ref"], ["$projection", "CompanyCode"])
        self.assertEqual(mixin_on[2]["ref"], ["_V_I_COMPA", "CompanyCode"])

    def test_step4_mixin_target(self):
        build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        mixin_entry = self.csn["definitions"][self.SOURCE]["query"]["SELECT"]["mixin"]["_V_I_COMPA"]
        self.assertEqual(mixin_entry["target"], self.TARGET)

    # Original elements preserved
    def test_original_elements_preserved(self):
        build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        elements = self.csn["definitions"][self.SOURCE]["elements"]
        self.assertIn("CompanyCode", elements)
        self.assertIn("FiscalYear", elements)

    # Error: missing source view
    def test_missing_source_view_raises(self):
        csn = _make_csn("OTHER_VIEW")
        with self.assertRaises(ValueError) as ctx:
            build_association_extension(csn, "ZZ_ASSOCIATION_TEST", self.TARGET, self.JOIN)
        self.assertIn("ZZ_ASSOCIATION_TEST", str(ctx.exception))

    # Error: empty join_fields
    def test_empty_join_fields_raises(self):
        with self.assertRaises(ValueError):
            build_association_extension(self.csn, self.SOURCE, self.TARGET, [])


# ---------------------------------------------------------------------------
# Tests: build_association_extension -- compound-key
# ---------------------------------------------------------------------------

class TestBuildAssociationExtensionCompoundKey(unittest.TestCase):

    SOURCE = "ZZ_ASSOCIATION_TEST"
    TARGET = "V_I_FISCALYEARPERIODFORVARIANT"
    JOIN   = [
        {"source_field": "FiscalYearVariant", "target_field": "FiscalYearVariant"},
        {"source_field": "FiscalYearPeriod",  "target_field": "FiscalYearPeriod"},
    ]

    def setUp(self):
        fields = {
            "FiscalYearVariant": {"@EndUserText.label": "Fiscal year variant", "type": "cds.String", "length": 2},
            "FiscalYearPeriod":  {"@EndUserText.label": "Fiscal year period",  "type": "cds.String", "length": 7},
        }
        self.csn = _make_csn(self.SOURCE, fields)

    def test_assoc_name_derived(self):
        _, assoc_name = build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        self.assertEqual(assoc_name, "_V_I_FISCA")

    def test_step1_annotation_on_first_key_only(self):
        build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        elements = self.csn["definitions"][self.SOURCE]["elements"]
        self.assertIn("@ObjectModel.foreignKey.association", elements["FiscalYearVariant"])
        self.assertNotIn("@ObjectModel.foreignKey.association", elements["FiscalYearPeriod"])

    def test_step2_bare_on_has_and(self):
        build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        on_cond = self.csn["definitions"][self.SOURCE]["elements"]["_V_I_FISCA"]["on"]
        self.assertIn("and", on_cond)

    def test_step4_mixin_on_has_projection_and(self):
        build_association_extension(self.csn, self.SOURCE, self.TARGET, self.JOIN)
        mixin_on = self.csn["definitions"][self.SOURCE]["query"]["SELECT"]["mixin"]["_V_I_FISCA"]["on"]
        # Both source refs use $projection
        self.assertEqual(mixin_on[0]["ref"][0], "$projection")
        self.assertEqual(mixin_on[4]["ref"][0], "$projection")
        self.assertIn("and", mixin_on)


# ---------------------------------------------------------------------------
# Tests: execute() -- param validation (no CLI)
# ---------------------------------------------------------------------------

class TestExecuteValidation(unittest.TestCase):

    def _call(self, **kwargs):
        from skills.create_association import execute
        return execute(kwargs)

    def test_missing_source_view_returns_error(self):
        result = self._call(
            target_view="V_I_COMPANYCODE",
            join_field_source="CompanyCode",
            join_field_target="CompanyCode",
        )
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("source_view" in e for e in result["errors"]))

    def test_missing_target_view_returns_error(self):
        result = self._call(
            source_view="SV_BILLING_DOC_JOINED",
            join_field_source="CompanyCode",
            join_field_target="CompanyCode",
        )
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("target_view" in e for e in result["errors"]))

    def test_missing_join_fields_returns_error(self):
        result = self._call(
            source_view="SV_BILLING_DOC_JOINED",
            target_view="V_I_COMPANYCODE",
        )
        self.assertEqual(result["status"], "error")
        self.assertTrue(any("join_fields" in e for e in result["errors"]))

    def test_deploy_without_confirm_returns_error(self):
        result = self._call(
            source_view="SV_BILLING_DOC_JOINED",
            target_view="V_I_COMPANYCODE",
            join_field_source="CompanyCode",
            join_field_target="CompanyCode",
            deploy=True,
        )
        self.assertEqual(result["status"], "error")
        errors_text = " ".join(result["errors"])
        self.assertIn("confirm", errors_text.lower())

    def test_deploy_without_acknowledge_ai_returns_error(self):
        result = self._call(
            source_view="SV_BILLING_DOC_JOINED",
            target_view="V_I_COMPANYCODE",
            join_field_source="CompanyCode",
            join_field_target="CompanyCode",
            deploy=True,
            confirm=True,
        )
        self.assertEqual(result["status"], "error")
        errors_text = " ".join(result["errors"])
        self.assertIn("acknowledge_ai", errors_text.lower())

    def test_join_fields_list_accepted(self):
        # Providing join_fields as a list should be accepted (no error from validation alone)
        result = self._call(
            source_view="SV_BILLING_DOC_JOINED",
            target_view="V_I_COMPANYCODE",
            join_fields=[{"source_field": "CompanyCode", "target_field": "CompanyCode"}],
        )
        # Will fail at CLI fetch stage (not "error" about params), not a param-validation error
        self.assertNotIn("join_fields", " ".join(result.get("errors", [])))


if __name__ == "__main__":
    unittest.main()
