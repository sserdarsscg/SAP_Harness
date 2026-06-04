"""Skill 6: create_transformation_flow

Creates a Transformation Flow (TF_) that reads from an existing SQL view (SV_),
excludes specified key/granular columns, groups by dimension columns
(cds.String, cds.Date, cds.Timestamp), and aggregates measure columns
(cds.Decimal, cds.Integer) via SUM.

Two objects are generated and optionally deployed:
  TL_<NAME>_AGG  – Local Table to receive the aggregated data
  TF_<NAME>      – Transformation Flow: source view -> TL (FULL load)

Naming follows project conventions:
  TL_ prefix for local tables
  TF_ prefix for transformation flows
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

DEFAULT_SOURCE_VIEW = "SV_BILLING_DOC_JOINED"
DEFAULT_SPACE = "ZZ_BDC_HARNESS_1"

# Columns excluded by default (transaction-level keys not meaningful after aggregation)
EXCLUDE_BY_DEFAULT: frozenset[str] = frozenset({"BILLINGDOCUMENT", "BILLINGDOCUMENTITEM"})

# CDS types treated as measures -> SUM aggregation
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

def _classify_columns(
    elements: dict[str, Any],
    exclude: frozenset[str],
) -> tuple[list[dict], list[dict]]:
    """Split view elements into (dimensions, measures), skipping excluded columns.

    Decimal/Integer types -> measures (SUM aggregation).
    Everything else       -> dimensions (GROUP BY).

    Returns two lists of column dicts with keys:
      name, type, label, [precision, scale, length]
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
# CSN builders
# ---------------------------------------------------------------------------

def build_local_table_csn(
    tl_name: str,
    dimensions: list[dict],
    measures: list[dict],
) -> dict:
    """Build CSN definition for the target Local Table (TL_).

    All dimension columns become composite keys; measures are non-key.
    Public – can be used independently and in tests.
    """
    elements: dict[str, Any] = {}

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
        elem = {
            "type": col["type"],
            "@EndUserText.label": col["label"],
        }
        for attr in ("precision", "scale"):
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


def build_transformation_flow_csn(
    tf_name: str,
    source_view: str,
    tl_name: str,
    dimensions: list[dict],
    measures: list[dict],
) -> dict:
    """Build the Transformation Flow CSN definition.

    SELECT list:
      - Dimensions: plain qualified ref  (used in GROUP BY)
      - Measures:   SUM(ref) AS name
    Public – can be used independently and in tests.
    """
    columns: list[Any] = [
        {"ref": [source_view, col["name"]]}
        for col in dimensions
    ]
    columns += [
        {
            "xpr": [{"func": "SUM", "args": [{"ref": [source_view, col["name"]]}]}],
            "as": col["name"],
        }
        for col in measures
    ]

    group_by = [{"ref": [source_view, col["name"]]} for col in dimensions]

    return {
        "definitions": {
            tf_name: {
                "kind": "entity",
                "@EndUserText.label": tf_name.replace("_", " ").title(),
                "@DataWarehouse.taskType": "TF",
                "@DataWarehouse.etlLoad": {
                    "sourceEntity": source_view,
                    "targetEntity": tl_name,
                    "loadType": "FULL",
                },
                "query": {
                    "SELECT": {
                        "from": {"ref": [source_view]},
                        "columns": columns,
                        "groupBy": group_by,
                    }
                },
            }
        }
    }


# ---------------------------------------------------------------------------
# Deploy helpers
# ---------------------------------------------------------------------------

def _read_view_http(space_id: str, view_name: str, host: str, token: str) -> dict | None:
    """Read a view CSN directly via HTTP GET (bypasses CLI auth issues)."""
    url = f"{host}/dwaas-core/api/v1/spaces/{space_id}/views/{view_name}"
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.sap.datasphere.object.content.design-time+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        log.error("HTTP GET view '%s' failed: %s", view_name, exc)
        return None


def _deploy_transformation_flow(
    tf_name: str,
    space_id: str,
    tf_csn: dict,
    host: str,
    token: str,
    deploy: bool = True,
) -> dict:
    """Deploy a Transformation Flow via direct HTTP PUT.

    The CLI `transformation-flows create` (POST) cannot extract the object name
    from the CSN body. The correct approach is PUT to:
      /dwaas-core/api/v1/spaces/{spaceId}/transformationflows/{technicalName}

    deploy=True  → ?saveAnyway=true         (save+deploy)
    deploy=False → ?saveAnyway=true&deploy=false (save only)
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
            msg = err.get("message", err.get("code", raw.decode(errors="replace")[:200]))
        except Exception:
            msg = raw.decode(errors="replace")[:200]
        return {"status": "error", "exit_code": exc.code, "error": msg}
    except Exception as exc:
        return {"status": "error", "error": str(exc)}


def _deploy_object(
    cli_run: Any,
    object_command: list[str],
    space_id: str,
    technical_name: str,
    csn_data: dict,
) -> dict:
    """Write CSN to a temp file and call the CLI; clean up regardless."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        json.dump(csn_data, f, indent=2)
        path = f.name
    try:
        return cli_run(
            object_command
            + [
                "--space", space_id,
                "--technical-name", technical_name,
                "--file-path", path,
                "--save-anyway",
            ]
        )
    finally:
        os.unlink(path)


# ---------------------------------------------------------------------------
# Public execute entry-point
# ---------------------------------------------------------------------------

def execute(params: dict) -> dict:
    """Skill 6 entry-point.

    Required params: none (sensible defaults provided).

    Optional params:
      source_view      (str)  – SQL view to aggregate (default: SV_BILLING_DOC_JOINED)
      space_id         (str)  – Datasphere space (default: ZZ_BDC_HARNESS_1)
      exclude_columns  (list) – extra column names to exclude beyond defaults
      tf_name          (str)  – override generated TF_ name
      tl_name          (str)  – override generated TL_ name
      deploy           (bool) – False = dry-run only, True = deploy to Datasphere
      confirm          (bool) – must be True when deploy=True
      acknowledge_ai   (bool) – must be True when deploy=True
    """
    source_view = params.get("source_view", DEFAULT_SOURCE_VIEW).upper()
    space_id = params.get("space_id", DEFAULT_SPACE)
    extra_exclude: frozenset[str] = frozenset(
        c.upper() for c in params.get("exclude_columns", [])
    )
    exclude = EXCLUDE_BY_DEFAULT | extra_exclude
    deploy = params.get("deploy", False)
    confirm = params.get("confirm", False)
    acknowledge_ai = params.get("acknowledge_ai", False)

    # Derive object names from source view
    base = source_view.removeprefix("SV_") if source_view.startswith("SV_") else source_view
    tf_name = params.get("tf_name", f"TF_{base}").upper()
    tl_name = params.get("tl_name", f"TL_{base}_AGG").upper()

    # --- Read source view CSN ---
    # Use direct HTTP GET (CLI may fail with auth issues on some installations).
    from executors.datasphere_cli import _get_access_token, HOST as _HOST, read_view_raw

    token_for_read = _get_access_token()
    existing_csn = _read_view_http(space_id, source_view, _HOST, token_for_read)
    if existing_csn is None:
        # Fallback to CLI
        existing_csn = read_view_raw(space_id, source_view)
    if existing_csn is None:
        return {
            "status": "error",
            "errors": [f"Cannot read view '{source_view}' from space '{space_id}'"],
        }

    view_def = existing_csn.get("definitions", {}).get(source_view, {})
    elements = view_def.get("elements", {})
    if not elements:
        return {
            "status": "error",
            "errors": [f"View '{source_view}' has no elements — cannot classify columns"],
        }

    dimensions, measures = _classify_columns(elements, exclude)

    if not dimensions:
        return {
            "status": "error",
            "errors": ["No dimension columns remain after exclusions"],
        }

    tl_csn = build_local_table_csn(tl_name, dimensions, measures)
    tf_csn = build_transformation_flow_csn(tf_name, source_view, tl_name, dimensions, measures)

    # --- Dry-run ---
    if not deploy:
        return {
            "status": "dry_run",
            "source_view": source_view,
            "space_id": space_id,
            "excluded_columns": sorted(exclude),
            "tf_name": tf_name,
            "tl_name": tl_name,
            "dimensions": [d["name"] for d in dimensions],
            "measures": [m["name"] for m in measures],
            "tl_csn": tl_csn,
            "tf_csn": tf_csn,
            "next_step": "Review the CSN above. To deploy, call again with deploy=true, confirm=true, acknowledge_ai=true.",
        }

    # --- Live deploy ---
    if not (confirm and acknowledge_ai):
        return {
            "status": "error",
            "errors": ["Deploy blocked: set confirm=true and acknowledge_ai=true to proceed"],
        }

    from executors.datasphere_cli import _run_cli, HOST as _HOST, _get_access_token

    results: dict[str, Any] = {}

    # Step 1: Create Local Table (via CLI — works correctly)
    results["local_table"] = _deploy_object(
        _run_cli,
        ["objects", "local-tables", "create"],
        space_id, tl_name, tl_csn,
    )
    log.info("Local table '%s': %s", tl_name, results["local_table"].get("status"))

    # Step 2: Create Transformation Flow via direct HTTP PUT.
    # The CLI `transformation-flows create` (POST) cannot extract the object
    # name from the CSN body; PUT to .../transformationflows/{name} works correctly.
    token = _get_access_token()
    results["transformation_flow"] = _deploy_transformation_flow(
        tf_name, space_id, tf_csn, _HOST, token, deploy=True
    )
    log.info("Transformation flow '%s': %s", tf_name, results["transformation_flow"].get("status"))

    overall = (
        "deployed"
        if all(r.get("status") == "success" for r in results.values())
        else "partial"
    )

    return {
        "status": overall,
        "source_view": source_view,
        "space_id": space_id,
        "tf_name": tf_name,
        "tl_name": tl_name,
        "dimensions": [d["name"] for d in dimensions],
        "measures": [m["name"] for m in measures],
        "columns_deployed": len(dimensions) + len(measures),
        "results": results,
    }


register_skill("create_transformation_flow", execute)
