"""Skill: create_association

Adds a cds.Association element to an existing view (SV_ or GV_) so it can
navigate to a master data view.

This skill fetches the source view's current CSN from Datasphere, injects
the association element, and optionally deploys the updated view.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Any

from agent.skill_registry import register_skill

DEFAULT_SPACE = "ZZ_BDC_HARNESS_1"

_PREFIX_RE = re.compile(r"^[A-Z]{2}_", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_association_name(target_view: str) -> str:
    """Derive association element name from target, e.g. SV_COMPANYCODE → TO_COMPANYCODE."""
    stem = _PREFIX_RE.sub("", target_view.upper())
    return f"TO_{stem}"


# ---------------------------------------------------------------------------
# Core CSN builder (public — used by mcp_server and tests)
# ---------------------------------------------------------------------------

def build_association_extension(
    existing_view_csn: dict,
    source_view: str,
    target_view: str,
    join_field_source: str,
    join_field_target: str,
) -> tuple[dict, str, list]:
    """Inject a cds.Association element into an existing view CSN.

    Args:
        existing_view_csn:  Full CSN dict of the source view
        source_view:        Technical name of the view to extend (e.g. SV_BILLING_DOC_JOINED)
        target_view:        Association target view name (e.g. SV_COMPANYCODE)
        join_field_source:  Foreign key column on source (e.g. CompanyCode)
        join_field_target:  Primary key column on target (e.g. CompanyCode)

    Returns:
        (updated_csn, association_name, join_condition)
    """
    definitions = existing_view_csn.setdefault("definitions", {})
    source_def = definitions.get(source_view)
    if not source_def:
        raise ValueError(
            f"Source view '{source_view}' not found in CSN definitions. "
            f"Available: {list(definitions.keys())}"
        )

    elements = source_def.setdefault("elements", {})
    assoc_name = _build_association_name(target_view)
    join_condition = [
        {"ref": [assoc_name, join_field_target]},
        "=",
        {"ref": [join_field_source]},
    ]

    elements[assoc_name] = {
        "type": "cds.Association",
        "target": target_view,
        "cardinality": {"max": 1},
        "@sap.semantics": "to-one",
        "@EndUserText.label": f"Association to {target_view}",
        "on": join_condition,
    }

    return existing_view_csn, assoc_name, join_condition


# ---------------------------------------------------------------------------
# Skill entry point
# ---------------------------------------------------------------------------

def execute(params: dict) -> dict:
    """Add a cds.Association to an existing deployed view.

    Params:
        source_view         View to extend (e.g. SV_BILLING_DOC_JOINED)
        target_view         Association target view (e.g. SV_COMPANYCODE)
        join_field_source   Foreign key on source (e.g. CompanyCode)
        join_field_target   Primary key on target (e.g. CompanyCode)
        space_id            Datasphere space (default: ZZ_BDC_HARNESS_1)
        deploy              Deploy the updated view (default: False)
        confirm             Governance: human sign-off (default: False)
        acknowledge_ai      Governance: AI literacy ack (default: False)
    """
    from executors.datasphere_cli import read_view_raw as cli_read_view_raw
    from executors.datasphere_cli import update_view as cli_update_view
    from executors.datasphere_cli import update_view_no_deploy as cli_update_view_no_deploy

    source_view = params.get("source_view", "").upper().strip()
    target_view = params.get("target_view", "").upper().strip()
    join_field_source = params.get("join_field_source", "").strip()
    join_field_target = params.get("join_field_target", "").strip()
    space_id = params.get("space_id", DEFAULT_SPACE)
    deploy = params.get("deploy", False) is True

    errors: list[str] = []
    if not source_view:
        errors.append("source_view is required")
    if not target_view:
        errors.append("target_view is required")
    if not join_field_source:
        errors.append("join_field_source is required")
    if not join_field_target:
        errors.append("join_field_target is required")
    if deploy:
        if params.get("confirm") is not True:
            errors.append("Human confirmation required: set confirm=true")
        if params.get("acknowledge_ai") is not True:
            errors.append("AI literacy acknowledgement required: set acknowledge_ai=true")
    if errors:
        return {"status": "error", "errors": errors}

    # Fetch source view CSN from Datasphere
    existing_csn = cli_read_view_raw(space_id, source_view)
    if existing_csn is None:
        return {
            "status": "error",
            "errors": [
                f"Could not read view '{source_view}' from space '{space_id}'. "
                "Verify the view is deployed."
            ],
        }

    try:
        updated_csn, assoc_name, join_condition = build_association_extension(
            existing_view_csn=existing_csn,
            source_view=source_view,
            target_view=target_view,
            join_field_source=join_field_source,
            join_field_target=join_field_target,
        )
    except ValueError as exc:
        return {"status": "error", "errors": [str(exc)]}

    if not deploy:
        return {
            "status": "dry_run",
            "source_view": source_view,
            "target_view": target_view,
            "association_name": assoc_name,
            "join_condition": join_condition,
            "space_id": space_id,
            "csn": updated_csn,
            "next_step": (
                "Dry-run only. Set deploy=true + confirm=true + acknowledge_ai=true to deploy."
            ),
        }

    # Deploy
    fd, temp_path = tempfile.mkstemp(suffix=".json", prefix="assoc_csn_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(updated_csn, f, indent=2)
        cli_output = cli_update_view(space_id, temp_path, source_view)
        if "FAILED" in cli_output:
            # Deploy failed — fall back to save-only (no-deploy)
            cli_output = cli_update_view_no_deploy(space_id, temp_path, source_view)
    finally:
        os.unlink(temp_path)

    return {
        "status": "deployed",
        "source_view": source_view,
        "target_view": target_view,
        "association_name": assoc_name,
        "space_id": space_id,
        "cli_output": cli_output,
    }


register_skill("create_association", execute)
