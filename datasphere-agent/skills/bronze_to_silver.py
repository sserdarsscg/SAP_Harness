"""
Skill: bronze_to_silver

Generates SQL to move/transform data from a bronze (raw/landing) layer
to a silver (cleansed/harmonized) layer in SAP Datasphere.

This is a simplified example – real transformations would be more complex.
"""

import re
from agent.skill_registry import register_skill


def _extract_table_name(prompt: str) -> str:
    """
    Try to extract a table name from the user prompt.
    Falls back to a default if nothing is found.
    """
    # Look for common patterns like "customer table", "orders table"
    match = re.search(r"(\w+)\s+table", prompt.lower())
    if match:
        return match.group(1).upper()
    return "UNKNOWN_TABLE"


# Layer prefix mapping per naming conventions
LAYER_PREFIXES = {
    "bronze": "10_BL",
    "silver": "20_SL",
    "gold_propagation": "30_GP",
    "gold_reporting": "40_GR",
}


def _resolve_layer(layer: str) -> str:
    """Map a layer alias to its naming convention prefix."""
    return LAYER_PREFIXES.get(layer.lower(), layer)


def generate_sql(
    table_name: str,
    source_layer: str = "bronze",
    target_layer: str = "silver",
) -> str:
    """
    Build an INSERT-SELECT SQL statement for a layer-to-layer transformation.
    Public function – used by both the CLI planner and the MCP server.
    """
    src = _resolve_layer(source_layer)
    tgt = _resolve_layer(target_layer)
    return (
        f"-- {source_layer.capitalize()} to {target_layer.capitalize()} transformation for {table_name}\n"
        f"INSERT INTO \"{tgt}\".\"{table_name}\" (\n"
        f"    id, name, updated_at\n"
        f")\n"
        f"SELECT\n"
        f"    id,\n"
        f"    TRIM(name)       AS name,        -- basic cleansing\n"
        f"    CURRENT_TIMESTAMP AS updated_at   -- silver timestamp\n"
        f"FROM \"{src}\".\"{table_name}\"\n"
        f"WHERE id IS NOT NULL;                 -- filter out incomplete rows"
    )


def _generate_sql(table_name: str) -> str:
    """Backward-compatible wrapper used by the existing execute() flow."""
    return generate_sql(table_name, source_layer="bronze", target_layer="silver")


def execute(params: dict) -> dict:
    """
    Skill entry point.
    1. Extract table name from user prompt
    2. Generate transformation SQL
    3. Return SQL for execution
    """
    user_prompt = params.get("user_prompt", "")
    table_name = _extract_table_name(user_prompt)
    sql = _generate_sql(table_name)

    return {
        "status": "success",
        "table": table_name,
        "sql": sql,
        "output": "SQL generated successfully",
    }


# Self-register this skill with the registry
register_skill("bronze_to_silver", execute)
