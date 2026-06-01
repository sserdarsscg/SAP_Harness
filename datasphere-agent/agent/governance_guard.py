"""Skill 0: Governance and AI literacy guard for all skill execution.

This module provides a reusable pre-execution validation layer and audit logging
that can be applied by planners, MCP handlers, and future execution paths.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any


log = logging.getLogger("governance-guard")

SPACE_BRONZE = "ZZ_BDC_HARNESS_1"
SPACE_CONSUMPTION = "ZZ_BDC_HARNESS_2"

MUTATING_SKILLS = {
    "create_view",
    "share_to_space",
    "create_association",
    "create_backup",
    "create_sql_view_with_association",
}

# Space rules can be extended for future skills without changing call sites.
SKILL_SPACE_RULES = {
    "create_view": {"space_id": {SPACE_BRONZE}},
    "create_association": {"space_id": {SPACE_BRONZE}},
    "create_backup": {"space_id": {SPACE_BRONZE}},
    "create_sql_view_with_association": {"space_id": {SPACE_BRONZE}},
    "share_to_space": {
        "source_space": {SPACE_BRONZE},
        "target_spaces": {SPACE_CONSUMPTION},
    },
}

_JOIN_PATTERN = re.compile(r"\bjoin\b", flags=re.IGNORECASE)
_AUDIT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "logs",
    "governance_audit.jsonl",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bool(value: Any) -> bool:
    return value is True


def _contains_join(value: Any) -> bool:
    return isinstance(value, str) and bool(_JOIN_PATTERN.search(value))


def _looks_mutating(skill_name: str) -> bool:
    if skill_name in MUTATING_SKILLS:
        return True
    lower = skill_name.lower()
    return lower.startswith(("create_", "update_", "delete_", "share_", "deploy_"))


def _validate_space_rules(skill_name: str, params: dict[str, Any], errors: list[str]) -> None:
    rule = SKILL_SPACE_RULES.get(skill_name)
    if not rule:
        return

    allowed_space = rule.get("space_id")
    if allowed_space is not None:
        value = params.get("space_id", SPACE_BRONZE)
        if value not in allowed_space:
            errors.append(
                f"Invalid space_id '{value}'. Allowed: {sorted(allowed_space)}"
            )

    allowed_source = rule.get("source_space")
    if allowed_source is not None:
        value = params.get("source_space", SPACE_BRONZE)
        if value not in allowed_source:
            errors.append(
                f"Invalid source_space '{value}'. Allowed: {sorted(allowed_source)}"
            )

    allowed_targets = rule.get("target_spaces")
    if allowed_targets is not None:
        targets = params.get("target_spaces", [])
        if not isinstance(targets, list) or not targets:
            errors.append("target_spaces must be a non-empty list.")
            return
        invalid = [space_id for space_id in targets if space_id not in allowed_targets]
        if invalid:
            errors.append(
                f"Invalid target_spaces {invalid}. Allowed: {sorted(allowed_targets)}"
            )


def _validate_sql_only(skill_name: str, params: dict[str, Any], errors: list[str]) -> None:
    if skill_name != "create_view":
        return

    view_type = str(params.get("view_type", "SV")).upper()
    if view_type != "SV":
        errors.append("Only SQL views are allowed. Set view_type='SV'.")

    view_name = str(params.get("view_name", "")).upper()
    if view_name and not view_name.startswith("SV_"):
        errors.append("Naming rule violation: SQL view names must start with 'SV_'.")


def _validate_no_join(params: dict[str, Any], errors: list[str]) -> None:
    candidate_keys = ("sql", "query", "statement", "user_prompt")
    for key in candidate_keys:
        if _contains_join(params.get(key)):
            errors.append(
                f"Architectural constraint violation: JOIN is not allowed in '{key}'."
            )


def validate_skill_call(skill_name: str, params: Any) -> dict[str, Any]:
    """Validate input and governance constraints before skill execution.

    Returns a structured validation result to enable transparent user feedback.
    """
    result: dict[str, Any] = {
        "skill_name": skill_name,
        "timestamp": _utc_now(),
        "status": "failure",
        "allowed": False,
        "requires_confirmation": _looks_mutating(skill_name),
        "errors": [],
        "checks": {
            "input_type": False,
            "space_rules": False,
            "sql_only": False,
            "no_join": False,
            "human_confirmation": False,
            "ai_literacy_ack": False,
        },
        "normalized_arguments": {},
    }

    if not isinstance(params, dict):
        result["errors"].append("Invalid input: arguments must be a JSON object.")
        return result

    normalized = dict(params)
    errors: list[str] = []
    result["checks"]["input_type"] = True

    _validate_space_rules(skill_name, normalized, errors)
    result["checks"]["space_rules"] = not any(
        err.startswith("Invalid space") or "source_space" in err or "target_spaces" in err
        for err in errors
    )

    _validate_sql_only(skill_name, normalized, errors)
    result["checks"]["sql_only"] = not any("SQL view" in err or "Naming rule" in err for err in errors)

    _validate_no_join(normalized, errors)
    result["checks"]["no_join"] = not any("JOIN" in err for err in errors)

    if _looks_mutating(skill_name):
        if not _bool(normalized.get("confirm")):
            errors.append("Human confirmation required: set confirm=true.")
        else:
            result["checks"]["human_confirmation"] = True

        if not _bool(normalized.get("acknowledge_ai")):
            errors.append(
                "AI literacy acknowledgement required: set acknowledge_ai=true to confirm you reviewed AI-generated output before execution."
            )
        else:
            result["checks"]["ai_literacy_ack"] = True
    else:
        result["checks"]["human_confirmation"] = True
        result["checks"]["ai_literacy_ack"] = True

    result["errors"] = errors
    result["normalized_arguments"] = normalized
    if not errors:
        result["status"] = "success"
        result["allowed"] = True

    return result


def log_skill_action(
    skill_name: str,
    params: Any,
    validation: dict[str, Any],
    output: str,
    result: str,
) -> dict[str, Any]:
    """Create and persist an auditable governance log event."""
    entry = {
        "timestamp": _utc_now(),
        "skill_name": skill_name,
        "input": params,
        "validation": validation,
        "output": output,
        "result": result,
    }

    os.makedirs(os.path.dirname(_AUDIT_PATH), exist_ok=True)
    with open(_AUDIT_PATH, "a", encoding="utf-8") as file_handle:
        file_handle.write(json.dumps(entry, ensure_ascii=True) + "\n")

    log.info("governance result=%s skill=%s", result, skill_name)
    return entry