"""
Contract tests for MCP tool descriptors.

Validates that each tool JSON file:
- Has all required MCP fields (name, description, inputSchema)
- inputSchema declares type=object and has a properties dict
- All 'required' keys exist in 'properties'
- No unknown top-level keys
- Annotations block (if present) is a dict

Covered tool files:
  - mcp_tools/bronze_to_silver_tool.json
  - mcp_tools/create_association_tool.json
  - mcp_tools/create_sql_view_with_association_tool.json
"""

import json
import os
import sys
import unittest

# Ensure the project root is on sys.path so imports work
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

MCP_TOOLS_DIR = os.path.join(PROJECT_ROOT, "mcp_tools")

# Legacy constant kept for backward compatibility
TOOL_JSON_PATH = os.path.join(MCP_TOOLS_DIR, "bronze_to_silver_tool.json")

KNOWN_MCP_KEYS = {
    "name", "description", "inputSchema", "parameters",
    "annotations", "examples",
}


# ---------------------------------------------------------------------------
# Generic contract mixin — applied to every tool descriptor
# ---------------------------------------------------------------------------

class ToolDescriptorContractMixin:
    """Reusable contract assertions. Subclasses set cls.descriptor and cls.tool_path."""

    descriptor: dict
    tool_path: str

    def test_required_fields_exist(self):
        """name, description, and inputSchema (or parameters) must be present."""
        d = self.descriptor
        self.assertIn("name", d, f"[{self.tool_path}] Missing 'name'")
        self.assertIsInstance(d["name"], str)
        self.assertTrue(len(d["name"]) > 0, f"[{self.tool_path}] 'name' must not be empty")

        self.assertIn("description", d, f"[{self.tool_path}] Missing 'description'")
        self.assertIsInstance(d["description"], str)
        self.assertTrue(len(d["description"]) > 0, f"[{self.tool_path}] 'description' must not be empty")

        has_schema = "inputSchema" in d or "parameters" in d
        self.assertTrue(has_schema, f"[{self.tool_path}] Missing 'inputSchema' or 'parameters'")

    def test_input_schema_is_valid_json_schema(self):
        """inputSchema must declare type=object and have a properties dict."""
        schema = self.descriptor.get("inputSchema", self.descriptor.get("parameters"))
        self.assertEqual(schema.get("type"), "object",
                         f"[{self.tool_path}] inputSchema.type must be 'object'")
        self.assertIn("properties", schema,
                      f"[{self.tool_path}] inputSchema must have 'properties'")
        self.assertIsInstance(schema["properties"], dict)

    def test_required_schema_keys_are_declared(self):
        """Every key listed in 'required' must exist in 'properties'."""
        schema = self.descriptor.get("inputSchema", self.descriptor.get("parameters"))
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        for key in required:
            self.assertIn(key, properties,
                          f"[{self.tool_path}] Required key '{key}' not in properties")

    def test_no_extra_unknown_top_level_keys(self):
        """No keys outside the known MCP set."""
        extra = set(self.descriptor.keys()) - KNOWN_MCP_KEYS
        self.assertEqual(extra, set(),
                         f"[{self.tool_path}] Unexpected top-level keys: {extra}")

    def test_annotations_is_dict_if_present(self):
        """annotations block must be a dict when present."""
        annotations = self.descriptor.get("annotations")
        if annotations is not None:
            self.assertIsInstance(annotations, dict,
                                  f"[{self.tool_path}] 'annotations' must be a dict")

    def test_examples_format_if_present(self):
        """If 'examples' exists it must be a non-empty list of dicts."""
        examples = self.descriptor.get("examples")
        if examples is None:
            return
        self.assertIsInstance(examples, list,
                              f"[{self.tool_path}] 'examples' must be a list")
        self.assertTrue(len(examples) > 0,
                        f"[{self.tool_path}] 'examples' must not be empty")
        for idx, ex in enumerate(examples):
            self.assertIsInstance(ex, dict,
                                  f"[{self.tool_path}] examples[{idx}] must be a dict")


# ---------------------------------------------------------------------------
# Tool-specific test classes
# ---------------------------------------------------------------------------

class TestBronzeToSilverDescriptor(ToolDescriptorContractMixin, unittest.TestCase):
    """Contract checks for bronze_to_silver_tool.json + skill integration test."""

    tool_path = "mcp_tools/bronze_to_silver_tool.json"

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(MCP_TOOLS_DIR, "bronze_to_silver_tool.json"), encoding="utf-8") as f:
            cls.descriptor = json.load(f)

    def test_schema_keys_match_skill_output(self):
        """Build a sample input and verify the skill returns expected keys."""
        schema = self.descriptor.get("inputSchema", self.descriptor.get("parameters"))
        properties = schema["properties"]

        sample_input = {}
        for key, prop in properties.items():
            if "default" in prop:
                sample_input[key] = prop["default"]
            elif prop.get("type") == "string":
                sample_input[key] = "CUSTOMER"
            elif prop.get("type") == "integer":
                sample_input[key] = 1
            elif prop.get("type") == "boolean":
                sample_input[key] = True

        table = sample_input.get("table_name", "CUSTOMER")
        source = sample_input.get("source_layer", "bronze")
        target = sample_input.get("target_layer", "silver")

        from skills.bronze_to_silver import execute
        result = execute({"user_prompt": f"move {source} {table} table to {target}"})

        self.assertIsInstance(result, dict)
        self.assertIn("status", result)
        self.assertIn("sql", result)
        self.assertEqual(result["status"], "success")
        self.assertIn(table.upper(), result["sql"])


class TestCreateAssociationDescriptor(ToolDescriptorContractMixin, unittest.TestCase):
    """Contract checks for create_association_tool.json."""

    tool_path = "mcp_tools/create_association_tool.json"

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(MCP_TOOLS_DIR, "create_association_tool.json"), encoding="utf-8") as f:
            cls.descriptor = json.load(f)

    def test_name_matches_skill(self):
        self.assertEqual(self.descriptor["name"], "create_association")

    def test_required_params_are_correct(self):
        required = self.descriptor["inputSchema"]["required"]
        self.assertIn("source_view", required)
        self.assertIn("target_view", required)
        self.assertIn("join_field_source", required)
        self.assertIn("join_field_target", required)

    def test_deploy_defaults_to_false(self):
        props = self.descriptor["inputSchema"]["properties"]
        self.assertFalse(props["deploy"]["default"])


class TestCreateSqlViewWithAssociationDescriptor(ToolDescriptorContractMixin, unittest.TestCase):
    """Contract checks for create_sql_view_with_association_tool.json."""

    tool_path = "mcp_tools/create_sql_view_with_association_tool.json"

    @classmethod
    def setUpClass(cls):
        with open(
            os.path.join(MCP_TOOLS_DIR, "create_sql_view_with_association_tool.json"),
            encoding="utf-8",
        ) as f:
            cls.descriptor = json.load(f)

    def test_name_matches_skill(self):
        self.assertEqual(self.descriptor["name"], "create_sql_view_with_association")

    def test_required_is_empty_list(self):
        """All params have defaults — required must be empty."""
        required = self.descriptor["inputSchema"].get("required", [])
        self.assertEqual(required, [])

    def test_default_view_name_is_sv_billing_doc_joined(self):
        props = self.descriptor["inputSchema"]["properties"]
        self.assertEqual(props["view_name"]["default"], "SV_BILLING_DOC_JOINED")

    def test_master_data_view_default_is_sv_companycode(self):
        props = self.descriptor["inputSchema"]["properties"]
        self.assertEqual(props["master_data_view"]["default"], "SV_COMPANYCODE")

    def test_master_data_key_default_is_company_code(self):
        props = self.descriptor["inputSchema"]["properties"]
        self.assertEqual(props["master_data_key"]["default"], "Company_Code")

    def test_deploy_defaults_to_false(self):
        props = self.descriptor["inputSchema"]["properties"]
        self.assertFalse(props["deploy"]["default"])


if __name__ == "__main__":
    unittest.main()
