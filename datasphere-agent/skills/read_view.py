"""
Skill: read_view

Generates a SELECT SQL statement to read data from a deployed view
in SAP Datasphere. Supports specifying space, view name, column list,
and optional row limit.

Known deployed views (DE_IND_CONTENT_HDB space):
  - ADSO_Sales_Document_Item_Data_V  (ADSO Sales Document Item Data)
"""

from agent.skill_registry import register_skill


def generate_read_sql(
    view_name: str,
    space_id: str = "ZZ_BDC_HARNESS_1",
    columns: str = "*",
    limit: int | None = 100,
) -> str:
    """
    Build a SELECT SQL statement to read from a Datasphere view.
    Public function – used by both the CLI planner and the MCP server.
    """
    col_clause = columns if columns else "*"
    limit_clause = f"\nLIMIT {limit}" if limit else ""

    return (
        f"-- Read from view {view_name} in space {space_id}\n"
        f"SELECT {col_clause}\n"
        f"FROM \"{space_id}\".\"{view_name}\""
        f"{limit_clause};"
    )


def execute(params: dict) -> dict:
    """
    Skill entry point for CLI planner.
    Extracts view name from user prompt and generates SELECT SQL.
    """
    import re

    user_prompt = params.get("user_prompt", "")
    prompt_lower = user_prompt.lower()

    # Try to extract view name from prompt
    # Look for patterns like "view ADSO_Sales_Document_Item_Data_V"
    # or "sales document" (mapped to known view)
    view_name = "ADSO_Sales_Document_Item_Data_V"  # default known view

    match = re.search(r"view\s+(\w+)", prompt_lower)
    if match:
        view_name = match.group(1)

    # Check for known aliases
    if "sales" in prompt_lower and "document" in prompt_lower:
        view_name = "ADSO_Sales_Document_Item_Data_V"

    sql = generate_read_sql(view_name)

    return {
        "status": "success",
        "view": view_name,
        "sql": sql,
        "output": "SQL generated successfully",
    }


# Self-register this skill with the registry
register_skill("read_view", execute)
