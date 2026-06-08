"""Skill 6: create_transformation_flow

Generic Datasphere Transformation Engine.

Creates a Transformation Flow (TF_) that loads data from a source SQL view (SV_)
into a target Local Table (TL_).  Two modes are supported:

  "simple"      - 1-to-1 copy: all columns selected, no GROUP BY or aggregation.
  "aggregated"  - GROUP BY all dimension columns (String/Date/Timestamp),
                  SUM all measure columns (Decimal/Integer variants).

Two Datasphere objects are generated and optionally deployed:
  TL_<base>      - Local Table (target) for simple mode
  TL_<base>_AGG  - Local Table (target) for aggregated mode
  TF_<base>      - Transformation Flow (source view -> local table, FULL load)

Both objects follow project naming conventions (TL_ / TF_ prefixes).
All inputs come from params -- no business-specific defaults are embedded here.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import urllib.request
import urllib.error
from typing import Any

from agent.skill_registry import register_skill

log = logging.getLogger("skill-6")

# CDS types classified as numeric measures -> SUM aggregation in "aggregated" mode
MEASURE_TYPES: frozenset[str] = frozenset({
    "cds.Decimal",
    "cds.Integer",
    "cds.Int32",
    "cds.Int64",
    "cds.Double",
})


# ---------------------------------------------------------------------------
# Column classification
# ---------------------------------------------------------------------------

def classify_columns(
    elements: dict[str, Any],
    exclude: frozenset[str],
) -> tuple[list[dict], list[dict]]:
    """Split view elements into (dimensions, measures), skipping excluded columns.

    Decimal / Integer types -> measures (SUM in aggregated mode).
    Everything else          -> dimensions (GROUP BY in aggregated mode).

    Each returned dict has keys: name, type, label, and optionally
    precision / scale / length.

    Public -- used by tests and the MCP server handler.
    """
    dimensions: list[dict] = []
    measures: list[dict] = []

    for name, defn in elements.items():
        if name.upper() in exclude:
            log.debug("Excluding column: %s", name)
            continue

        col_type = defn.get("type", "cds.String")
        col: dict[str, Any] = {
            "name": name,
            "type": col_type,
            "label": defn.get("@EndUserText.label", name),
            "key": defn.get("key", False),
        }
        for attr in ("precision", "scale", "length"):
            if attr in defn:
                col[attr] = defn[attr]

        if col_type in MEASURE_TYPES:
            measures.append(col)
        else:
            dimensions.append(col)

    return dimensions, measures


# ---------------------------------------------------------------------------
# Local Table CSN builder
# ---------------------------------------------------------------------------

def build_local_table_csn(
    tl_name: str,
    dimensions: list[dict],
    measures: list[dict],
    mode: str,
    key_columns: frozenset[str] | None = None,
) -> dict:
    """Build the CSN definition for the target Local Table (TL_).

    aggregated mode: all dimension columns become composite keys; measures non-key.
    simple mode:     key_columns (if given) > source view keys > first column.

    Public -- used by tests and the MCP server handler.
    """
    elements: dict[str, Any] = {}

    if mode == "aggregated":
        for col in dimensions:
            elem: dict[str, Any] = {
                "type": col["type"],
                "key": True,
                "@EndUserText.label": col["label"],
            }
            if "length" in col:
                elem["length"] = col["length"]
            elements[col["name"]] = elem

        for col in measures:
            elem = {"type": col["type"], "@EndUserText.label": col["label"]}
            for attr in ("precision", "scale"):
                if attr in col:
                    elem[attr] = col[attr]
            elements[col["name"]] = elem

    else:  # simple: 1-to-1 copy
        all_cols = dimensions + measures
        # Determine effective key set: explicit override > source view keys > first column
        if key_columns:
            effective_keys: frozenset[str] = frozenset(c.upper() for c in key_columns)
        else:
            src_keys = frozenset(c["name"].upper() for c in all_cols if c.get("key"))
            effective_keys = src_keys if src_keys else (
                frozenset({all_cols[0]["name"].upper()}) if all_cols else frozenset()
            )
        for col in all_cols:
            elem = {"type": col["type"], "@EndUserText.label": col["label"]}
            if col["name"].upper() in effective_keys:
                elem["key"] = True
            for attr in ("precision", "scale", "length"):
                if attr in col:
                    elem[attr] = col[attr]
            elements[col["name"]] = elem

    return {
        "definitions": {
            tl_name: {
                "kind": "entity",
                "@EndUserText.label": tl_name.replace("_", " ").title(),
                "elements": elements,
            }
        }
    }


# ---------------------------------------------------------------------------
# SQL Transform node builder
# ---------------------------------------------------------------------------

def build_sql_transform(
    tf_name: str,
    source_view: str,
    dimensions: list[dict],
    measures: list[dict],
    mode: str,
) -> dict:
    """Build the sqltransform1 process node in the real Datasphere component format.

    simple mode:     plain unqualified ref for every column -- no GROUP BY.
    aggregated mode: unqualified refs for dimensions + SUM(ref) for measures + groupBy.

    Returns the full sqltransform1 component dict.
    Public -- used by tests and the MCP server handler.
    """
    all_cols = dimensions + measures

    # SQL string for the visual editor display
    col_sql = ",\n\t".join(f'"{c["name"]}"' for c in all_cols)
    sql_string = f'SELECT {col_sql}\nFROM "{source_view}"'

    # Inline elements for the sqltransform definition (mirrors source view structure)
    elements: dict[str, Any] = {}
    for col in all_cols:
        elem: dict[str, Any] = {
            "@EndUserText.label": col["label"],
            "type": col["type"],
        }
        if col.get("key"):
            elem["key"] = True
        for attr in ("precision", "scale", "length"):
            if attr in col:
                elem[attr] = col[attr]
        elements[col["name"]] = elem

    # Query columns -- unqualified refs (no table prefix)
    if mode == "aggregated":
        select_cols: list[Any] = [{"ref": [c["name"]]} for c in dimensions]
        select_cols += [
            {
                "xpr": [{"func": "SUM", "args": [{"ref": [c["name"]]}]}],
                "as": c["name"],
            }
            for c in measures
        ]
        group_by: list[Any] = [{"ref": [c["name"]]} for c in dimensions]
        query: dict[str, Any] = {
            "SELECT": {
                "from": {"ref": [source_view]},
                "columns": select_cols,
                "groupBy": group_by,
            }
        }
    else:
        select_cols = [{"ref": [c["name"]]} for c in all_cols]
        query = {
            "SELECT": {
                "from": {"ref": [source_view]},
                "columns": select_cols,
            }
        }

    return {
        "component": "com.sap.dwc.sqltransform",
        "metadata": {
            "label": "View Transform",
            "x": 0, "y": 12, "height": 40, "width": 120,
            "config": {
                "definition": {
                    "kind": "entity",
                    "elements": elements,
                    "query": query,
                    "@EndUserText.label": "View 1",
                    "@ObjectModel.modelingPattern": {"#": "DATA_STRUCTURE"},
                    "@ObjectModel.supportedCapabilities": [{"#": "DATA_STRUCTURE"}],
                    "@DataWarehouse.consumption.external": False,
                    "@DataWarehouse.sqlEditor.query": sql_string,
                },
                "version": {"csn": "1.0"},
                "meta": {"creator": "View Editor", "kind": "sap.dwc.viewmodel"},
                "$version": "1.0",
                "name": f"{tf_name}$TRF_TV_sqltransform1",
            },
        },
    }


# ---------------------------------------------------------------------------
# Target node builder
# ---------------------------------------------------------------------------

def build_target_node(
    tl_name: str,
    dimensions: list[dict],
    measures: list[dict],
    mode: str,
    key_columns: frozenset[str] | None = None,
) -> dict:
    """Build the target1 process node in the real Datasphere component format.

    Includes attribute mappings (1:1) and inline entity definition for the TL_.
    Public -- used by tests and the MCP server handler.
    """
    all_cols = dimensions + measures

    # Attribute mappings: 1:1 source -> target
    attr_mappings: list[dict] = [
        {"source": c["name"], "target": c["name"]} for c in all_cols
    ]

    # Inline elements for the target entity definition
    tl_elements: dict[str, Any] = {}
    if mode == "aggregated":
        for col in dimensions:
            elem: dict[str, Any] = {
                "@EndUserText.label": col["label"],
                "type": col["type"],
                "key": True,
            }
            if "length" in col:
                elem["length"] = col["length"]
            tl_elements[col["name"]] = elem
        for col in measures:
            elem = {
                "@EndUserText.label": col["label"],
                "type": col["type"],
                "key": False,
            }
            for attr in ("precision", "scale"):
                if attr in col:
                    elem[attr] = col[attr]
            tl_elements[col["name"]] = elem
    else:
        if key_columns:
            effective_keys: frozenset[str] = frozenset(c.upper() for c in key_columns)
        else:
            src_keys = frozenset(c["name"].upper() for c in all_cols if c.get("key"))
            effective_keys = src_keys if src_keys else (
                frozenset({all_cols[0]["name"].upper()}) if all_cols else frozenset()
            )
        for col in all_cols:
            elem = {
                "@EndUserText.label": col["label"],
                "type": col["type"],
                "key": col["name"].upper() in effective_keys,
            }
            for attr in ("precision", "scale", "length"):
                if attr in col:
                    elem[attr] = col[attr]
            tl_elements[col["name"]] = elem

    return {
        "component": "com.sap.dwc.target",
        "metadata": {
            "label": tl_name,
            "x": 200, "y": 12, "height": 40, "width": 120,
            "config": {
                "attributeMappings": attr_mappings,
                "definition": {
                    "elements": tl_elements,
                    "kind": "entity",
                    "@EndUserText.label": tl_name,
                    "@DataWarehouse.enclosingObject": tl_name,
                },
                "name": tl_name,
                "truncate": False,
            },
        },
    }


# ---------------------------------------------------------------------------
# Transformation Flow CSN builder
# ---------------------------------------------------------------------------

def build_transformation_flow_csn(
    tf_name: str,
    source_view: str,
    tl_name: str,
    dimensions: list[dict],
    measures: list[dict],
    mode: str,
    load_type: str = "FULL",
    key_columns: frozenset[str] | None = None,
) -> dict:
    """Build the full TF payload in the real Datasphere transformationflows format.

    Top-level key: "transformationflows"
    kind: "sap.dis.transformationflow"
    Load type is in contents.metadata.loadType.
    Processes use component-based format (com.sap.dwc.sqltransform / com.sap.dwc.target).
    Connections use src/tgt port-based wiring.

    Public -- used by tests and the MCP server handler.
    """
    sql_transform = build_sql_transform(tf_name, source_view, dimensions, measures, mode)
    target_node = build_target_node(tl_name, dimensions, measures, mode, key_columns)

    return {
        "transformationflows": {
            tf_name: {
                "kind": "sap.dis.transformationflow",
                "@EndUserText.label": tf_name.replace("_", " ").title(),
                "contents": {
                    "properties": {},
                    "metadata": {
                        "loadType": load_type,
                    },
                    "description": tf_name,
                    "processes": {
                        "sqltransform1": sql_transform,
                        "target1": target_node,
                    },
                    "groups": [],
                    "connections": [
                        {
                            "metadata": {"points": "125,32 195,32"},
                            "src": {"port": "outTable", "process": "sqltransform1"},
                            "tgt": {"port": "inTable", "process": "target1"},
                        }
                    ],
                    "inports": {},
                    "outports": {},
                    "parameters": {},
                },
            }
        }
    }


# ---------------------------------------------------------------------------
# Deploy helpers
# ---------------------------------------------------------------------------

def _deploy_transformation_flow_http(
    tf_name: str,
    space_id: str,
    tf_csn: dict,
    host: str,
    token: str,
    deploy: bool = True,
) -> dict:
    """Deploy a Transformation Flow via HTTP PUT.

    The CLI transformation-flows create (POST) cannot resolve the object name
    from the CSN body.  PUT to .../transformationflows/{technicalName} works.

    deploy=True  -> ?saveAnyway=true
    deploy=False -> ?saveAnyway=true&deploy=false
    """
    qs = "saveAnyway=true" if deploy else "saveAnyway=true&deploy=false"
    url = f"{host}/dwaas-core/api/v1/spaces/{space_id}/transformationflows/{tf_name}?{qs}"
    body = json.dumps(tf_csn).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="PUT",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            try:
                data = json.loads(raw)
            except Exception:
                data = {"raw": raw.decode(errors="replace")}
            return {"status": "success", "data": data}
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            err = json.loads(raw)
            msg = err.get("message", err.get("code", raw.decode(errors="replace")[:300]))
        except Exception:
            msg = raw.decode(errors="replace")[:300]
        return {"status": "error", "exit_code": exc.code, "error": msg}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _run_transformation_flow(
    tf_name: str,
    space_id: str,
    host: str,
    token: str,
) -> dict:
    """Attempt to trigger a Transformation Flow run via Task Chain runner.

    The dwaas-core API v1 does not expose a dedicated TF run endpoint.
    Falls back to the task-chains run path which may work if the TF is
    treated as a runnable object; otherwise returns a clear 'not_supported'
    status with UI instructions.
    """
    # Try the task-chains run path (discovery spec: POST /tasks/chains/{space}/run/{object})
    url = f"{host}/dwaas-core/api/v1/tasks/chains/{space_id}/run/{tf_name}"
    req = urllib.request.Request(
        url,
        data=b"{}",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            try:
                data = json.loads(raw)
            except Exception:
                data = {"raw": raw.decode(errors="replace")}
            return {"status": "success", "data": data}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return {
                "status": "not_supported",
                "message": (
                    f"The Datasphere API does not expose a programmatic run endpoint "
                    f"for Transformation Flows. To populate '{tf_name}', open the "
                    f"Datasphere UI → Data Integration → Transformation Flows → "
                    f"'{tf_name}' → Run."
                ),
            }
        raw = exc.read()
        try:
            err = json.loads(raw)
            msg = err.get("message", err.get("code", raw.decode(errors="replace")[:300]))
        except Exception:
            msg = raw.decode(errors="replace")[:300]
        return {"status": "error", "exit_code": exc.code, "error": msg}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _deploy_local_table(space_id: str, tl_name: str, tl_csn: dict) -> dict:
    """Write Local Table CSN to a temp file and deploy via CLI."""
    from executors.datasphere_cli import _run_cli

    fd, path = tempfile.mkstemp(suffix=".json", prefix="tl_csn_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(tl_csn, f, indent=2)
        return _run_cli([
            "objects", "local-tables", "create",
            "--space", space_id,
            "--technical-name", tl_name,
            "--file-path", path,
            "--save-anyway",
        ])
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

def _validate_params(params: dict) -> list[str]:
    """Return a list of validation error messages, or an empty list if all OK."""
    errors: list[str] = []

    source_view = params.get("source_view", "")
    if not source_view:
        errors.append("source_view is required.")
    elif not source_view.upper().startswith("SV_"):
        errors.append(
            f"source_view must start with 'SV_'. Got: '{source_view}'"
        )

    if not params.get("space_id", ""):
        errors.append("space_id is required.")

    mode = params.get("mode", "simple")
    if mode not in ("simple", "aggregated"):
        errors.append(
            f"mode must be 'simple' or 'aggregated'. Got: '{mode}'"
        )

    load_type = params.get("load_type", "FULL")
    if load_type not in ("FULL", "INITIAL_ONLY", "DELTA"):
        errors.append(
            f"load_type must be 'FULL', 'INITIAL_ONLY', or 'DELTA'. Got: '{load_type}'"
        )

    tf_name = params.get("tf_name", "")
    if tf_name and not tf_name.upper().startswith("TF_"):
        errors.append(f"tf_name must start with 'TF_'. Got: '{tf_name}'")

    tl_name = params.get("tl_name", "")
    if tl_name and not tl_name.upper().startswith("TL_"):
        errors.append(f"tl_name must start with 'TL_'. Got: '{tl_name}'")

    if params.get("deploy"):
        if params.get("confirm") is not True:
            errors.append("Human confirmation required: set confirm=true.")
        if params.get("acknowledge_ai") is not True:
            errors.append(
                "AI literacy acknowledgement required: set acknowledge_ai=true."
            )

    return errors


# ---------------------------------------------------------------------------
# Public execute entry-point
# ---------------------------------------------------------------------------

def execute(params: dict) -> dict:
    """Skill 6 entry-point -- generic Datasphere Transformation Engine.

    Required params:
      source_view   (str)  -- Source SQL view (must start with SV_)
      space_id      (str)  -- Datasphere space ID

    Optional params:
      mode            (str)   -- "simple" (default) or "aggregated"
      exclude_columns (list)  -- Column names to exclude from the flow
      tf_name         (str)   -- Override TF_ technical name
      tl_name         (str)   -- Override TL_ technical name
      deploy          (bool)  -- False = dry-run (default), True = deploy
      confirm         (bool)  -- Required when deploy=True
      acknowledge_ai  (bool)  -- Required when deploy=True
    """
    errors = _validate_params(params)
    if errors:
        return {"status": "error", "errors": errors}

    source_view = params["source_view"].upper()
    space_id = params["space_id"]
    mode = params.get("mode", "simple")
    load_type = params.get("load_type", "FULL")
    deploy = params.get("deploy", False) is True
    confirm = params.get("confirm", False)
    acknowledge_ai = params.get("acknowledge_ai", False)

    exclude: frozenset[str] = frozenset(
        c.upper() for c in params.get("exclude_columns", [])
    )

    # Derive object names from source view base
    base = source_view.removeprefix("SV_") if source_view.startswith("SV_") else source_view
    tl_suffix = "_AGG" if mode == "aggregated" else ""
    tf_name = (params.get("tf_name") or f"TF_{base}").upper()
    tl_name = (params.get("tl_name") or f"TL_{base}{tl_suffix}").upper()

    # --- Read source view CSN ---
    from executors.datasphere_cli import _get_access_token, HOST as _HOST, read_view_raw

    existing_csn: dict | None = None
    try:
        token = _get_access_token()
        url = (
            f"{_HOST}/dwaas-core/api/v1/spaces/{space_id}/views/{source_view}"
        )
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": (
                    "application/vnd.sap.datasphere.object.content"
                    ".design-time+json"
                ),
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            existing_csn = json.loads(resp.read())
    except Exception as exc:
        log.debug("HTTP GET view '%s' failed, falling back to CLI: %s", source_view, exc)

    if existing_csn is None:
        existing_csn = read_view_raw(space_id, source_view)

    if existing_csn is None:
        return {
            "status": "error",
            "errors": [
                f"Cannot read view '{source_view}' from space '{space_id}'"
            ],
        }

    view_def = existing_csn.get("definitions", {}).get(source_view, {})
    elements: dict = view_def.get("elements", {})
    if not elements:
        return {
            "status": "error",
            "errors": [
                f"View '{source_view}' has no elements -- verify the view is deployed"
            ],
        }

    # --- Classify columns ---
    dimensions, measures = classify_columns(elements, exclude)

    if not dimensions and not measures:
        return {
            "status": "error",
            "errors": ["No columns remain after applying exclude_columns"],
        }

    if mode == "aggregated" and not dimensions:
        return {
            "status": "error",
            "errors": [
                "Aggregated mode requires at least one dimension column (non-numeric). "
                "All remaining columns are measures. "
                "Reduce exclude_columns or switch to mode='simple'."
            ],
        }

    key_columns: frozenset[str] | None = None
    raw_keys = params.get("key_columns", [])
    if raw_keys:
        key_columns = frozenset(c.upper() for c in raw_keys)

    # --- Build CSN artefacts ---
    tl_csn = build_local_table_csn(tl_name, dimensions, measures, mode, key_columns)
    tf_csn = build_transformation_flow_csn(
        tf_name, source_view, tl_name, dimensions, measures, mode, load_type, key_columns
    )

    # columns block only emitted for aggregated mode (not meaningful for simple)
    col_info: dict[str, Any] = {}
    if mode == "aggregated":
        col_info = {
            "dimensions": [d["name"] for d in dimensions],
            "measures": [m["name"] for m in measures],
        }

    # --- Dry-run ---
    if not deploy:
        response: dict[str, Any] = {
            "status": "dry_run",
            "mode": mode,
            "load_type": load_type,
            "source_view": source_view,
            "space_id": space_id,
            "transformation_flow": tf_name,
            "target_table": tl_name,
            "tl_csn": tl_csn,
            "tf_csn": tf_csn,
            "next_step": (
                "Review the CSN above. To deploy, call again with "
                "deploy=true, confirm=true, acknowledge_ai=true."
            ),
        }
        if col_info:
            response["columns"] = col_info
        return response

    # --- Live deploy ---
    results: dict[str, Any] = {}

    # Step 1: Create Local Table via CLI
    cli_result = _deploy_local_table(space_id, tl_name, tl_csn)
    results["local_table"] = {
        "status": cli_result.get("status", "error"),
        "message": cli_result.get("output") or cli_result.get("error", ""),
    }
    log.info("Local table '%s': %s", tl_name, results["local_table"]["status"])

    # Step 2: Create Transformation Flow via HTTP PUT
    token = _get_access_token()
    results["transformation_flow"] = _deploy_transformation_flow_http(
        tf_name, space_id, tf_csn, _HOST, token, deploy=True
    )
    log.info(
        "Transformation flow '%s': %s",
        tf_name,
        results["transformation_flow"].get("status"),
    )

    # Step 3: Run the flow once immediately after successful deployment
    if results["transformation_flow"].get("status") == "success":
        token = _get_access_token()
        results["run"] = _run_transformation_flow(tf_name, space_id, _HOST, token)
        log.info("Run '%s': %s", tf_name, results["run"].get("status"))
    else:
        results["run"] = {"status": "skipped", "reason": "TF deployment did not succeed"}

    overall = (
        "deployed"
        if all(r.get("status") in ("success", "not_supported", "skipped") for r in results.values())
        else "partial"
    )

    response = {
        "status": overall,
        "mode": mode,
        "load_type": load_type,
        "source_view": source_view,
        "space_id": space_id,
        "transformation_flow": tf_name,
        "target_table": tl_name,
        "columns_deployed": len(dimensions) + len(measures),
        "results": results,
    }
    if col_info:
        response["columns"] = col_info
    return response


register_skill("create_transformation_flow", execute)
