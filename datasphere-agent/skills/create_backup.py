"""Skill: create_backup

Creates a simple logical backup name for an existing Datasphere object before a
later modification step. When an original CSN is provided, the skill also
produces a copied CSN definition under the backup name without modifying the
original definition.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime

from agent.skill_registry import register_skill


NAMING_CONVENTION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "naming_convention.json",
)


def _load_naming_conventions() -> dict:
    """Load naming convention configuration from JSON file."""
    with open(NAMING_CONVENTION_PATH, "r", encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _get_backup_config() -> dict:
    """Return backup naming configuration."""
    config = _load_naming_conventions()
    backup_config = config.get("naming_conventions", {}).get("backup", {})
    if not backup_config:
        raise ValueError("Missing naming_conventions.backup in naming_convention.json")
    return backup_config


def _get_view_prefix() -> str:
    """Return the configured view prefix for view backups."""
    config = _load_naming_conventions()
    prefix = config.get("naming_conventions", {}).get("view", {}).get("prefix", "")
    if not prefix:
        raise ValueError("Missing naming_conventions.view.prefix in naming_convention.json")
    return prefix.upper()


def normalize_object_name(object_name: str) -> str:
    """Normalize an object name using the configured view prefix when needed."""
    name = object_name.upper()
    prefix = _get_view_prefix()
    if name.startswith(prefix):
        return name
    return f"{prefix}{name}"


def generate_backup_name(object_name: str, timestamp: datetime | None = None) -> str:
    """Generate a readable backup name using naming_convention.json settings."""
    backup_config = _get_backup_config()
    separator = backup_config.get("separator", "_")
    timestamp_format = backup_config.get("timestamp_format", "%Y%m%d_%H%M")
    effective_timestamp = timestamp or datetime.now()
    normalized_name = normalize_object_name(object_name)
    return f"{normalized_name}{separator}{effective_timestamp.strftime(timestamp_format)}"


def generate_backup_csn(object_name: str, original_csn: dict, backup_name: str) -> dict:
    """Clone an existing CSN definition under a new backup object name."""
    normalized_name = normalize_object_name(object_name)
    copied_csn = copy.deepcopy(original_csn)
    definitions = copied_csn.get("definitions", {})
    original_definition = definitions.get(normalized_name)

    if not original_definition:
        raise ValueError(
            f"Object '{normalized_name}' not found in original_csn.definitions"
        )

    definitions[backup_name] = definitions.pop(normalized_name)
    backup_definition = definitions[backup_name]
    backup_definition["@EndUserText.label"] = f"Backup of {normalized_name}"

    query = backup_definition.get("query", {}).get("SELECT", {})
    source_ref = query.get("from", {}).get("ref", [])
    if source_ref == [normalized_name]:
        query["from"] = {"ref": [normalized_name]}

    return copied_csn


def execute(params: dict) -> dict:
    """Skill entry point for simple logical backups.

    Required params:
        object_name

    Optional params:
        original_csn
    """
    object_name = params.get("object_name") or params.get("view_name")
    if not object_name:
        return {"status": "error", "message": "Missing required param: object_name"}

    normalized_name = normalize_object_name(object_name)
    backup_name = generate_backup_name(normalized_name)
    original_csn = params.get("original_csn")

    result = {
        "status": "success",
        "original_name": normalized_name,
        "backup_name": backup_name,
    }

    if isinstance(original_csn, dict):
        backup_csn = generate_backup_csn(normalized_name, original_csn, backup_name)
        result["csn"] = backup_csn
        result["output"] = f"Logical backup prepared for {normalized_name} as {backup_name}"
        return result

    result["output"] = f"Backup name prepared for {normalized_name}: {backup_name}"
    return result


register_skill("create_backup", execute)