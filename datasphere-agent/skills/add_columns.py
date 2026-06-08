"""Skill 5: add_columns

Generic engine to add calculated and restricted columns to an existing SQL
view (SV_) in SAP Datasphere.

Column types:
  - calculated : arithmetic or CASE-with-ELSE expression
  - restricted : CASE-WHEN-without-ELSE (implicit NULL = restricted measure)

Expressions are supplied as SQL strings by the caller (GitHub Copilot translates
the user's natural language into the structured column specs). This module parses
the expression strings into CSN xpr lists and resolves column refs against the
live view's SELECT list so that table-qualified refs are preserved exactly.

Defaults to a dry-run. Set deploy=True (plus confirm=True, acknowledge_ai=True)
to push the updated CSN to Datasphere.

Governance is enforced at the MCP handler layer via governance_guard.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from typing import Any

from agent.skill_registry import register_skill

log = logging.getLogger("skill-5")

DEFAULT_VIEW_NAME = "SV_BILLING_DOC_JOINED"
DEFAULT_SPACE = "ZZ_BDC_HARNESS_1"

# ---------------------------------------------------------------------------
# Ref-map builder
# ---------------------------------------------------------------------------

def _build_qualified_ref_map(columns: list) -> dict[str, list]:
    """Scan SELECT.columns and map column name (uppercase) -> ref list.

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
            ref_map[ref[1].upper()] = ref
        elif len(ref) == 1:
            ref_map[ref[0].upper()] = ref
    return ref_map


# ---------------------------------------------------------------------------
# Expression tokeniser
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(
    r"'[^']*'"            # single-quoted string literal
    r"|\d+(?:\.\d+)?"    # numeric literal
    r"|[A-Za-z_]\w*"     # identifier (field name or keyword)
    r"|[+\-*/=<>!]+"     # operators
    r"|\S",              # any other single non-whitespace char
    re.IGNORECASE,
)

_KEYWORDS = {"CASE", "WHEN", "THEN", "ELSE", "END", "AND", "OR", "NOT"}


def _tokenise(expr: str) -> list[str]:
    return _TOKEN_RE.findall(expr)


def _is_numeric(token: str) -> bool:
    try:
        float(token)
        return True
    except ValueError:
        return False


def _is_string_literal(token: str) -> bool:
    return token.startswith("'") and token.endswith("'")


def _make_val(token: str) -> dict:
    """Convert a literal token to a CSN val node."""
    if _is_string_literal(token):
        return {"val": token[1:-1]}
    if _is_numeric(token):
        return {"val": float(token) if "." in token else int(token)}
    return {"val": token}


def _resolve_ref(name: str, ref_map: dict[str, list]) -> dict:
    """Return a CSN ref node, using table-qualified form when available."""
    qualified = ref_map.get(name.upper())
    if qualified:
        return {"ref": qualified}
    return {"ref": [name]}


# ---------------------------------------------------------------------------
# Expression -> CSN xpr parser
# ---------------------------------------------------------------------------

def _parse_case(tokens: list[str], pos: int, ref_map: dict) -> tuple[list, int]:
    """Parse CASE WHEN ... THEN ... [WHEN ... THEN ...] [ELSE ...] END.

    pos should point to the token *after* CASE.
    Returns (xpr_list, new_pos).
    """
    xpr: list[Any] = ["case"]
    while pos < len(tokens):
        tok = tokens[pos].upper()
        if tok == "WHEN":
            xpr.append("when")
            pos += 1
            # Collect all condition tokens until THEN (respecting parenthesis depth)
            cond_toks: list[str] = []
            depth = 0
            while pos < len(tokens):
                t = tokens[pos]
                if t == "(":
                    depth += 1
                    cond_toks.append(t)
                    pos += 1
                elif t == ")":
                    depth -= 1
                    cond_toks.append(t)
                    pos += 1
                elif t.upper() == "THEN" and depth == 0:
                    break
                else:
                    cond_toks.append(t)
                    pos += 1
            # Find the outermost comparison operator and split the condition
            _CMP_OPS = {">=", "<=", "<>", "!=", ">", "<", "="}
            split_at = -1
            d = 0
            for ci, ct in enumerate(cond_toks):
                if ct == "(": d += 1
                elif ct == ")": d -= 1
                elif d == 0 and ct in _CMP_OPS:
                    split_at = ci
                    break
            if split_at >= 0:
                xpr.extend(_parse_arithmetic(cond_toks[:split_at], ref_map))
                xpr.append(cond_toks[split_at])
                xpr.extend(_parse_arithmetic(cond_toks[split_at + 1:], ref_map))
            else:
                xpr.extend(_parse_arithmetic(cond_toks, ref_map))
        elif tok == "THEN":
            xpr.append("then")
            pos += 1
            val_tok = tokens[pos]; pos += 1
            if _is_string_literal(val_tok) or _is_numeric(val_tok):
                xpr.append(_make_val(val_tok))
            else:
                xpr.append(_resolve_ref(val_tok, ref_map))
        elif tok == "ELSE":
            xpr.append("else")
            pos += 1
            val_tok = tokens[pos]; pos += 1
            if _is_string_literal(val_tok) or _is_numeric(val_tok):
                xpr.append(_make_val(val_tok))
            else:
                xpr.append(_resolve_ref(val_tok, ref_map))
        elif tok == "END":
            xpr.append("end")
            pos += 1
            break
        else:
            pos += 1
    return xpr, pos


def _apply_safe_division(xpr: list) -> list:
    """Wrap column refs following '/' in NULLIF(ref, 0) to guard against division by zero."""
    result: list[Any] = []
    i = 0
    while i < len(xpr):
        item = xpr[i]
        if (
            item == "/"
            and i + 1 < len(xpr)
            and isinstance(xpr[i + 1], dict)
            and "ref" in xpr[i + 1]
        ):
            result.append("/")
            result.append({"func": "NULLIF", "args": [xpr[i + 1], {"val": 0}]})
            i += 2
        else:
            result.append(item)
            i += 1
    return result


def _parse_arithmetic(tokens: list[str], ref_map: dict) -> list:
    """Parse a compound arithmetic expression including parentheses and function calls."""
    xpr: list[Any] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in {"+", "-", "*", "/"}:
            xpr.append(tok)
            i += 1
        elif tok in {"(", ")"}:
            xpr.append(tok)
            i += 1
        elif _is_string_literal(tok) or _is_numeric(tok):
            xpr.append(_make_val(tok))
            i += 1
        elif tok.upper() not in _KEYWORDS:
            if i + 1 < len(tokens) and tokens[i + 1] == "(":
                func_name = tok.upper()
                i += 2
                raw_args: list[list[str]] = []
                current: list[str] = []
                depth = 1
                while i < len(tokens):
                    t = tokens[i]
                    i += 1
                    if t == "(":
                        depth += 1
                        current.append(t)
                    elif t == ")":
                        depth -= 1
                        if depth == 0:
                            raw_args.append(current)
                            break
                        else:
                            current.append(t)
                    elif t == "," and depth == 1:
                        raw_args.append(current)
                        current = []
                    else:
                        current.append(t)
                csn_args: list[Any] = []
                for arg_toks in raw_args:
                    parsed = _parse_arithmetic(arg_toks, ref_map)
                    csn_args.append(parsed[0] if len(parsed) == 1 else parsed)
                xpr.append({"func": func_name, "args": csn_args})
            else:
                xpr.append(_resolve_ref(tok, ref_map))
                i += 1
        else:
            i += 1
    return _apply_safe_division(xpr)


def expression_to_csn_xpr(expr: str, ref_map: dict, col_name: str) -> dict:
    """Convert a SQL expression string to a CSN xpr column dict.

    Handles:
      - Arithmetic:  'NetAmount + TaxAmount'
      - CASE WHEN:   'CASE WHEN field op val THEN result [ELSE default] END'

    Returns a CSN column dict with 'xpr' and 'as' keys.
    """
    tokens = _tokenise(expr.strip())
    if not tokens:
        raise ValueError(f"Empty expression for column '{col_name}'")

    if tokens[0].upper() == "CASE":
        xpr, _ = _parse_case(tokens, 1, ref_map)
    else:
        xpr = _parse_arithmetic(tokens, ref_map)

    if not xpr:
        raise ValueError(
            f"Could not parse expression for column '{col_name}': {expr!r}"
        )

    return {"xpr": xpr, "as": col_name}


# ---------------------------------------------------------------------------
# SQL-string patcher  (for @DataWarehouse.sqlEditor.query)
# ---------------------------------------------------------------------------

def _build_sql_expr(expr: str, ref_map: dict) -> str:
    """Qualify bare field names in an expression string using ref_map."""
    # Step 1: Protect single-quoted string literals so their contents are not touched.
    # Placeholders are \x00<index>\x00 — pure digits, so they never match [A-Za-z_]\w*.
    literals: list[str] = []

    def _save_literal(m: re.Match) -> str:
        literals.append(m.group(0))
        return f"\x00{len(literals) - 1}\x00"

    protected = re.sub(r"'[^']*'", _save_literal, expr)

    def _qualify(match: re.Match) -> str:
        name = match.group(0)
        if name.upper() in _KEYWORDS:
            return name
        ref = ref_map.get(name.upper())
        if ref and len(ref) == 2:
            return f'"{ref[0]}"."{ref[1]}"'
        if ref and len(ref) == 1:
            return f'"{ref[0]}"'
        return f'"{name}"'

    # Step 2: Qualify identifiers. Skip function calls (followed immediately by '(').
    # Using (?!\() instead of (?!\s*\() so that keywords like WHEN followed by ' ('
    # are matched in full and passed to _qualify, where they are returned unchanged.
    qualified = re.sub(r"[A-Za-z_]\w*(?!\()", _qualify, protected)

    # Step 3: Wrap column refs after '/' in NULLIF(..., 0) to guard against division by zero.
    qualified = re.sub(
        r'/\s*("(?:[^"]+)"(?:\."(?:[^"]+)")?)',
        r'/ NULLIF(\1, 0)',
        qualified,
    )

    # Step 4: Restore string literals.
    for i, lit in enumerate(literals):
        qualified = qualified.replace(f"\x00{i}\x00", lit)

    return qualified


def _patch_sql_with_columns(sql: str, col_specs: list[dict]) -> str:
    """Inject new column SQL expressions into the sqlEditor.query string.

    col_specs: list of {name, sql_expr} dicts for columns to add.
    Idempotent: skips any column whose name already appears in the SQL.
    """
    from_idx = sql.find("\nFROM ")
    if from_idx == -1:
        log.warning("\\nFROM not found in sqlEditor.query; SQL annotation not patched")
        return sql

    additions = ""
    for spec in col_specs:
        if spec["name"] not in sql:
            additions += f',\n  {spec["sql_expr"]} AS "{spec["name"]}"'

    if not additions:
        return sql
    return sql[:from_idx] + additions + sql[from_idx:]


# ---------------------------------------------------------------------------
# CSN elements type builder
# ---------------------------------------------------------------------------

def _build_element_def(col: dict) -> dict:
    """Build the CSN elements entry for a column spec."""
    dt    = col.get("data_type", "cds.Decimal")
    label = col.get("label", col["name"])
    elem: dict[str, Any] = {"type": dt, "@EndUserText.label": label}
    if dt == "cds.Decimal":
        elem["precision"] = col.get("precision", 34)
        elem["scale"]     = col.get("scale", 4)
    elif dt == "cds.String" and "length" in col:
        elem["length"] = col["length"]
    return elem


# ---------------------------------------------------------------------------
# Core injector (public — used by mcp_server and tests)
# ---------------------------------------------------------------------------

def inject_columns(existing_csn: dict, view_name: str, col_specs: list[dict]) -> dict:
    """Inject user-defined calculated/restricted columns into existing_csn in-place.

    Args:
        existing_csn:  Parsed CSN dict fetched from Datasphere.
        view_name:     Technical name of the view.
        col_specs:     List of column dicts from the MCP tool input.

    Returns:
        The mutated existing_csn dict.
    """
    definitions = existing_csn.get("definitions", {})
    if view_name not in definitions:
        raise ValueError(
            f"View '{view_name}' not found in CSN definitions. "
            f"Available: {list(definitions.keys())}"
        )

    view_def = definitions[view_name]
    elements: dict = view_def.setdefault("elements", {})
    select: dict   = view_def.setdefault("query", {}).setdefault("SELECT", {})
    columns: list  = select.setdefault("columns", [])

    ref_map = _build_qualified_ref_map(columns)
    sql_patches: list[dict] = []

    for col in col_specs:
        col_name = col["name"]
        if col_name in elements:
            log.debug("Column '%s' already exists — skipping", col_name)
            continue

        xpr_col = expression_to_csn_xpr(col["expression"], ref_map, col_name)
        columns.append(xpr_col)
        elements[col_name] = _build_element_def(col)
        log.debug("Injected column '%s' (%s)", col_name, col.get("column_type", "?"))

        sql_expr = _build_sql_expr(col["expression"], ref_map)
        sql_patches.append({"name": col_name, "sql_expr": sql_expr})

    sql_key = "@DataWarehouse.sqlEditor.query"
    if sql_key in view_def and sql_patches:
        view_def[sql_key] = _patch_sql_with_columns(view_def[sql_key], sql_patches)

    return existing_csn


# ---------------------------------------------------------------------------
# Skill entry point
# ---------------------------------------------------------------------------


def execute(params: dict) -> dict:
    """Add user-defined calculated or restricted columns to an existing SV_ view.

    Params:
        view_name       Technical name of the SQL view (default: SV_BILLING_DOC_JOINED).
        space_id        Datasphere space (default: ZZ_BDC_HARNESS_1).
        columns         List of column specs: {name, expression, column_type,
                        data_type, label, precision?, scale?, length?}
        deploy          Deploy the updated view (default: False -> dry-run).
        confirm         Governance: human sign-off (required when deploy=True).
        acknowledge_ai  Governance: AI literacy ack (required when deploy=True).
    """
    from executors.datasphere_cli import read_view_raw as cli_read_view_raw
    from executors.datasphere_cli import update_view as cli_update_view
    from executors.datasphere_cli import update_view_no_deploy as cli_update_view_no_deploy

    view_name = params.get("view_name", DEFAULT_VIEW_NAME).upper().strip()
    space_id  = params.get("space_id", DEFAULT_SPACE)
    deploy    = params.get("deploy", False) is True
    col_specs = params.get("columns", [])

    # -----------------------------------------------------------------------
    # Input validation
    # -----------------------------------------------------------------------
    errors: list[str] = []
    if not view_name.startswith("SV_"):
        errors.append(
            f"Naming rule violation: view name must start with 'SV_'. Got: '{view_name}'"
        )
    if not col_specs:
        errors.append("No columns specified. Provide at least one entry in 'columns'.")
    for col in col_specs:
        if not col.get("name"):
            errors.append("Each column must have a 'name'.")
        if not col.get("expression"):
            errors.append(f"Column '{col.get('name', '?')}' is missing an 'expression'.")
        if col.get("column_type") not in ("calculated", "restricted"):
            errors.append(
                f"Column '{col.get('name', '?')}' has invalid column_type "
                f"'{col.get('column_type')}'. Must be 'calculated' or 'restricted'."
            )
    if deploy:
        if params.get("confirm") is not True:
            errors.append("Human confirmation required: set confirm=true.")
        if params.get("acknowledge_ai") is not True:
            errors.append("AI literacy acknowledgement required: set acknowledge_ai=true.")
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
    # Idempotency check — skip columns already present
    # -----------------------------------------------------------------------
    existing_elements = (
        existing_csn.get("definitions", {})
        .get(view_name, {})
        .get("elements", {})
    )
    new_cols = [c for c in col_specs if c["name"] not in existing_elements]
    if not new_cols:
        names = [c["name"] for c in col_specs]
        return {
            "status": "already_applied",
            "view_name": view_name,
            "space_id": space_id,
            "message": (
                f"All requested columns {names} already exist in the view. "
                "No changes needed."
            ),
        }

    # -----------------------------------------------------------------------
    # Inject columns into CSN
    # -----------------------------------------------------------------------
    try:
        updated_csn = inject_columns(existing_csn, view_name, new_cols)
    except ValueError as exc:
        return {"status": "error", "errors": [str(exc)]}

    if not deploy:
        return {
            "status": "dry_run",
            "view_name": view_name,
            "space_id": space_id,
            "columns_added": [c["name"] for c in new_cols],
            "csn": updated_csn,
            "next_step": (
                "Dry-run only. Set deploy=true + confirm=true + acknowledge_ai=true to deploy."
            ),
        }

    # -----------------------------------------------------------------------
    # Deploy
    # -----------------------------------------------------------------------
    fd, temp_path = tempfile.mkstemp(suffix=".json", prefix="add_columns_csn_")
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
        "columns_added": [c["name"] for c in new_cols],
        "cli_output": cli_output,
    }


register_skill("add_columns", execute)
