"""Skill-level governance compatibility module.

This module exposes governance_check for callers that import from skills.
The canonical implementation still lives in agent.governance_guard.
"""

from __future__ import annotations

from agent.governance_guard import validate_skill_call, log_skill_action


def governance_check(skill_name: str, params: dict) -> dict:
    """Backward-compatible alias for the shared governance validator."""
    return validate_skill_call(skill_name, params)


def log_action(
    skill_name: str,
    params: dict,
    status: str,
    message: str,
) -> dict:
    """Backward-compatible alias for governance action logging."""
    validation = {
        "status": "legacy-wrapper",
        "allowed": status.upper() in {"SUCCESS", "OK"},
        "errors": [],
        "checks": {},
        "normalized_arguments": params,
    }
    return log_skill_action(
        skill_name=skill_name,
        params=params,
        validation=validation,
        output=message,
        result=status.lower(),
    )
