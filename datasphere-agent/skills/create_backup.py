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
import re
from datetime import datetime

from agent.skill_registry import register_skill


def _extract_object_name(prompt: str) -> str | None:
    """Extract a view technical name from a natural language prompt."""
    match = re.search(r'\b([A-Z]{2}_\w+)\b', prompt.upper())
    if match:
        return match.group(1)
    match = re.search(r'backup\s+(?:view\s+|of\s+|for\s+)?(\w+)', prompt, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


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
    """Normalize an object name: leave it as-is if it already has a XX_ prefix
    (e.g. SV_, GV_, AM_), otherwise prepend the default view prefix.
    """
    name = object_name.upper()
    # If already has any two-letter prefix (SV_, GV_, AM_, etc.) keep it as-is
    if re.match(r'^[A-Z]{2}_', name):
        return name
    prefix = _get_view_prefix()
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
    """Skill entry point – creates a backup view in Datasphere.

    Required params:
        object_name  – technical name of the existing view to back up

    Optional params:
        space_id     – Datasphere space (default: ZZ_BDC_HARNESS_1)
    """
    import json as _json
    import os
    import tempfile

    from executors.datasphere_cli import create_view as cli_create_view, read_view_raw

    object_name = (
        params.get("object_name")
        or params.get("view_name")
        or _extract_object_name(params.get("user_prompt", ""))
    )
    if not object_name:
        return {"status": "error", "message": "Missing required param: object_name"}

    space_id = params.get("space_id", "ZZ_BDC_HARNESS_1")
    normalized_name = normalize_object_name(object_name)

    # 1. Verify the original object exists in Datasphere
    original_csn = read_view_raw(space_id, normalized_name)
    if original_csn is None:
        return {
            "status": "error",
            "message": (
                f"Object '{normalized_name}' not found in space '{space_id}'. "
                "Only existing objects can be backed up."
            ),
        }

    # 2. Generate the backup name
    backup_name = generate_backup_name(normalized_name)

    # 3. Prevent overwriting an existing backup
    existing_backup = read_view_raw(space_id, backup_name)
    if existing_backup is not None:
        return {
            "status": "error",
            "message": (
                f"Backup '{backup_name}' already exists in space '{space_id}'. "
                "Will not overwrite an existing backup."
            ),
        }

    # 4. Build the backup CSN
    try:
        backup_csn = generate_backup_csn(normalized_name, original_csn, backup_name)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    # 5. Persist the backup view to Datasphere via CLI
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    try:
        _json.dump(backup_csn, tmp, ensure_ascii=False, indent=2)
        tmp.close()
        cli_result = cli_create_view(space_id, tmp.name)
    finally:
        os.unlink(tmp.name)

    if "ERROR" in cli_result or "FAILED" in cli_result:
        return {
            "status": "error",
            "original_name": normalized_name,
            "backup_name": backup_name,
            "message": f"CLI failed to persist backup.\n{cli_result}",
        }

    return {
        "status": "success",
        "original_name": normalized_name,
        "backup_name": backup_name,
        "space_id": space_id,
        "output": (
            f"Backup created successfully: '{normalized_name}' → '{backup_name}' "
            f"in space '{space_id}'"
        ),
    }


register_skill("create_backup", execute)