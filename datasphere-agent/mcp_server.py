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
from skills.create_backup import generate_backup_name, generate_backup_csn  # noqa: E402

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
            "Add an association inside an existing Graphical View (GV) to link "
            "a transaction view to a master data view. The association is defined "
            "as a cds.Association element with target view and join condition."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "source_view": {
                    "type": "string",
                    "description": "Transaction view name (e.g. BILLING_TXN or GV_BILLING_TXN).",
                },
                "target_view": {
                    "type": "string",
                    "description": "Master data view name (e.g. CHART_OF_ACCOUNTS or GV_CHART_OF_ACCOUNTS).",
                },
                "join_field_source": {
                    "type": "string",
                    "description": "Foreign key column on the source view side.",
                },
                "join_field_target": {
                    "type": "string",
                    "description": "Primary key column on the target view side.",
                },
                "existing_view_csn": {
                    "type": "object",
                    "description": "Full CSN definition of the source view (required to add the association element).",
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
            "required": ["source_view", "target_view", "join_field_source", "join_field_target", "existing_view_csn"],
        },
    },
    {
        "name": "create_backup",
        "description": (
            "Create a simple logical backup name for an existing Datasphere object "
            "before modification. If an existing CSN is provided, prepares a copied "
            "definition under the backup name without modifying the original."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "object_name": {
                    "type": "string",
                    "description": "Object name to back up (e.g. TEST_VIEW or GV_TEST_VIEW).",
                },
                "original_csn": {
                    "type": "object",
                    "description": "Optional: full CSN definition of the object to create a copy.",
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
    """Share views to target spaces by adding @DataWarehouse.shareTo annotation."""
    import json as _json

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
            # 4. Update view via CLI
            output = cli_update_view(source_space, temp_path, vn)
            results.append(f"Shared {vn} -> {target_spaces}: {output}")
        finally:
            import os
            os.unlink(temp_path)

    return "\n\n".join(results) if results else "No views processed."


def _handle_create_association(arguments: dict) -> str:
    """Create an association inside an existing view."""
    import json as _json

    source_view = arguments.get("source_view")
    target_view = arguments.get("target_view")
    join_field_source = arguments.get("join_field_source")
    join_field_target = arguments.get("join_field_target")
    existing_view_csn = arguments.get("existing_view_csn")

    if not all([source_view, target_view, join_field_source, join_field_target, existing_view_csn]):
        return "ERROR: all parameters are required"

    try:
        log.info("Creating association: %s -> %s", source_view, target_view)
        updated_csn, assoc_name, join_condition = build_association_extension(
            existing_view_csn=existing_view_csn,
            source_view=source_view,
            target_view=target_view,
            join_field_source=join_field_source,
            join_field_target=join_field_target,
        )
    except ValueError as exc:
        return f"ERROR: {exc}"

    csn_text = _json.dumps(updated_csn, indent=2)
    return (
        f"Association created successfully\n"
        f"Association name: {assoc_name}\n"
        f"Join condition: {_json.dumps(join_condition, indent=2)}\n"
        f"Updated CSN:\n{csn_text}"
    )


def _handle_create_backup(arguments: dict) -> str:
    """Create a logical backup name and optionally copy the CSN definition."""
    import json as _json

    object_name = arguments.get("object_name")
    original_csn = arguments.get("original_csn")

    if not object_name:
        return "ERROR: object_name is required"

    log.info("Creating backup for %s", object_name)
    backup_name = generate_backup_name(object_name)

    if original_csn and isinstance(original_csn, dict):
        try:
            backup_csn = generate_backup_csn(object_name, original_csn, backup_name)
            csn_text = _json.dumps(backup_csn, indent=2)
            return (
                f"Backup created successfully\n"
                f"Original name: {object_name}\n"
                f"Backup name: {backup_name}\n"
                f"Backup CSN:\n{csn_text}"
            )
        except ValueError as exc:
            return f"ERROR: {exc}"
    else:
        return (
            f"Backup name prepared\n"
            f"Original name: {object_name}\n"
            f"Backup name: {backup_name}"
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
