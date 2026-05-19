"""Skill: create_association

Adds an association inside an existing Graphical View (GV) so a transaction
view can navigate to a master data view.

Important: this skill does not create new objects. It extends an existing
view definition by adding one cds.Association element to its elements section.
"""

import json
import os
from agent.skill_registry import register_skill as _register_skill

NAMING_CONVENTION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "naming_convention.json",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_naming_conventions() -> dict:
    with open(NAMING_CONVENTION_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_assoc_prefix() -> str:
    config = _load_naming_conventions()
    prefix = (
        config.get("naming_conventions", {})
        .get("association", {})
        .get("prefix", "")
    )
    if not prefix:
        raise ValueError(
            "Missing naming_conventions.association.prefix in naming_convention.json"
        )
    return prefix.upper()


def _ensure_prefix(name: str) -> str:
    name = name.upper()
    prefix = _get_assoc_prefix()
    return name if name.startswith(prefix) else f"{prefix}{name}"


def _build_association_name(source_view: str, target_view: str) -> str:
    """Create a deterministic association element name."""
    source_stem = source_view.replace("GV_", "", 1)
    target_stem = target_view.replace("GV_", "", 1)
    return f"to_{target_stem}_by_{source_stem}".upper()


def register_skill(intent_name: str):
    """Decorator wrapper so this module can use @register_skill syntax."""

    def _decorator(func):
        _register_skill(intent_name, func)
        return func

    return _decorator


# ---------------------------------------------------------------------------
# Core CSN builder
# ---------------------------------------------------------------------------

def build_association_extension(
    existing_view_csn: dict,
    source_view: str,
    target_view: str,
    join_field_source: str,
    join_field_target: str,
) -> tuple[dict, str, list]:
    """Extend existing source view CSN with a cds.Association element.

    Returns:
        updated_csn, association_name, join_condition
    """
    normalized_source = _ensure_prefix(source_view)
    normalized_target = _ensure_prefix(target_view)

    definitions = existing_view_csn.setdefault("definitions", {})
    source_def = definitions.get(normalized_source)
    if not source_def:
        raise ValueError(
            f"Source view '{normalized_source}' not found in existing_view_csn.definitions"
        )

    elements = source_def.setdefault("elements", {})
    assoc_name = _build_association_name(normalized_source, normalized_target)
    join_condition = [
        {"ref": [assoc_name, join_field_target]},
        "=",
        {"ref": [join_field_source]},
    ]

    elements[assoc_name] = {
        "type": "cds.Association",
        "target": normalized_target,
        "on": join_condition,
        "@EndUserText.label": f"Association to {normalized_target}",
    }

    return existing_view_csn, assoc_name, join_condition


@register_skill("create_association")
def execute(params: dict) -> dict:
    """Entry point for association creation.

    Required params:
        source_view
        target_view
        join_field_source
        join_field_target

    Optional params:
        existing_view_csn  # full CSN definition that already contains source_view
    """
    required = [
        "source_view",
        "target_view",
        "join_field_source",
        "join_field_target",
    ]
    for key in required:
        if not params.get(key):
            return {"status": "error", "message": f"Missing required param: {key}"}

    existing_view_csn = params.get("existing_view_csn")
    if not isinstance(existing_view_csn, dict):
        return {
            "status": "error",
            "message": (
                "Missing required param: existing_view_csn (full source view CSN). "
                "This skill extends existing views only and does not create new objects."
            ),
        }

    try:
        updated_csn, association_name, join_condition = build_association_extension(
            existing_view_csn=existing_view_csn,
            source_view=params["source_view"],
            target_view=params["target_view"],
            join_field_source=params["join_field_source"],
            join_field_target=params["join_field_target"],
        )
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    return {
        "status": "success",
        "source_view": _ensure_prefix(params["source_view"]),
        "target_view": _ensure_prefix(params["target_view"]),
        "association_name": association_name,
        "join_condition": join_condition,
        "csn": updated_csn,
    }
