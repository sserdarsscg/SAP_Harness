"""
Skill: share_to_space

Shares a view (or list of views) from one SAP Datasphere space to another
by adding the @DataWarehouse.shareTo CSN annotation and updating the view
via the datasphere CLI.

The workflow:
1. Read the current CSN definition of the view
2. Add/merge @DataWarehouse.shareTo with the target space(s)
3. Write updated CSN to a temp file
4. Call `datasphere objects views update` to persist the change
"""

import json
import os
import tempfile
from agent.skill_registry import register_skill


def build_share_csn(view_csn: dict, target_spaces: list[str]) -> dict:
    """
    Take an existing view CSN and add/merge @DataWarehouse.shareTo annotation.

    Args:
        view_csn:      Full CSN dict as returned by `views read`
        target_spaces: List of space IDs to share to

    Returns:
        Updated CSN dict with shareTo annotation merged.
    """
    definitions = view_csn.get("definitions", {})
    for view_name, view_def in definitions.items():
        existing = view_def.get("@DataWarehouse.shareTo", [])
        merged = list(set(existing) | set(target_spaces))
        view_def["@DataWarehouse.shareTo"] = sorted(merged)

    return view_csn


def share_csn_to_temp_file(csn: dict) -> str:
    """Write updated CSN to a temporary file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".json", prefix="share_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(csn, f, indent=2)
    return path


def execute(params: dict) -> dict:
    """
    Skill entry point for CLI planner.
    Generates share CSN and shows the dry-run output.
    """
    view_names = params.get("view_names", [])
    target_spaces = params.get("target_spaces", [])
    source_space = params.get("source_space", "ZZ_BDC_HARNESS_1")

    if not view_names or not target_spaces:
        return {
            "status": "error",
            "message": "view_names and target_spaces are required.",
        }

    results = []
    for vn in view_names:
        results.append(
            f"-- Would share {vn} from {source_space} to {target_spaces}"
        )

    return {
        "status": "ok",
        "message": "\n".join(results),
    }


register_skill("share_to_space", execute)
