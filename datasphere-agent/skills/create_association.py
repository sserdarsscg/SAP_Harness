"""Skill: create_association

Adds one or more cds.Association elements to an existing view (SV_ or GV_)
so it can navigate to master-data views.

The four-step CSN protocol is followed precisely:
  1. @ObjectModel.foreignKey.association annotation on the FK field in elements
  2. Association element in elements (bare refs in `on`)
  3. Association ref appended to query.SELECT.columns
  4. Association entry in query.SELECT.mixin ($projection prefix on source refs)

This skill fetches the source view's current CSN from Datasphere, injects
the association elements, and optionally deploys the updated view.
"""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any

from agent.skill_registry import register_skill

DEFAULT_SPACE = "ZZ_BDC_HARNESS_1"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_association_name(target_view: str) -> str:
    """Derive association name: '_' + first 9 chars of target view name (max 10 total).

    Examples:
        V_I_COMPANYCODE                => _V_I_COMPA
        V_I_FISCALYEARPERIODFORVARIANT => _V_I_FISCA
    """
    return "_" + target_view[:9]


def _build_on_condition(
    assoc_name: str,
    join_fields: list,
    use_projection: bool,
) -> list:
    """Build the `on` condition list for a cds.Association.

    Args:
        assoc_name:      e.g. "_V_I_COMPA"
        join_fields:     [{"source_field": "CompanyCode", "target_field": "CompanyCode"}, ...]
        use_projection:  True  => source ref uses ["$projection", field]  (mixin)
                         False => source ref uses [field]                  (elements)
    """
    condition = []
    for i, pair in enumerate(join_fields):
        if i > 0:
            condition.append("and")
        src_ref = ["$projection", pair["source_field"]] if use_projection else [pair["source_field"]]
        condition.append({"ref": src_ref})
        condition.append("=")
        condition.append({"ref": [assoc_name, pair["target_field"]]})
    return condition


# ---------------------------------------------------------------------------
# Core CSN builder (public -- used by mcp_server and tests)
# ---------------------------------------------------------------------------

def build_association_extension(
    existing_view_csn: dict,
    source_view: str,
    target_view: str,
    join_fields: list,
    source_label: str = "",
    target_label: str = "",
) -> tuple:
    """Inject a cds.Association into an existing view CSN (four-step protocol).

    Mutates existing_view_csn in-place and also returns it.

    Args:
        existing_view_csn:  Full CSN dict of the source view.
        source_view:        Technical name of the view to extend.
        target_view:        Association target view technical name.
        join_fields:        List of {"source_field": ..., "target_field": ...} dicts.
                            Single-key: one entry.  Compound-key: all key pairs in order.
        source_label:       @EndUserText.label of the source view.
                            Falls back to source_view if empty.
        target_label:       @EndUserText.label of the target view.
                            Falls back to target_view if empty.

    Returns:
        (updated_csn, association_name)
    """
    if not join_fields:
        raise ValueError("join_fields must contain at least one entry")

    definitions = existing_view_csn.setdefault("definitions", {})
    source_def = definitions.get(source_view)
    if not source_def:
        raise ValueError(
            f"Source view '{source_view}' not found in CSN definitions. "
            f"Available: {list(definitions.keys())}"
        )

    assoc_name = _build_association_name(target_view)
    src_lbl = source_label or source_view
    tgt_lbl = target_label or target_view
    assoc_label = f"{src_lbl} to {tgt_lbl}"

    # -------------------------------------------------------------------
    # Step 1 -- Annotate the leading FK field in elements
    # -------------------------------------------------------------------
    elements = source_def.setdefault("elements", {})
    first_source_field = join_fields[0]["source_field"]
    if first_source_field in elements:
        elements[first_source_field]["@ObjectModel.foreignKey.association"] = {"=": assoc_name}

    # -------------------------------------------------------------------
    # Step 2 -- Add association element to elements (bare refs)
    # -------------------------------------------------------------------
    on_bare = _build_on_condition(assoc_name, join_fields, use_projection=False)
    elements[assoc_name] = {
        "type": "cds.Association",
        "@EndUserText.label": assoc_label,
        "on": on_bare,
        "target": target_view,
    }

    # -------------------------------------------------------------------
    # Step 3 -- Append association ref to query.SELECT.columns
    # -------------------------------------------------------------------
    select = source_def.setdefault("query", {}).setdefault("SELECT", {})
    columns = select.setdefault("columns", [])
    if not any(isinstance(c, dict) and c.get("ref") == [assoc_name] for c in columns):
        columns.append({"ref": [assoc_name]})

    # -------------------------------------------------------------------
    # Step 4 -- Add to query.SELECT.mixin ($projection prefix on source refs)
    # -------------------------------------------------------------------
    on_proj = _build_on_condition(assoc_name, join_fields, use_projection=True)
    mixin = select.setdefault("mixin", {})
    mixin[assoc_name] = {
        "type": "cds.Association",
        "@EndUserText.label": assoc_label,
        "on": on_proj,
        "target": target_view,
    }

    return existing_view_csn, assoc_name


# ---------------------------------------------------------------------------
# Skill entry point
# ---------------------------------------------------------------------------

def execute(params: dict) -> dict:
    """Add one or more cds.Associations to an existing deployed view.

    Params:
        source_view         View to extend (e.g. SV_BILLING_DOC_JOINED)
        target_view         Association target view (e.g. V_I_COMPANYCODE)
        join_fields         List of {source_field, target_field} dicts.
                            Single-key: [{"source_field": "CompanyCode",
                                          "target_field": "CompanyCode"}]
                            Compound-key: multiple entries in key order.
        join_field_source   Shorthand for single-key: source field name.
                            Ignored when join_fields is provided.
        join_field_target   Shorthand for single-key: target field name.
                            Ignored when join_fields is provided.
        target_label        Human-readable label for the target view (optional).
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
    space_id = params.get("space_id", DEFAULT_SPACE)
    deploy = params.get("deploy", False) is True
    target_label = params.get("target_label", "").strip()

    # Resolve join_fields -- support both list form and legacy single-field shorthand.
    raw_join_fields = params.get("join_fields")
    if raw_join_fields:
        join_fields = [
            {"source_field": jf["source_field"], "target_field": jf["target_field"]}
            for jf in raw_join_fields
        ]
    else:
        jfs = params.get("join_field_source", "").strip()
        jft = params.get("join_field_target", "").strip()
        join_fields = [{"source_field": jfs, "target_field": jft}] if jfs and jft else []

    errors = []
    if not source_view:
        errors.append("source_view is required")
    if not target_view:
        errors.append("target_view is required")
    if not join_fields:
        errors.append("join_fields (or join_field_source + join_field_target) is required")
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

    # Derive source label from CSN
    source_def = existing_csn.get("definitions", {}).get(source_view, {})
    source_label = source_def.get("@EndUserText.label", source_view)

    try:
        updated_csn, assoc_name = build_association_extension(
            existing_view_csn=existing_csn,
            source_view=source_view,
            target_view=target_view,
            join_fields=join_fields,
            source_label=source_label,
            target_label=target_label,
        )
    except ValueError as exc:
        return {"status": "error", "errors": [str(exc)]}

    if not deploy:
        return {
            "status": "dry_run",
            "source_view": source_view,
            "target_view": target_view,
            "association_name": assoc_name,
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
