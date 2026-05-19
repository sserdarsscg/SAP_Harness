"""Compatibility wrapper for Skill 0 governance helpers.

The canonical implementation lives in agent.governance_guard and is applied
globally in the planner and MCP server before skill execution.
"""

from __future__ import annotations

from skills.governance_guard import governance_check


def _demo() -> None:
    """Small local runner for manual governance_check testing."""
    params = {
        "view_name": "wrong_name",
        "space_id": "ZZ_BDC_HARNESS_1",
    }
    result = governance_check("create_view", params)
    print(result)
if __name__ == "__main__":
    _demo()
