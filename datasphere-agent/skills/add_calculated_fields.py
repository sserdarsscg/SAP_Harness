"""Skill 4: add_calculated_fields

Adds two calculated columns to an existing SQL view (SV_) in SAP Datasphere
by reading the live CSN, injecting xpr column definitions, and updating the view.

Calculated fields:
  - GrossAmount       = NetAmount + TaxAmount          (cds.Decimal 34,4)
  - QuantityCategory  = CASE WHEN BillingQuantity > 100 THEN 'High'
                             WHEN BillingQuantity > 10  THEN 'Medium'
                             ELSE 'Low' END             (cds.String 6)

The skill reads the current deployed view CSN from Datasphere so that
table-qualified column refs (e.g. ["VR1_BILLING_DOC_ITEM_TD_001","NetAmount"])
are preserved exactly as the platform expects.

Defaults to a dry-run. Set deploy=True (plus confirm=True and acknowledge_ai=True)
to push the updated CSN to Datasphere.

Governance is enforced at the MCP handler layer via governance_guard.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile

from agent.skill_registry import register_skill

log = logging.getLogger("skill-4")

DEFAULT_VIEW_NAME = "SV_BILLING_DOC_JOINED"
DEFAULT_SPACE = "ZZ_BDC_HARNESS_1"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_qualified_ref_map(columns: list) -> dict[str, list]:
    """Scan SELECT.columns and map column name (uppercase) → ref list.

    Handles both table-qualified refs   ["TABLE", "COLUMN"]
    and unqualified refs                ["COLUMN"].
    Skips xpr columns (already calculated — no plain ref key).
    """
    ref_map: dict[str, list] = {}
    for col in columns:
        if not isinstance(col, dict):
            continue
        ref = col.get("ref")
        if not ref:
            continue
        if len(ref) == 2:
            # table-qualified: ["TABLE", "COLUMN"]
            ref_map[ref[1].upper()] = ref
        elif len(ref) == 1:
            # unqualified: ["COLUMN"]
            ref_map[ref[0].upper()] = ref
    return ref_map


def _build_gross_amount_column(ref_map: dict[str, list]) -> dict:
    """Return CSN xpr dict for NetAmount + TaxAmount aliased as GrossAmount."""
    net_ref = ref_map.get("NETAMOUNT", ["NetAmount"])
    tax_ref = ref_map.get("TAXAMOUNT", ["TaxAmount"])
    return {
        "xpr": [
            {"ref": net_ref},
            "+",
            {"ref": tax_ref},
        ],
        "as": "GrossAmount",
    }


def _build_quantity_category_column(ref_map: dict[str, list]) -> dict:
    """Return CSN xpr dict for the BillingQuantity CASE expression aliased as QuantityCategory.

    Logic:
        CASE WHEN BillingQuantity > 100 THEN 'High'
             WHEN BillingQuantity > 10  THEN 'Medium'
             ELSE 'Low'
        END
    """
    qty_ref = ref_map.get("BILLINGQUANTITY", ["BillingQuantity"])
    return {
        "xpr": [
            "case",
            "when", {"ref": qty_ref}, ">", {"val": 100},
            "then", {"val": "High"},
            "when", {"ref": qty_ref}, ">", {"val": 10},
            "then", {"val": "Medium"},
            "else", {"val": "Low"},
            "end",
        ],
        "as": "QuantityCategory",
    }


def _patch_sql_editor_query(sql: str, item_alias: str) -> str:
    """Inject GrossAmount and QuantityCategory into @DataWarehouse.sqlEditor.query.

    The Datasphere UI SQL editor renders this annotation string, NOT the CSN xpr
    column nodes. Both representations must be updated so the UI shows the logic.

    Inserts the two SQL expressions immediately before the \\nFROM clause.
    Is idempotent: if 'GrossAmount' is already present the string is returned unchanged.
    """
    if not item_alias or "GrossAmount" in sql:
        return sql
    new_cols = (
        f',\n  "{item_alias}"."NetAmount" + "{item_alias}"."TaxAmount" AS "GrossAmount"'
        f',\n  CASE WHEN "{item_alias}"."BillingQuantity" > 100 THEN \'High\''
        f' WHEN "{item_alias}"."BillingQuantity" > 10 THEN \'Medium\''
        f' ELSE \'Low\' END AS "QuantityCategory"'
    )
    from_idx = sql.find('\nFROM ')
    if from_idx == -1:
        log.warning("Could not find \\nFROM in sqlEditor.query; SQL annotation not patched")
        return sql
    return sql[:from_idx] + new_cols + sql[from_idx:]


# ---------------------------------------------------------------------------
# Public generator (used by tests and mcp_server directly)
# ---------------------------------------------------------------------------

def inject_calculated_fields(existing_csn: dict, view_name: str) -> dict:
    """Inject GrossAmount and QuantityCategory into existing_csn in-place.

    Args:
        existing_csn:  Parsed CSN dict fetched from Datasphere.
        view_name:     Canonical technical name of the view (e.g. SV_BILLING_DOC_JOINED).

    Returns:
        The mutated existing_csn dict.

    Raises:
        ValueError: if the view is not found in definitions.
    """
    definitions = existing_csn.get("definitions", {})
    if view_name not in definitions:
        raise ValueError(
            f"View '{view_name}' not found in CSN definitions. "
            f"Available: {list(definitions.keys())}"
        )

    view_def = definitions[view_name]
    elements: dict = view_def.setdefault("elements", {})
    select: dict = view_def.setdefault("query", {}).setdefault("SELECT", {})
    columns: list = select.setdefault("columns", [])

    ref_map = _build_qualified_ref_map(columns)

    if "GrossAmount" not in elements:
        columns.append(_build_gross_amount_column(ref_map))
        elements["GrossAmount"] = {
            "type": "cds.Decimal",
            "precision": 34,
            "scale": 4,
            "@EndUserText.label": "Gross Amount",
        }
        log.debug("Injected GrossAmount column")

    if "QuantityCategory" not in elements:
        columns.append(_build_quantity_category_column(ref_map))
        elements["QuantityCategory"] = {
            "type": "cds.String",
            "length": 6,
            "@EndUserText.label": "Quantity Category",
        }
        log.debug("Injected QuantityCategory column")

    # Patch @DataWarehouse.sqlEditor.query – the SQL string the UI editor displays.
    # This annotation is separate from the CSN xpr nodes and must be updated
    # independently; otherwise the UI shows the old SQL without the new columns.
    sql_key = "@DataWarehouse.sqlEditor.query"
    if sql_key in view_def:
        item_alias = (ref_map.get("NETAMOUNT") or [""])[0]
        view_def[sql_key] = _patch_sql_editor_query(view_def[sql_key], item_alias)
        log.debug("Patched sqlEditor.query with item alias '%s'", item_alias)

    return existing_csn


# ---------------------------------------------------------------------------
# Skill entry point
# ---------------------------------------------------------------------------

def execute(params: dict) -> dict:
    """Add GrossAmount and QuantityCategory calculated columns to an existing SV_ view.

    Params:
        view_name       Technical name of the SQL view (default: SV_BILLING_DOC_JOINED).
        space_id        Datasphere space (default: ZZ_BDC_HARNESS_1).
        deploy          Deploy the updated view (default: False → dry-run).
        confirm         Governance: human sign-off (required when deploy=True).
        acknowledge_ai  Governance: AI literacy ack (required when deploy=True).
    """
    from executors.datasphere_cli import read_view_raw as cli_read_view_raw
    from executors.datasphere_cli import update_view as cli_update_view
    from executors.datasphere_cli import update_view_no_deploy as cli_update_view_no_deploy

    view_name = params.get("view_name", DEFAULT_VIEW_NAME).upper().strip()
    space_id = params.get("space_id", DEFAULT_SPACE)
    deploy = params.get("deploy", False) is True

    # -----------------------------------------------------------------------
    # Input validation
    # -----------------------------------------------------------------------
    errors: list[str] = []
    if not view_name.startswith("SV_"):
        errors.append(
            f"Naming rule violation: view name must start with 'SV_'. Got: '{view_name}'"
        )
    if deploy:
        if params.get("confirm") is not True:
            errors.append("Human confirmation required: set confirm=true.")
        if params.get("acknowledge_ai") is not True:
            errors.append(
                "AI literacy acknowledgement required: set acknowledge_ai=true "
                "to confirm you reviewed AI-generated output before execution."
            )
    if errors:
        return {"status": "error", "errors": errors}

    # -----------------------------------------------------------------------
    # Fetch live CSN from Datasphere
    # -----------------------------------------------------------------------
    log.info("Reading view '%s' from space '%s'", view_name, space_id)
    existing_csn = cli_read_view_raw(space_id, view_name)
    if existing_csn is None:
        return {
            "status": "error",
            "errors": [
                f"Could not read view '{view_name}' from space '{space_id}'. "
                "Verify the view is deployed and the space ID is correct."
            ],
        }

    # -----------------------------------------------------------------------
    # Idempotency check
    # -----------------------------------------------------------------------
    definitions = existing_csn.get("definitions", {})
    if view_name not in definitions:
        return {
            "status": "error",
            "errors": [
                f"View '{view_name}' not found in CSN definitions. "
                f"Available: {list(definitions.keys())}"
            ],
        }

    existing_elements = definitions[view_name].get("elements", {})
    already_gross = "GrossAmount" in existing_elements
    already_qty_cat = "QuantityCategory" in existing_elements

    # Also check if the UI SQL annotation already has the columns.
    # If elements are present but the SQL string is missing them, we still need
    # to re-deploy so the Datasphere UI SQL editor shows the correct expressions.
    sql_key = "@DataWarehouse.sqlEditor.query"
    existing_sql = definitions[view_name].get(sql_key, "")
    sql_already_patched = "GrossAmount" in existing_sql

    if already_gross and already_qty_cat and sql_already_patched:
        return {
            "status": "already_applied",
            "view_name": view_name,
            "space_id": space_id,
            "message": (
                "Both GrossAmount and QuantityCategory are already present in the view. "
                "No changes needed."
            ),
        }

    # -----------------------------------------------------------------------
    # Inject calculated fields into CSN
    # -----------------------------------------------------------------------
    try:
        updated_csn = inject_calculated_fields(existing_csn, view_name)
    except ValueError as exc:
        return {"status": "error", "errors": [str(exc)]}

    if not deploy:
        return {
            "status": "dry_run",
            "view_name": view_name,
            "space_id": space_id,
            "csn": updated_csn,
            "next_step": (
                "Dry-run only. Set deploy=true + confirm=true + acknowledge_ai=true to deploy."
            ),
        }

    # -----------------------------------------------------------------------
    # Deploy
    # -----------------------------------------------------------------------
    fd, temp_path = tempfile.mkstemp(suffix=".json", prefix="calc_fields_csn_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(updated_csn, f, indent=2)

        log.info("Deploying updated CSN for '%s'", view_name)
        cli_output = cli_update_view(space_id, temp_path, view_name)

        if "FAILED" in cli_output:
            log.warning("Deploy failed, falling back to save-only (--no-deploy)")
            cli_output = cli_update_view_no_deploy(space_id, temp_path, view_name)
    finally:
        os.unlink(temp_path)

    return {
        "status": "deployed",
        "view_name": view_name,
        "space_id": space_id,
        "cli_output": cli_output,
    }


register_skill("add_calculated_fields", execute)
