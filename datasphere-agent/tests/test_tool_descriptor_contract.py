"""
Contract tests for the bronze_to_silver MCP tool descriptor.

Validates that:
- The JSON descriptor has all required MCP fields
- The input schema properties are consistent with the Python skill
- A sample input derived from the schema can be passed to the skill
"""

import json
import os
import sys
import unittest

# Ensure the project root is on sys.path so imports work
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

TOOL_JSON_PATH = os.path.join(PROJECT_ROOT, "mcp_tools", "bronze_to_silver_tool.json")


class TestToolDescriptorContract(unittest.TestCase):
    """Verify the MCP tool descriptor is well-formed and matches the skill."""

    @classmethod
    def setUpClass(cls):
        with open(TOOL_JSON_PATH, encoding="utf-8") as f:
            cls.descriptor = json.load(f)

    # ------------------------------------------------------------------
    # 1. Required MCP fields
    # ------------------------------------------------------------------

    def test_required_fields_exist(self):
        """name, description, and inputSchema (or parameters) must be present."""
        d = self.descriptor

        self.assertIn("name", d, "Missing 'name' in tool descriptor")
        self.assertIsInstance(d["name"], str)
        self.assertTrue(len(d["name"]) > 0, "'name' must not be empty")

        self.assertIn("description", d, "Missing 'description' in tool descriptor")
        self.assertIsInstance(d["description"], str)
        self.assertTrue(len(d["description"]) > 0, "'description' must not be empty")

        # MCP uses 'inputSchema'; accept 'parameters' as an alias
        has_schema = "inputSchema" in d or "parameters" in d
        self.assertTrue(has_schema, "Missing 'inputSchema' or 'parameters'")

    def test_input_schema_is_valid_json_schema(self):
        """inputSchema must declare type=object and have a properties dict."""
        schema = self.descriptor.get("inputSchema", self.descriptor.get("parameters"))
        self.assertEqual(schema.get("type"), "object", "inputSchema.type must be 'object'")
        self.assertIn("properties", schema, "inputSchema must have 'properties'")
        self.assertIsInstance(schema["properties"], dict)

    def test_examples_format_if_present(self):
        """If 'examples' exists it must be a non-empty list of dicts."""
        examples = self.descriptor.get("examples")
        if examples is None:
            return  # optional field
        self.assertIsInstance(examples, list, "'examples' must be a list")
        self.assertTrue(len(examples) > 0, "'examples' must not be empty")
        for idx, ex in enumerate(examples):
            self.assertIsInstance(ex, dict, f"examples[{idx}] must be a dict")

    # ------------------------------------------------------------------
    # 2. Schema ↔ Skill parameter alignment
    # ------------------------------------------------------------------

    def test_schema_keys_match_skill_output(self):
        """
        Build a sample input from the schema defaults/types, call the skill,
        and verify the result dict contains expected keys.
        """
        schema = self.descriptor.get("inputSchema", self.descriptor.get("parameters"))
        properties = schema["properties"]

        # Build sample input using defaults or sensible type-based values
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

        # The skill expects 'user_prompt' — synthesise one from the schema values
        table = sample_input.get("table_name", "CUSTOMER")
        source = sample_input.get("source_layer", "bronze")
        target = sample_input.get("target_layer", "silver")
        skill_params = {
            "user_prompt": f"move {source} {table} table to {target}"
        }

        # Import skill (triggers self-registration)
        from skills.bronze_to_silver import execute  # noqa: E402

        result = execute(skill_params)

        # Verify skill returned a well-formed result
        self.assertIsInstance(result, dict, "Skill must return a dict")
        self.assertIn("status", result, "Skill result missing 'status'")
        self.assertIn("sql", result, "Skill result missing 'sql'")
        self.assertEqual(result["status"], "success")

        # The generated SQL must reference the table we provided
        self.assertIn(table.upper(), result["sql"],
                       f"Generated SQL does not reference table '{table}'")

    def test_required_schema_keys_are_declared(self):
        """Every key listed in 'required' must exist in 'properties'."""
        schema = self.descriptor.get("inputSchema", self.descriptor.get("parameters"))
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for key in required:
            self.assertIn(key, properties,
                          f"Required key '{key}' is not in properties")

    def test_no_extra_unknown_top_level_keys(self):
        """Warn if the descriptor has keys outside the known MCP set."""
        known_keys = {
            "name", "description", "inputSchema", "parameters",
            "annotations", "examples",
        }
        extra = set(self.descriptor.keys()) - known_keys
        self.assertEqual(extra, set(),
                         f"Unexpected top-level keys in descriptor: {extra}")


if __name__ == "__main__":
    unittest.main()
