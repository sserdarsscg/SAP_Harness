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

# Naming convention file lives at datasphere-agent root
NAMING_CONVENTION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "naming_convention.json",
)


def _load_naming_conventions() -> dict:
    """Load naming convention configuration from JSON file."""
    with open(NAMING_CONVENTION_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_view_prefix(view_type: str = "GV") -> str:
    """Read the configured view prefix from naming_convention.json based on view type.
    
    Args:
        view_type: "GV" for Graphical View (default), "SV" for SQL View
    
    Returns:
        The configured prefix (e.g., "GV_" or "SV_")
    """
    config = _load_naming_conventions()
    
    if view_type.upper() == "SV":
        prefix = config.get("naming_conventions", {}).get("sql_view", {}).get("prefix", "")
        if not prefix:
            raise ValueError("Missing naming_conventions.sql_view.prefix in naming_convention.json")
    else:
        # Default to GV (Graphical View)
        prefix = config.get("naming_conventions", {}).get("view", {}).get("prefix", "")
        if not prefix:
            raise ValueError("Missing naming_conventions.view.prefix in naming_convention.json")
    
    return prefix.upper()


def _ensure_prefix(view_name: str, view_type: str = "GV") -> str:
    """Ensure view name uses the configured view prefix.
    
    Args:
        view_name: Technical name (e.g., DOC_ITEM_VIEW)
        view_type: "GV" for Graphical View (default), "SV" for SQL View
    
    Returns:
        Prefixed name (e.g., GV_DOC_ITEM_VIEW or SV_DOC_ITEM_VIEW)
    """
    name = view_name.upper()
    prefix = _get_view_prefix(view_type)
    if name.startswith(prefix):
        return name
    return f"{prefix}{name}"


def generate_csn(
    view_name: str,
    columns: list[dict],
    business_name: str | None = None,
    view_type: str = "GV",
) -> dict:
    """
    Build a CSN JSON definition for a Datasphere view.

    Args:
        view_name:     Technical name (e.g. V_SALES_ITEMS)
        columns:       List of dicts with keys: name, type, key (optional)
                       type uses CDS types: cds.Integer, cds.String, cds.Decimal, etc.
        business_name: Human-readable label (defaults to view_name)
        view_type:     "GV" for Graphical View (default), "SV" for SQL View
    """
    if not business_name:
        business_name = view_name

    view_name = _ensure_prefix(view_name, view_type)

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
    Generates CSN for a view.
    """
    import re

    user_prompt = params.get("user_prompt", "")
    view_type = params.get("view_type", "GV").upper()

    # Try to extract view name from prompt
    view_name = "V_NEW_VIEW"
    match = re.search(r"(?:view|create)\s+(\w+)", user_prompt.lower())
    if match:
        view_name = match.group(1).upper()

    csn = generate_csn(view_name, DEFAULT_COLUMNS, view_type=view_type)
    csn_text = json.dumps(csn, indent=2)

    return {
        "status": "success",
        "view_name": view_name,
        "view_type": view_type,
        "csn": csn,
        "output": f"CSN definition generated for {view_type} {view_name}",
    }


# Self-register this skill with the registry
register_skill("create_view", execute)
