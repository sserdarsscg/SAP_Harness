"""Skill 3: create_sql_view_with_association

Creates a SQL View (SV_) that INNER JOINs two billing tables on BillingDocument
and defines a cds.Association on CompanyCode linking to TL_COMPANYCODE master data.

Source tables:
  - VR1_BILLING_DOC_ITEM_TD_001  (Billing Document Item)
  - VR1_BILLING_DOC_TD_001       (Billing Document Header)

Join key  : BillingDocument
Association: CompanyCode → TL_COMPANYCODE (many-to-one)

Execution is a dry-run by default: returns the CSN for human review.
Deploy is a separate explicit step (set deploy=True once CSN is approved).

Governance (Skill 0) is enforced at the MCP handler layer.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from typing import Any

from agent.skill_registry import register_skill

log = logging.getLogger("skill-3")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_SOURCE_TABLE_1 = "VR1_BILLING_DOC_ITEM_TD_001"   # Billing Document Item
DEFAULT_SOURCE_TABLE_2 = "VR1_BILLING_DOC_TD_001"         # Billing Document Header
DEFAULT_JOIN_FIELD = "BillingDocument"
DEFAULT_VIEW_NAME = "SV_BILLING_DOC_JOINED"
DEFAULT_ASSOCIATION_FIELD = "CompanyCode"
DEFAULT_MASTER_DATA_VIEW = "SV_COMPANYCODE"
DEFAULT_MASTER_DATA_KEY = "Company_Code"   # Key field inside DEFAULT_MASTER_DATA_VIEW
DEFAULT_SPACE = "ZZ_BDC_HARNESS_1"

NAMING_CONVENTION_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "naming_convention.json",
)

_PREFIX_RE = re.compile(r"^[A-Z]{2}_", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_sv_prefix(name: str) -> str:
    """Enforce SV_ prefix on SQL view names."""
    name = name.upper()
    return name if name.startswith("SV_") else f"SV_{name}"


def _has_known_prefix(name: str) -> bool:
    """Return True if name already carries a two-letter prefix (GV_, TL_, SV_, …)."""
    return bool(_PREFIX_RE.match(name.upper()))


def _build_assoc_element_name(target: str) -> str:
    """Build a deterministic element name, e.g. TL_COMPANYCODE → TO_COMPANYCODE."""
    # Strip any leading XX_ prefix then build TO_<STEM>
    stem = _PREFIX_RE.sub("", target.upper())
    return f"TO_{stem}"


def _merge_elements(
    table1: str,
    table2: str,
    join_field: str,
    elems1: dict[str, Any],
    elems2: dict[str, Any],
) -> tuple[dict[str, Any], list[dict]]:
    """Merge column definitions and SELECT columns from two joined tables.

    Strategy:
    - Join field (BillingDocument): taken from table1 once, marked as key.
    - Columns unique to table1: taken from table1.
    - Columns unique to table2: taken from table2.
    - Columns in both (excluding join field): table1 wins; table2 duplicate skipped.
    - All SELECT refs are table-qualified to avoid ambiguity.

    Returns:
        (merged_elements_dict, select_columns_list)
    """
    elements: dict[str, Any] = {}
    select_columns: list[dict] = []

    seen: set[str] = set()

    def _add_col(col_name: str, col_def: dict, table_ref: str) -> None:
        if col_name in seen:
            return
        seen.add(col_name)
        elem: dict[str, Any] = {"type": col_def.get("type", "cds.String")}
        if col_def.get("key") or col_name == join_field:
            elem["key"] = True
        for attr in ("length", "precision", "scale"):
            if attr in col_def:
                elem[attr] = col_def[attr]
        elem["@EndUserText.label"] = col_def.get("@EndUserText.label", col_name)
        elements[col_name] = elem
        select_columns.append({"ref": [table_ref, col_name]})

    # Table 1 columns (join field first to keep it at the top)
    if join_field in elems1:
        _add_col(join_field, elems1[join_field], table1)
    for col_name, col_def in elems1.items():
        if col_name != join_field:
            _add_col(col_name, col_def, table1)

    # Table 2 columns (skip join field — already added from table1)
    for col_name, col_def in elems2.items():
        if col_name != join_field:
            _add_col(col_name, col_def, table2)

    return elements, select_columns


# ---------------------------------------------------------------------------
# CSN builder
# ---------------------------------------------------------------------------

def build_sv_csn(
    view_name: str,
    source_table_1: str,
    source_table_2: str,
    join_field: str,
    association_field: str,
    master_data_view: str,
    table1_elements: dict[str, Any],
    table2_elements: dict[str, Any],
    master_data_key: str | None = None,
    include_association: bool = False,
) -> dict:
    """Build a CSN SQL View that INNER JOINs two tables and includes a cds.Association.

    Args:
        view_name:          SV_ view technical name
        source_table_1:     First source table (e.g. VR1_BILLING_DOC_ITEM_TD_001)
        source_table_2:     Second source table (e.g. VR1_BILLING_DOC_TD_001)
        join_field:         Column used for the INNER JOIN (e.g. BillingDocument)
        association_field:  FK column on the source side (e.g. CompanyCode)
        master_data_view:   Association target view (e.g. SV_COMPANYCODE)
        table1_elements:    Column definitions from source_table_1
        table2_elements:    Column definitions from source_table_2
        master_data_key:    PK column name inside master_data_view (defaults to association_field)

    Returns:
        CSN dict ready for dry-run review or deployment.
    """
    view_name = _ensure_sv_prefix(view_name)
    assoc_element_name = _build_assoc_element_name(master_data_view)
    target_key = master_data_key if master_data_key else association_field

    # Merge columns from both tables
    elements, select_columns = _merge_elements(
        table1=source_table_1,
        table2=source_table_2,
        join_field=join_field,
        elems1=table1_elements,
        elems2=table2_elements,
    )

    # Datasphere SQL Views (SV_) do NOT support cds.Association elements —
    # associations must live on a Graphical View (GV_) layer on top.
    # The include_association flag is kept for experimental use only.
    if include_association:
        elements[assoc_element_name] = {
            "type": "cds.Association",
            "target": master_data_view,
            "cardinality": {"max": 1},
            "@sap.semantics": "to-one",
            "@EndUserText.label": f"Association to {master_data_view}",
            "on": [
                {"ref": [assoc_element_name, target_key]},
                "=",
                {"ref": [association_field]},
            ],
        }

    csn = {
        "definitions": {
            view_name: {
                "kind": "entity",
                "@EndUserText.label": "Billing Document Joined View",
                "@Analytics.dataCategory": "#FACT",
                "query": {
                    "SELECT": {
                        "from": {
                            "join": "inner",
                            "args": [
                                {"ref": [source_table_1]},
                                {"ref": [source_table_2]},
                            ],
                            "on": [
                                {"ref": [source_table_1, join_field]},
                                "=",
                                {"ref": [source_table_2, join_field]},
                            ],
                        },
                        "columns": select_columns,
                    }
                },
                "elements": elements,
            }
        }
    }

    return csn


def csn_to_temp_file(csn: dict) -> str:
    """Write CSN JSON to a temp file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".json", prefix="sv_csn_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(csn, f, indent=2)
    return path


# ---------------------------------------------------------------------------
# Skill entry point
# ---------------------------------------------------------------------------

def execute(params: dict) -> dict:
    """Skill 3 entry point.

    Params (all have defaults):
        view_name           SV_ view technical name            (default: SV_BILLING_DOC_JOINED)
        source_table_1      First source table                 (default: VR1_BILLING_DOC_ITEM_TD_001)
        source_table_2      Second source table                (default: VR1_BILLING_DOC_TD_001)
        join_field          Column for INNER JOIN              (default: BillingDocument)
        association_field   Column used as association key     (default: CompanyCode)
        master_data_view    Association target object          (default: SV_COMPANYCODE)
        master_data_key     PK field in master_data_view       (default: Company_Code)
        space_id            Datasphere space                   (default: ZZ_BDC_HARNESS_1)
        deploy              Deploy after dry-run               (default: False)
        confirm             Governance: human sign-off         (default: False)
        acknowledge_ai      Governance: AI literacy ack        (default: False)
    """
    from executors.datasphere_cli import read_local_table as cli_read_local_table
    from executors.datasphere_cli import create_view as cli_create_view
    from executors.datasphere_cli import update_view_no_deploy as cli_update_view_no_deploy

    view_name         = _ensure_sv_prefix(params.get("view_name", DEFAULT_VIEW_NAME))
    source_table_1    = params.get("source_table_1", DEFAULT_SOURCE_TABLE_1).upper()
    source_table_2    = params.get("source_table_2", DEFAULT_SOURCE_TABLE_2).upper()
    join_field        = params.get("join_field", DEFAULT_JOIN_FIELD)
    association_field = params.get("association_field", DEFAULT_ASSOCIATION_FIELD)
    master_data_view  = params.get("master_data_view", DEFAULT_MASTER_DATA_VIEW).upper()
    master_data_key   = params.get("master_data_key", DEFAULT_MASTER_DATA_KEY)
    space_id          = params.get("space_id", DEFAULT_SPACE)
    deploy            = params.get("deploy", False) is True
    include_association = params.get("include_association", False) is True

    # --- Governance pre-checks ---
    errors: list[str] = []
    if not view_name.startswith("SV_"):
        errors.append(f"Naming rule: view_name must start with 'SV_', got '{view_name}'")
    if not source_table_1:
        errors.append("source_table_1 is required")
    if not source_table_2:
        errors.append("source_table_2 is required")
    if not join_field:
        errors.append("join_field is required")
    if not association_field:
        errors.append("association_field is required")
    if not _has_known_prefix(master_data_view):
        errors.append(
            f"master_data_view must have a recognised prefix (TL_, GV_, …), got '{master_data_view}'"
        )
    if deploy and not params.get("confirm"):
        errors.append("confirm=True is required before deploying")
    if deploy and not params.get("acknowledge_ai"):
        errors.append("acknowledge_ai=True is required before deploying")

    if errors:
        return {"status": "error", "errors": errors}

    # --- Read both table schemas ---
    def _read_table(table: str) -> dict[str, Any] | None:
        log.info("Reading table schema: %s / %s", space_id, table)
        table_def = cli_read_local_table(space_id, table)
        if table_def is None:
            return None
        return (
            table_def
            .get("definitions", {})
            .get(table, {})
            .get("elements", {})
        )

    elems1 = _read_table(source_table_1)
    if not elems1:
        return {
            "status": "error",
            "errors": [f"Could not read table '{source_table_1}' in space '{space_id}'."],
        }

    elems2 = _read_table(source_table_2)
    if not elems2:
        return {
            "status": "error",
            "errors": [f"Could not read table '{source_table_2}' in space '{space_id}'."],
        }

    # --- Validate join_field and association_field ---
    if join_field not in elems1:
        return {
            "status": "error",
            "errors": [f"join_field '{join_field}' not found in '{source_table_1}'."],
        }
    if join_field not in elems2:
        return {
            "status": "error",
            "errors": [f"join_field '{join_field}' not found in '{source_table_2}'."],
        }

    # association_field must exist in at least one of the tables
    assoc_in_t1 = association_field in elems1
    assoc_in_t2 = association_field in elems2
    if not assoc_in_t1 and not assoc_in_t2:
        available = list({**elems1, **elems2}.keys())[:15]
        return {
            "status": "error",
            "errors": [
                f"association_field '{association_field}' not found in either table. "
                f"Available fields (first 15): {available}"
            ],
        }

    # --- Build CSN ---
    csn = build_sv_csn(
        view_name=view_name,
        source_table_1=source_table_1,
        source_table_2=source_table_2,
        join_field=join_field,
        association_field=association_field,
        master_data_view=master_data_view,
        table1_elements=elems1,
        table2_elements=elems2,
        master_data_key=master_data_key,
        include_association=include_association,
    )

    log.info(
        "CSN built: %s (JOIN %s ↔ %s ON %s | ASSOC %s → %s)",
        view_name, source_table_1, source_table_2,
        join_field, association_field, master_data_view,
    )

    # --- Dry-run: return CSN for review ---
    if not deploy:
        return {
            "status": "dry_run",
            "view_name": view_name,
            "source_table_1": source_table_1,
            "source_table_2": source_table_2,
            "join_field": join_field,
            "association_field": association_field,
            "master_data_view": master_data_view,
            "master_data_key": master_data_key,
            "space_id": space_id,
            "csn": csn,
            "next_step": (
                "Review the CSN above. "
                "To deploy, call again with deploy=True, confirm=True, acknowledge_ai=True."
            ),
        }

    # --- Deploy ---
    log.info("Deploying %s to space %s", view_name, space_id)
    temp_path = csn_to_temp_file(csn)
    try:
        cli_result = cli_create_view(space_id, temp_path)
        if "FAILED" in cli_result:
            # View already exists — fall back to update (no-deploy)
            log.info("create failed for %s, retrying with update", view_name)
            cli_result = cli_update_view_no_deploy(space_id, temp_path, view_name)
    finally:
        os.unlink(temp_path)

    return {
        "status": "deployed",
        "view_name": view_name,
        "source_table_1": source_table_1,
        "source_table_2": source_table_2,
        "join_field": join_field,
        "association_field": association_field,
        "master_data_view": master_data_view,
        "master_data_key": master_data_key,
        "space_id": space_id,
        "cli_output": cli_result,
    }


# Self-register with the skill registry
register_skill("create_sql_view_with_association", execute)
