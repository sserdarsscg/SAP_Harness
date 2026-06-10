"""
MCP Server – stdio JSON-RPC 2.0 transport for Datasphere agent skills.

This is a minimal Model Context Protocol (MCP) server that:
  - Reads JSON-RPC 2.0 messages from STDIN (one per line)
  - Writes JSON-RPC 2.0 responses to STDOUT (one per line)
  - Exposes tool discovery  (method: "initialize", "tools/list")
  - Exposes tool invocation  (method: "tools/call")

All operations run LIVE against SAP Datasphere.
"""

import json
import sys
import logging
from typing import Any
from agent.governance_guard import validate_skill_call, log_skill_action

# ---------------------------------------------------------------------------
# Logging – all diagnostic output goes to STDERR so STDOUT stays clean
# for JSON-RPC messages.
# ---------------------------------------------------------------------------
logging.basicConfig(
    stream=sys.stderr,
    level=logging.DEBUG,
    format="[mcp-server] %(levelname)s %(message)s",
)
log = logging.getLogger("mcp-server")

# ---------------------------------------------------------------------------
# Skill imports – import the public helpers directly (no stdout side-effects)
# ---------------------------------------------------------------------------
from skills.bronze_to_silver import generate_sql        # noqa: E402
from skills.read_view import generate_read_sql            # noqa: E402
from skills.create_view import generate_csn, csn_to_temp_file, _ensure_prefix  # noqa: E402
from skills.share_to_space import build_share_csn, share_csn_to_temp_file  # noqa: E402
from skills.create_association import build_association_extension  # noqa: E402
from skills.create_sql_view_with_association import build_sv_csn  # noqa: E402
from skills.add_columns import inject_columns  # noqa: E402
from skills.create_transformation_flow import build_local_table_csn, build_transformation_flow_csn  # noqa: E402
from skills.create_task_chain import build_task_chain_csn, derive_tc_name  # noqa: E402

# Live CLI imports (no mock mode)
from executors.datasphere_cli import (                   # noqa: E402
    list_spaces,
    read_space,
    list_views,
    read_view as cli_read_view,
    create_view as cli_create_view,
    read_local_table as cli_read_local_table,
    read_view_raw as cli_read_view_raw,
    update_view as cli_update_view,
    update_view_no_deploy as cli_update_view_no_deploy,
    list_dbusers,
)

# ---------------------------------------------------------------------------
# MCP protocol constants
# ---------------------------------------------------------------------------
PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "datasphere-mcp"
SERVER_VERSION = "0.4.0"

# ---------------------------------------------------------------------------
# Tool catalogue – each entry follows the MCP Tool schema
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "bronze_to_silver",
        "description": (
            "Generate a SQL transformation that moves a table "
            "from a raw/landing (bronze) layer to a cleansed/harmonized "
            "(silver) layer in SAP Datasphere. "
            "Executes live transformation against Datasphere."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {
                    "type": "string",
                    "description": "Name of the table to transform (e.g. CUSTOMER, ORDERS).",
                },
                "source_layer": {
                    "type": "string",
                    "description": "Schema / layer where the source table resides.",
                    "default": "bronze",
                },
                "target_layer": {
                    "type": "string",
                    "description": "Schema / layer the transformed data will be written to.",
                    "default": "silver",
                },
            },
            "required": ["table_name"],
        },
    },
    {
        "name": "read_view",
        "description": (
            "Read the JSON definition of a deployed view from SAP Datasphere "
            "using the datasphere CLI. Available spaces: ZZ_BDC_HARNESS_1, "
            "ZZ_BDC_HARNESS_2. Returns the SELECT SQL statement to read from it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "view_name": {
                    "type": "string",
                    "description": "Technical name of the view (e.g. ADSO_Sales_Document_Item_Data_V).",
                    "default": "ADSO_Sales_Document_Item_Data_V",
                },
                "space_id": {
                    "type": "string",
                    "description": "Datasphere space ID. Available: ZZ_BDC_HARNESS_1, ZZ_BDC_HARNESS_2.",
                    "default": "ZZ_BDC_HARNESS_1",
                },
            },
            "required": [],
        },
    },
    {
        "name": "list_spaces",
        "description": (
            "List all available spaces in the SAP Datasphere tenant "
            "using the datasphere CLI. Returns space IDs and metadata."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "read_space",
        "description": (
            "Fetch detailed information about a specific space in SAP Datasphere "
            "using the datasphere CLI."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "space_id": {
                    "type": "string",
                    "description": "Space ID to read (e.g. ZZ_BDC_HARNESS_1).",
                    "default": "ZZ_BDC_HARNESS_1",
                },
            },
            "required": [],
        },
    },
    {
        "name": "list_views",
        "description": (
            "List all views in a given space in SAP Datasphere "
            "using the datasphere CLI."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "space_id": {
                    "type": "string",
                    "description": "Space ID to list views from. Available: ZZ_BDC_HARNESS_1, ZZ_BDC_HARNESS_2.",
                    "default": "ZZ_BDC_HARNESS_1",
                },
            },
            "required": [],
        },
    },
    {
        "name": "create_view",
        "description": (
            "Create a new view in SAP Datasphere. Provide the view name, "
            "business name, and column definitions. The view is created in "
            "CSN format via the datasphere CLI. "
            "Available spaces: ZZ_BDC_HARNESS_1, ZZ_BDC_HARNESS_2. "
            "Supports both Graphical Views (GV_) and SQL Views (SV_)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "view_name": {
                    "type": "string",
                    "description": "Technical name for the view (e.g. V_SALES_ITEMS).",
                },
                "business_name": {
                    "type": "string",
                    "description": "Human-readable label for the view.",
                },
                "view_type": {
                    "type": "string",
                    "description": "View type: 'GV' for Graphical View (default) or 'SV' for SQL View.",
                    "enum": ["GV", "SV"],
                    "default": "GV",
                },
                "space_id": {
                    "type": "string",
                    "description": "Space to create the view in. Available: ZZ_BDC_HARNESS_1, ZZ_BDC_HARNESS_2.",
                    "default": "ZZ_BDC_HARNESS_1",
                },
                "source_table": {
                    "type": "string",
                    "description": "Source table technical name to create a pass-through view from. If provided, columns are read from the table automatically. Use 'columns' to filter specific columns.",
                },
                "columns": {
                    "type": "array",
                    "description": "Column definitions or column name filter. If source_table is provided, this can be a list of column names to include (strings). Otherwise, full definitions: {name, type, key?, length?, label?}.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "type": {"type": "string", "default": "cds.String"},
                            "key": {"type": "boolean"},
                            "length": {"type": "integer"},
                            "label": {"type": "string"},
                        },
                        "required": ["name"],
                    },
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Human confirmation flag. Must be true to execute mutating actions.",
                    "default": False,
                },
                "acknowledge_ai": {
                    "type": "boolean",
                    "description": "AI literacy acknowledgement. Must be true to confirm review of AI-generated output before execution.",
                    "default": False,
                },
            },
            "required": ["view_name"],
        },
    },
    {
        "name": "share_to_space",
        "description": (
            "Share one or more views from a source space to one or more target "
            "spaces in SAP Datasphere. Adds the @DataWarehouse.shareTo CSN "
            "annotation and updates each view via the CLI. "
            "Views must be deployed before sharing."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "view_names": {
                    "type": "array",
                    "description": "List of view technical names to share (e.g. ['GV_BILLING_DOC_ITEM', 'GV_CHART_OF_ACCOUNT']).",
                    "items": {"type": "string"},
                },
                "target_spaces": {
                    "type": "array",
                    "description": "List of target space IDs to share to (e.g. ['ZZ_BDC_HARNESS_2']).",
                    "items": {"type": "string"},
                },
                "source_space": {
                    "type": "string",
                    "description": "Source space ID where views currently reside.",
                    "default": "ZZ_BDC_HARNESS_1",
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Human confirmation flag. Must be true to execute mutating actions.",
                    "default": False,
                },
                "acknowledge_ai": {
                    "type": "boolean",
                    "description": "AI literacy acknowledgement. Must be true to confirm review of AI-generated output before execution.",
                    "default": False,
                },
            },
            "required": ["view_names", "target_spaces"],
        },
    },
    {
        "name": "create_association",
        "description": (
            "Add a cds.Association element to an existing deployed view (SV_ or GV_) "
            "so it can navigate to a master data view. Fetches the source view CSN from "
            "Datasphere automatically — no need to supply the raw CSN. "
            "Returns a dry-run by default; set deploy=true to apply."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_view": {
                    "type": "string",
                    "description": "View to extend (e.g. SV_BILLING_DOC_JOINED).",
                },
                "target_view": {
                    "type": "string",
                    "description": "Association target view (e.g. SV_COMPANYCODE).",
                },
                "join_field_source": {
                    "type": "string",
                    "description": "Foreign key column on the source view (e.g. CompanyCode).",
                },
                "join_field_target": {
                    "type": "string",
                    "description": "Primary key column on the target view (e.g. CompanyCode).",
                },
                "space_id": {
                    "type": "string",
                    "description": "Datasphere space containing both views.",
                    "default": "ZZ_BDC_HARNESS_1",
                },
                "deploy": {
                    "type": "boolean",
                    "description": "Set true to deploy after dry-run review. Requires confirm and acknowledge_ai.",
                    "default": False,
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Human confirmation flag. Must be true when deploy=true.",
                    "default": False,
                },
                "acknowledge_ai": {
                    "type": "boolean",
                    "description": "AI literacy acknowledgement. Must be true when deploy=true.",
                    "default": False,
                },
            },
            "required": ["source_view", "target_view", "join_field_source", "join_field_target"],
        },
    },
    {
        "name": "create_sql_view_with_association",
        "description": (
            "Skill 3: Create a SQL View (SV_) that INNER JOINs Billing Document Item "
            "(VR1_BILLING_DOC_ITEM_TD_001) and Billing Document Header (VR1_BILLING_DOC_TD_001) "
            "on BillingDocument, and defines a cds.Association on CompanyCode linking to "
            "TL_COMPANYCODE master data. Returns a CSN dry-run by default. "
            "Set deploy=true to create in Datasphere."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "view_name": {
                    "type": "string",
                    "description": "Technical name for the SQL view (must start with SV_).",
                    "default": "SV_BILLING_DOC_JOINED",
                },
                "source_table_1": {
                    "type": "string",
                    "description": "First source table (Billing Document Item).",
                    "default": "VR1_BILLING_DOC_ITEM_TD_001",
                },
                "source_table_2": {
                    "type": "string",
                    "description": "Second source table (Billing Document Header).",
                    "default": "VR1_BILLING_DOC_TD_001",
                },
                "join_field": {
                    "type": "string",
                    "description": "Column used for the INNER JOIN between the two tables.",
                    "default": "BillingDocument",
                },
                "association_field": {
                    "type": "string",
                    "description": "Column used as the cds.Association key (many-to-one).",
                    "default": "CompanyCode",
                },
                "master_data_view": {
                    "type": "string",
                    "description": "Association target view (SV_ or GV_ view).",
                    "default": "SV_COMPANYCODE",
                },
                "master_data_key": {
                    "type": "string",
                    "description": "Primary key field inside master_data_view (defaults to association_field if not set).",
                    "default": "Company_Code",
                },
                "space_id": {
                    "type": "string",
                    "description": "Datasphere space ID.",
                    "default": "ZZ_BDC_HARNESS_1",
                },
                "deploy": {
                    "type": "boolean",
                    "description": "Set true to deploy after dry-run review. Requires confirm and acknowledge_ai.",
                    "default": False,
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Human confirmation flag. Must be true when deploy=true.",
                    "default": False,
                },
                "acknowledge_ai": {
                    "type": "boolean",
                    "description": "AI literacy acknowledgement. Must be true when deploy=true.",
                    "default": False,
                },
            },
            "required": [],
        },
    },
    {
        "name": "add_columns",
        "description": (
            "Skill 5: Add calculated and/or restricted columns to any SQL view (SV_) in SAP Datasphere. "
            "Calculated columns: arithmetic or CASE-with-ELSE expressions (e.g. NetAmount + TaxAmount). "
            "Restricted columns: CASE-WHEN without ELSE — result is NULL when condition not met. "
            "Accepts any view name, any column names, and any SQL expressions supplied by the user. "
            "Reads the live CSN, injects xpr definitions, and deploys. Dry-run by default."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "view_name": {
                    "type": "string",
                    "description": "Technical name of the SQL view to extend (must start with SV_).",
                    "default": "SV_BILLING_DOC_JOINED",
                },
                "space_id": {
                    "type": "string",
                    "description": "Datasphere space ID. Available: ZZ_BDC_HARNESS_1, ZZ_BDC_HARNESS_2.",
                    "default": "ZZ_BDC_HARNESS_1",
                },
                "columns": {
                    "type": "array",
                    "description": (
                        "List of columns to add. Each item defines one column. "
                        "column_type='calculated' for arithmetic/CASE-ELSE. "
                        "column_type='restricted' for CASE-WHEN without ELSE."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Column technical name (e.g. GrossAmount, InvoiceRevenue).",
                            },
                            "label": {
                                "type": "string",
                                "description": "Human-readable label shown in Datasphere UI.",
                            },
                            "column_type": {
                                "type": "string",
                                "enum": ["calculated", "restricted"],
                                "description": "calculated = arithmetic/CASE with ELSE. restricted = CASE WHEN without ELSE.",
                            },
                            "data_type": {
                                "type": "string",
                                "description": "CDS type: cds.Decimal, cds.String, cds.Integer, etc.",
                                "default": "cds.Decimal",
                            },
                            "precision": {
                                "type": "integer",
                                "description": "Precision for cds.Decimal columns.",
                                "default": 34,
                            },
                            "scale": {
                                "type": "integer",
                                "description": "Scale for cds.Decimal columns.",
                                "default": 4,
                            },
                            "length": {
                                "type": "integer",
                                "description": "Length for cds.String columns.",
                            },
                            "expression": {
                                "type": "string",
                                "description": (
                                    "SQL expression string. "
                                    "Arithmetic: 'NetAmount + TaxAmount'. "
                                    "CASE: 'CASE WHEN BillingDocumentType = \'F2\' THEN NetAmount END'."
                                ),
                            },
                        },
                        "required": ["name", "expression", "column_type"],
                    },
                },
                "deploy": {
                    "type": "boolean",
                    "description": "Set true to deploy after dry-run review. Requires confirm and acknowledge_ai.",
                    "default": False,
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Human confirmation flag. Must be true when deploy=true.",
                    "default": False,
                },
                "acknowledge_ai": {
                    "type": "boolean",
                    "description": "AI literacy acknowledgement. Must be true when deploy=true.",
                    "default": False,
                },
            },
            "required": ["columns"],
        },
    },
    {
        "name": "create_backup",
        "description": (
            "Create a backup copy of an existing Datasphere view before modification. "
            "Reads the original view from Datasphere, generates a timestamped backup name, "
            "and persists the backup as a new view in the same space. "
            "Fails if the original does not exist or a backup with the same timestamp already exists."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_name": {
                    "type": "string",
                    "description": "Technical name of the existing view to back up (e.g. SV_SALES or SV_SALES_VIEW).",
                },
                "space_id": {
                    "type": "string",
                    "description": "Datasphere space containing the view (default: ZZ_BDC_HARNESS_1).",
                    "default": "ZZ_BDC_HARNESS_1",
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Human confirmation flag. Must be true to execute mutating actions.",
                    "default": False,
                },
                "acknowledge_ai": {
                    "type": "boolean",
                    "description": "AI literacy acknowledgement. Must be true to confirm review of AI-generated output before execution.",
                    "default": False,
                },
            },
            "required": ["object_name"],
        },
    },
    {
        "name": "create_transformation_flow",
        "description": (
            "Skill 6: Create a Transformation Flow (TF_) and target Local Table (TL_) "
            "in SAP Datasphere. Reads a source SQL view, excludes granular key columns "
            "(BillingDocument, BillingDocumentItem by default), groups by dimension columns "
            "(String/Date) and aggregates measure columns (Decimal/Integer) via SUM. "
            "Dry-run by default. Set deploy=true to create both objects in Datasphere."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_view": {
                    "type": "string",
                    "description": "SQL view to aggregate (must start with SV_).",
                    "default": "SV_BILLING_DOC_JOINED",
                },
                "space_id": {
                    "type": "string",
                    "description": "Datasphere space ID. Available: ZZ_BDC_HARNESS_1, ZZ_BDC_HARNESS_2.",
                    "default": "ZZ_BDC_HARNESS_1",
                },
                "exclude_columns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Extra columns to exclude beyond BillingDocument and BillingDocumentItem.",
                },
                "tf_name": {
                    "type": "string",
                    "description": "Override TF technical name (default: TF_<source_base>).",
                },
                "tl_name": {
                    "type": "string",
                    "description": "Override TL technical name (default: TL_<source_base>_AGG).",
                },
                "deploy": {
                    "type": "boolean",
                    "description": "Set true to deploy. Requires confirm and acknowledge_ai.",
                    "default": False,
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Human confirmation flag. Must be true when deploy=true.",
                    "default": False,
                },
                "acknowledge_ai": {
                    "type": "boolean",
                    "description": "AI literacy acknowledgement. Must be true when deploy=true.",
                    "default": False,
                },
            },
            "required": [],
        },
    },
    {
        "name": "create_task_chain",
        "description": (
            "Skill 7: Create a Datasphere Task Chain (TC_) that executes an existing "
            "Transformation Flow (TF_). Generates a taskchains CSN with a START node and "
            "a TASK node (applicationId=TRANSFORMATION_FLOWS, activity=EXECUTE). "
            "TC name is derived as TC_<TF_NAME> for 1:1 traceability. "
            "Dry-run by default. Set deploy=true to create in Datasphere."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tf_name": {
                    "type": "string",
                    "description": "Technical name of the Transformation Flow to execute (must start with TF_).",
                },
                "space_id": {
                    "type": "string",
                    "description": "Datasphere space ID. Available: ZZ_BDC_HARNESS_1, ZZ_BDC_HARNESS_2.",
                    "default": "ZZ_BDC_HARNESS_1",
                },
                "tc_name": {
                    "type": "string",
                    "description": "Override the generated TC_ name (must start with TC_). Default: TC_<tf_name>.",
                },
                "folder": {
                    "type": "string",
                    "description": "Optional folder assignment for _meta.dependencies.folderAssignment.",
                },
                "deploy": {
                    "type": "boolean",
                    "description": "Set true to deploy. Requires confirm and acknowledge_ai.",
                    "default": False,
                },
                "run": {
                    "type": "boolean",
                    "description": "Set true to execute the Task Chain immediately after deploy. Requires deploy=true.",
                    "default": False,
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Human confirmation flag. Must be true when deploy=true.",
                    "default": False,
                },
                "acknowledge_ai": {
                    "type": "boolean",
                    "description": "AI literacy acknowledgement. Must be true when deploy=true.",
                    "default": False,
                },
            },
            "required": ["tf_name"],
        },
    },
]


def _handle_bronze_to_silver(arguments: dict) -> str:
    """Generate transformation SQL and execute live."""
    table_name = arguments.get("table_name", "UNKNOWN_TABLE").upper()
    source_layer = arguments.get("source_layer", "bronze")
    target_layer = arguments.get("target_layer", "silver")

    log.info("Generating SQL for %s: %s -> %s", table_name, source_layer, target_layer)
    sql = generate_sql(table_name, source_layer, target_layer)
    return sql


def _handle_read_view(arguments: dict) -> str:
    """Read a view definition from Datasphere."""
    view_name = arguments.get("view_name", "ADSO_Sales_Document_Item_Data_V")
    space_id = arguments.get("space_id", "ZZ_BDC_HARNESS_1")

    log.info("Reading view %s from space %s", view_name, space_id)
    return cli_read_view(space_id, view_name)


def _handle_list_spaces(arguments: dict) -> str:
    """List all spaces in Datasphere."""
    log.info("Listing spaces")
    return list_spaces()


def _handle_read_space(arguments: dict) -> str:
    """Read details of a specific space from Datasphere."""
    space_id = arguments.get("space_id", "ZZ_BDC_HARNESS_1")

    log.info("Reading space %s", space_id)
    return read_space(space_id)


def _handle_list_views(arguments: dict) -> str:
    """List all views in a space from Datasphere."""
    space_id = arguments.get("space_id", "ZZ_BDC_HARNESS_1")

    log.info("Listing views in space %s", space_id)
    return list_views(space_id)


def _handle_create_view(arguments: dict) -> str:
    """Create a view (Graphical or SQL) in Datasphere."""
    import json as _json

    view_name = arguments.get("view_name", "GV_NEW_VIEW").upper()
    business_name = arguments.get("business_name", view_name)
    view_type = arguments.get("view_type", "GV").upper()
    space_id = arguments.get("space_id", "ZZ_BDC_HARNESS_1")
    source_table = arguments.get("source_table")
    columns = arguments.get("columns")

    # If source_table is provided, read table and build columns
    if source_table:
        log.info("Reading source table %s to get columns...", source_table)
        table_def = cli_read_local_table(space_id, source_table)
        if table_def is None:
            return f"ERROR: Could not read table {source_table} in space {space_id}"
        source_elements = table_def["definitions"][source_table]["elements"]

        # If columns provided, use as name filter
        if columns:
            filter_names = {
                (c["name"] if isinstance(c, dict) else c).upper()
                for c in columns
            }
            source_elements = {
                k: v for k, v in source_elements.items()
                if k.upper() in filter_names
            }

        # Build full column defs from table metadata
        columns = []
        for col_name, col_def in source_elements.items():
            col = {"name": col_name, "type": col_def["type"]}
            if col_def.get("key"):
                col["key"] = True
            if "length" in col_def:
                col["length"] = col_def["length"]
            if "precision" in col_def:
                col["precision"] = col_def["precision"]
            if "scale" in col_def:
                col["scale"] = col_def["scale"]
            col["label"] = col_def.get("@EndUserText.label", col_name)
            columns.append(col)
    elif not columns:
        columns = [
            {"name": "ID", "type": "cds.Integer", "key": True, "label": "ID"},
            {"name": "NAME", "type": "cds.String", "length": 100, "label": "Name"},
        ]

    csn = generate_csn(view_name, columns, business_name, view_type=view_type)

    # If source_table provided, point query.from to source table instead of view itself
    if source_table:
        actual_name = _ensure_prefix(view_name, view_type=view_type)
        csn["definitions"][actual_name]["query"]["SELECT"]["from"] = {"ref": [source_table]}

    log.info("Creating %s view %s in space %s", view_type, view_name, space_id)
    temp_path = csn_to_temp_file(csn)
    try:
        return cli_create_view(space_id, temp_path)
    finally:
        import os
        os.unlink(temp_path)


def _handle_share_to_space(arguments: dict) -> str:
    """Share views to target spaces. Auto-deploys if view is not yet deployed."""
    import os

    view_names = arguments.get("view_names", [])
    target_spaces = arguments.get("target_spaces", [])
    source_space = arguments.get("source_space", "ZZ_BDC_HARNESS_1")

    if not view_names or not target_spaces:
        return "ERROR: view_names and target_spaces are required"

    results = []
    for vn in view_names:
        log.info("Sharing %s from %s to %s", vn, source_space, target_spaces)

        # 1. Read current view definition
        view_csn = cli_read_view_raw(source_space, vn)
        if view_csn is None:
            results.append(f"ERROR: Could not read view {vn} in space {source_space}")
            continue

        # 2. Add shareTo annotation
        updated_csn = build_share_csn(view_csn, target_spaces)

        # 3. Write to temp file
        temp_path = share_csn_to_temp_file(updated_csn)
        try:
            # 4. Try update + deploy (preferred path)
            output = cli_update_view(source_space, temp_path, vn)

            if "FAILED" not in output:
                results.append(f"Shared and deployed {vn} -> {target_spaces}: {output}")
            else:
                # 5. Deploy failed — fallback: save-only (no deploy)
                log.warning("Deploy failed for %s, falling back to save-only", vn)
                output_no_deploy = cli_update_view_no_deploy(source_space, temp_path, vn)

                if "FAILED" not in output_no_deploy:
                    results.append(
                        f"PARTIAL: {vn} share annotation saved but NOT deployed. "
                        f"Fix the view query and redeploy manually.\n{output_no_deploy}"
                    )
                else:
                    results.append(
                        f"ERROR: Could not share {vn}. Both deploy and save-only failed.\n"
                        f"Deploy attempt:\n{output}\n"
                        f"Save-only attempt:\n{output_no_deploy}"
                    )
        finally:
            os.unlink(temp_path)

    return "\n\n".join(results) if results else "No views processed."


def _handle_create_association(arguments: dict) -> str:
    """Add a cds.Association to an existing deployed view (dry-run by default)."""
    import json as _json
    from skills.create_association import execute as assoc_execute

    result = assoc_execute(arguments)

    if result["status"] == "error":
        errors = result.get("errors", ["Unknown error"])
        return "ERROR:\n" + "\n".join(f"  - {e}" for e in errors)

    if result["status"] == "dry_run":
        csn_pretty = _json.dumps(result["csn"], indent=2)
        return (
            f"DRY-RUN — association generated (not deployed)\n"
            f"Source view:      {result['source_view']}\n"
            f"Target view:      {result['target_view']}\n"
            f"Association name: {result['association_name']}\n"
            f"Space:            {result['space_id']}\n\n"
            f"CSN:\n{csn_pretty}\n\n"
            f"Next step: {result['next_step']}"
        )

    return (
        f"DEPLOYED\n"
        f"Source view:      {result['source_view']}\n"
        f"Target view:      {result['target_view']}\n"
        f"Association name: {result['association_name']}\n"
        f"Space:            {result['space_id']}\n"
        f"Output:           {result['cli_output']}"
    )


def _handle_create_backup(arguments: dict) -> str:
    """Create a backup copy of an existing view and persist it to Datasphere."""
    from skills.create_backup import execute as backup_execute

    object_name = arguments.get("object_name")
    if not object_name:
        return "ERROR: object_name is required"

    space_id = arguments.get("space_id", "ZZ_BDC_HARNESS_1")
    log.info("Creating backup for %s in space %s", object_name, space_id)

    result = backup_execute({"object_name": object_name, "space_id": space_id})

    if result.get("status") == "error":
        return f"ERROR: {result.get('message', 'Unknown error')}"

    return (
        f"Backup created successfully\n"
        f"Original: {result['original_name']}\n"
        f"Backup:   {result['backup_name']}\n"
        f"Space:    {result['space_id']}"
    )


def _handle_create_sql_view_with_association(arguments: dict) -> str:
    """Skill 3: INNER JOIN billing tables + cds.Association on CompanyCode (dry-run by default)."""
    import json as _json
    from skills.create_sql_view_with_association import execute as skill3_execute

    result = skill3_execute(arguments)

    if result["status"] == "error":
        errors = result.get("errors", ["Unknown error"])
        return "ERROR:\n" + "\n".join(f"  - {e}" for e in errors)

    if result["status"] == "dry_run":
        csn_pretty = _json.dumps(result["csn"], indent=2)
        return (
            f"DRY-RUN — CSN generated (not deployed)\n"
            f"View:              {result['view_name']}\n"
            f"Table 1:           {result['source_table_1']}\n"
            f"Table 2:           {result['source_table_2']}\n"
            f"Join field:        {result['join_field']}\n"
            f"Association field: {result['association_field']}\n"
            f"Master data view:  {result['master_data_view']}\n"
            f"Space:             {result['space_id']}\n\n"
            f"CSN:\n{csn_pretty}\n\n"
            f"Next step: {result['next_step']}"
        )

    # Deployed
    return (
        f"DEPLOYED\n"
        f"View:    {result['view_name']}\n"
        f"Space:   {result['space_id']}\n"
        f"Output:  {result['cli_output']}"
    )


def _handle_create_transformation_flow(arguments: dict) -> str:
    """Skill 6: Build aggregated TF_ + TL_ from a source SV_ view."""
    import json as _json
    from skills.create_transformation_flow import execute as tf_execute

    result = tf_execute(arguments)

    if result["status"] == "error":
        return "ERROR:\n" + "\n".join(f"  - {e}" for e in result.get("errors", []))

    if result["status"] == "dry_run":
        dims = result["dimensions"]
        meas = result["measures"]
        lines = [
            f"DRY-RUN: Transformation Flow for '{result['source_view']}'",
            f"  TF name : {result['tf_name']}",
            f"  TL name : {result['tl_name']}",
            f"  Excluded: {', '.join(result['excluded_columns'])}",
            f"  Dimensions ({len(dims)}): {', '.join(dims)}",
            f"  Measures  ({len(meas)}): {', '.join(meas)}",
            "",
            "--- Target Local Table CSN ---",
            _json.dumps(result["tl_csn"], indent=2),
            "",
            "--- Transformation Flow CSN ---",
            _json.dumps(result["tf_csn"], indent=2),
            "",
            result["next_step"],
        ]
        return "\n".join(lines)

    tl_r = result["results"].get("local_table", {})
    tf_r = result["results"].get("transformation_flow", {})
    return (
        f"Status: {result['status'].upper()}\n"
        f"  TL '{result['tl_name']}': {tl_r.get('status', '?')}\n"
        f"  TF '{result['tf_name']}': {tf_r.get('status', '?')}\n"
        f"  Dimensions: {len(result['dimensions'])}, Measures: {len(result['measures'])}"
    )


def _handle_add_columns(arguments: dict) -> str:
    """Skill 5: Add user-defined calculated/restricted columns to any SV_ view."""
    import json as _json
    from skills.add_columns import execute as skill5_execute

    result = skill5_execute(arguments)

    if result["status"] == "error":
        errors = result.get("errors", ["Unknown error"])
        return "ERROR:\n" + "\n".join(f"  - {e}" for e in errors)

    if result["status"] == "already_applied":
        return (
            f"ALREADY APPLIED\n"
            f"View:    {result['view_name']}\n"
            f"Space:   {result['space_id']}\n"
            f"Message: {result['message']}"
        )

    if result["status"] == "dry_run":
        csn_pretty = _json.dumps(result["csn"], indent=2)
        cols_added = result.get("columns_added", [])
        col_specs  = {c["name"]: c for c in arguments.get("columns", [])}
        col_lines  = ""
        for col_name in cols_added:
            spec  = col_specs.get(col_name, {})
            dtype = spec.get("data_type", "cds.Decimal")
            expr  = spec.get("expression", "")
            kind  = spec.get("column_type", "calculated")
            col_lines += f"  - {col_name} ({dtype}) [{kind}] = {expr}\n"
        return (
            f"DRY-RUN — columns generated (not deployed)\n"
            f"View:  {result['view_name']}\n"
            f"Space: {result['space_id']}\n\n"
            f"Columns to add:\n{col_lines}\n"
            f"CSN:\n{csn_pretty}\n\n"
            f"Next step: {result['next_step']}"
        )

    cols_added = result.get("columns_added", [])
    return (
        f"DEPLOYED\n"
        f"View:          {result['view_name']}\n"
        f"Space:         {result['space_id']}\n"
        f"Columns added: {', '.join(cols_added)}\n"
        f"Output:        {result['cli_output']}"
    )


def _handle_create_task_chain(arguments: dict) -> str:
    """Skill 7: Build and optionally deploy a Task Chain (TC_) wrapping a Transformation Flow (TF_)."""
    import json as _json
    from skills.create_task_chain import execute as tc_execute

    result = tc_execute(arguments)

    if result["status"] == "error":
        return "ERROR:\n" + "\n".join(f"  - {e}" for e in result.get("errors", []))

    if result["status"] == "dry_run":
        lines = [
            f"DRY-RUN: Task Chain for '{result['tf_name']}'",
            f"  TC name : {result['tc_name']}",
            f"  TF name : {result['tf_name']}",
            f"  Space   : {result['space_id']}",
            f"  Folder  : {result['folder'] or '(none)'}",
            "",
            "--- Task Chain CSN ---",
            _json.dumps(result["tc_csn"], indent=2),
            "",
            result["next_step"],
        ]
        return "\n".join(lines)

    if result["status"] == "deployed_and_running":
        tc_r = result["results"].get("task_chain", {})
        run_r = result["results"].get("run", {})
        return (
            f"Status: DEPLOYED AND RUNNING\n"
            f"  TC '{result['tc_name']}': deploy={tc_r.get('status', '?')}, run={run_r.get('status', '?')}\n"
            f"  TF '{result['tf_name']}' triggered\n"
            f"  Space: {result['space_id']}"
        )

    tc_r = result["results"].get("task_chain", {})
    return (
        f"Status: {result['status'].upper()}\n"
        f"  TC '{result['tc_name']}': {tc_r.get('status', '?')}\n"
        f"  TF '{result['tf_name']}' wrapped\n"
        f"  Space: {result['space_id']}"
    )


TOOL_HANDLERS = {
    "bronze_to_silver": _handle_bronze_to_silver,
    "read_view": _handle_read_view,
    "list_spaces": _handle_list_spaces,
    "read_space": _handle_read_space,
    "list_views": _handle_list_views,
    "create_view": _handle_create_view,
    "share_to_space": _handle_share_to_space,
    "create_association": _handle_create_association,
    "create_backup": _handle_create_backup,
    "create_sql_view_with_association": _handle_create_sql_view_with_association,
    "add_columns": _handle_add_columns,
    "create_transformation_flow": _handle_create_transformation_flow,
    "create_task_chain": _handle_create_task_chain,
}

# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------


def _ok(id: Any, result: Any) -> dict:
    """Build a successful JSON-RPC 2.0 response."""
    return {"jsonrpc": "2.0", "id": id, "result": result}


def _error(id: Any, code: int, message: str, data: Any = None) -> dict:
    """Build a JSON-RPC 2.0 error response."""
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": id, "error": err}


# Standard JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602

# ---------------------------------------------------------------------------
# Request dispatcher
# ---------------------------------------------------------------------------


def handle_request(msg: dict) -> dict | None:
    """
    Route a JSON-RPC request to the correct handler.
    Returns a response dict, or None for notifications (no id).
    """
    req_id = msg.get("id")
    method = msg.get("method", "")
    params = msg.get("params", {})

    log.debug("method=%s id=%s", method, req_id)

    # --- MCP lifecycle: initialize ---
    if method == "initialize":
        return _ok(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION,
            },
        })

    # --- MCP lifecycle: initialized (notification, no response) ---
    if method == "notifications/initialized":
        log.info("Client initialized.")
        return None

    # --- Tool discovery ---
    if method == "tools/list":
        return _ok(req_id, {"tools": TOOLS})

    # --- Tool invocation ---
    if method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        handler = TOOL_HANDLERS.get(tool_name)
        if handler is None:
            return _error(req_id, INVALID_PARAMS,
                          f"Unknown tool: '{tool_name}'")

        # Validate required params
        tool_def = next((t for t in TOOLS if t["name"] == tool_name), None)
        if tool_def:
            required = tool_def["inputSchema"].get("required", [])
            missing = [k for k in required if k not in arguments]
            if missing:
                return _error(req_id, INVALID_PARAMS,
                              f"Missing required parameters: {missing}")

        validation = validate_skill_call(tool_name, arguments)
        if not validation.get("allowed"):
            log_skill_action(
                skill_name=tool_name,
                params=arguments,
                validation=validation,
                output="Execution blocked by governance guard.",
                result="blocked",
            )
            return _error(
                req_id,
                INVALID_PARAMS,
                "Governance validation failed.",
                validation,
            )

        arguments = validation.get("normalized_arguments", arguments)

        try:
            text_result = handler(arguments)
        except Exception as exc:
            log.exception("Tool execution failed")
            log_skill_action(
                skill_name=tool_name,
                params=arguments,
                validation=validation,
                output=str(exc),
                result="failed",
            )
            return _error(req_id, -32000, f"Tool error: {exc}")

        execution_result = "failed" if str(text_result).startswith("ERROR:") else "success"
        log_skill_action(
            skill_name=tool_name,
            params=arguments,
            validation=validation,
            output=text_result,
            result=execution_result,
        )

        # MCP tools/call result format: list of content blocks
        return _ok(req_id, {
            "content": [{"type": "text", "text": text_result}],
        })

    # --- Ping (keep-alive) ---
    if method == "ping":
        return _ok(req_id, {})

    # --- Unknown method ---
    return _error(req_id, METHOD_NOT_FOUND,
                  f"Method not found: '{method}'")

# ---------------------------------------------------------------------------
# Main I/O loop – reads one JSON-RPC message per line from STDIN
# ---------------------------------------------------------------------------


def main() -> None:
    log.info("MCP server starting (stdio transport) – all operations run LIVE")

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue  # skip blank lines

        # Parse JSON
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            resp = _error(None, PARSE_ERROR, f"Invalid JSON: {exc}")
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
            continue

        # Basic JSON-RPC validation
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            resp = _error(msg.get("id"), INVALID_REQUEST,
                          "Missing or invalid 'jsonrpc' field.")
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
            continue

        # Dispatch
        resp = handle_request(msg)

        # Notifications (no id) get no response
        if resp is None:
            continue

        sys.stdout.write(json.dumps(resp) + "\n")
        sys.stdout.flush()

    log.info("STDIN closed – MCP server shutting down.")


if __name__ == "__main__":
    main()
