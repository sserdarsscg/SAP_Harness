"""
Skill: create_view

Generates a CSN (Core Schema Notation) JSON definition for a view
in SAP Datasphere and optionally creates it via the CLI.

CSN format required by Datasphere API:
{
  "definitions": {
    "<VIEW_NAME>": {
      "kind": "entity",
      "@EndUserText.label": "<business name>",
      "query": {
        "SELECT": {
          "from": { "ref": ["<VIEW_NAME>"] },
          "columns": [ { "ref": ["<col>"] }, ... ]
        }
      },
      "elements": {
        "<col>": { "type": "cds.<Type>", ... },
        ...
      }
    }
  }
}
"""

import json
import os
import tempfile
from agent.skill_registry import register_skill
from executors.mock_datasphere_cli import execute_sql

# Valid view prefixes per naming convention
VALID_VIEW_PREFIXES = ("GV_", "SV_", "AM_", "ER_")


def _ensure_prefix(view_name: str) -> str:
    """Ensure view name has a valid prefix. Default to GV_ if missing."""
    name = view_name.upper()
    if any(name.startswith(p) for p in VALID_VIEW_PREFIXES):
        return name
    return f"GV_{name}"


def generate_csn(
    view_name: str,
    columns: list[dict],
    business_name: str | None = None,
) -> dict:
    """
    Build a CSN JSON definition for a Datasphere view.

    Args:
        view_name:     Technical name (e.g. V_SALES_ITEMS)
        columns:       List of dicts with keys: name, type, key (optional)
                       type uses CDS types: cds.Integer, cds.String, cds.Decimal, etc.
        business_name: Human-readable label (defaults to view_name)
    """
    if not business_name:
        business_name = view_name

    view_name = _ensure_prefix(view_name)

    # Build elements dict
    elements = {}
    select_columns = []
    for col in columns:
        col_name = col["name"]
        col_def: dict = {"type": col.get("type", "cds.String")}
        if col.get("key"):
            col_def["key"] = True
        if col.get("length"):
            col_def["length"] = col["length"]
        col_def["@EndUserText.label"] = col.get("label", col_name)
        elements[col_name] = col_def
        select_columns.append({"ref": [col_name]})

    csn = {
        "definitions": {
            view_name: {
                "kind": "entity",
                "@EndUserText.label": business_name,
                "query": {
                    "SELECT": {
                        "from": {"ref": [view_name]},
                        "columns": select_columns,
                    }
                },
                "elements": elements,
            }
        }
    }
    return csn


def csn_to_temp_file(csn: dict) -> str:
    """Write CSN JSON to a temporary file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".json", prefix="csn_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(csn, f, indent=2)
    return path


# Default column templates for quick view creation
DEFAULT_COLUMNS = [
    {"name": "ID", "type": "cds.Integer", "key": True, "label": "ID"},
    {"name": "NAME", "type": "cds.String", "length": 100, "label": "Name"},
    {"name": "AMOUNT", "type": "cds.Decimal", "label": "Amount"},
    {"name": "CREATED_AT", "type": "cds.Timestamp", "label": "Created At"},
]


def execute(params: dict) -> dict:
    """
    Skill entry point for CLI planner.
    Generates CSN and shows the dry-run output.
    """
    import re

    user_prompt = params.get("user_prompt", "")

    # Try to extract view name from prompt
    view_name = "V_NEW_VIEW"
    match = re.search(r"(?:view|create)\s+(\w+)", user_prompt.lower())
    if match:
        view_name = match.group(1).upper()

    csn = generate_csn(view_name, DEFAULT_COLUMNS)
    csn_text = json.dumps(csn, indent=2)

    output = execute_sql(f"-- CSN definition for {view_name}:\n{csn_text}")

    return {
        "status": "success",
        "view_name": view_name,
        "csn": csn,
        "output": output,
    }


# Self-register this skill with the registry
register_skill("create_view", execute)
