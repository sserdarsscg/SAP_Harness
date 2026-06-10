"""Skill 7: create_task_chain

Creates a Datasphere Task Chain (TC_) that executes an existing Transformation Flow (TF_).

The generated Task Chain contains exactly two nodes:
  - node 0: START
  - node 1: TASK  (applicationId=TRANSFORMATION_FLOWS, activity=EXECUTE, objectId=<tf_name>)
linked START → TASK with statusRequired="ANY", layout="VERTICAL", schemaVersion=2.

Naming rule: tc_name = "TC_" + tf_name  (e.g. TF_BILLING_DOC_JOINED → TC_TF_BILLING_DOC_JOINED)
This ensures a 1:1 traceable relationship between each Task Chain and its Transformation Flow.

The `tc_name` parameter overrides the derived name when a custom name is required.
`_meta.dependencies.folderAssignment` is included only when `folder` param is supplied.

Three deployment modes:
  dry_run              (default) — returns the CSN dict without touching Datasphere
  deploy               (deploy=True + confirm=True + acknowledge_ai=True) — creates TC via CLI
  deploy + run         (deploy=True + run=True + confirm=True + acknowledge_ai=True) — creates TC then immediately executes it
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from typing import Any

from agent.skill_registry import register_skill

log = logging.getLogger("skill-7")

DEFAULT_SPACE = "ZZ_BDC_HARNESS_1"


# ---------------------------------------------------------------------------
# CSN builder — pure function, no I/O
# ---------------------------------------------------------------------------

def build_task_chain_csn(
    tc_name: str,
    tf_name: str,
    folder: str | None = None,
) -> dict:
    """Build the full Task Chain CSN dict.

    Parameters
    ----------
    tc_name : str
        Technical name for the Task Chain (e.g. TC_TF_BILLING_DOC_JOINED).
    tf_name : str
        Technical name of the Transformation Flow to execute (e.g. TF_BILLING_DOC_JOINED).
    folder : str | None
        When provided, written to ``_meta.dependencies.folderAssignment``.
        Omitted entirely when None.

    Returns
    -------
    dict
        Complete Task Chain CSN ready for ``json.dumps`` and CLI deployment.

    Public — used by tests and the MCP server handler.
    """
    task_chain_def: dict[str, Any] = {
        "kind": "sap.dwc.taskChain",
        "@EndUserText.label": tc_name,
        "nodes": [
            {"id": 0, "type": "START"},
            {
                "id": 1,
                "type": "TASK",
                "taskIdentifier": {
                    "applicationId": "TRANSFORMATION_FLOWS",
                    "activity": "EXECUTE",
                    "objectId": tf_name,
                },
                "ignoreError": False,
            },
        ],
        "links": [
            {
                "startNode": {"nodeId": 0, "statusRequired": "ANY"},
                "endNode": {"nodeId": 1},
                "id": 0,
            }
        ],
        "options": {"layout": "VERTICAL"},
        "schemaVersion": 2,
    }

    if folder is not None:
        task_chain_def["_meta"] = {
            "dependencies": {"folderAssignment": folder}
        }

    return {
        "taskchains": {tc_name: task_chain_def},
    }


# ---------------------------------------------------------------------------
# Name derivation
# ---------------------------------------------------------------------------

def derive_tc_name(tf_name: str) -> str:
    """Derive the Task Chain name from the Transformation Flow name.

    Rule: TC_ + tf_name  (e.g. TF_BILLING_DOC_JOINED → TC_TF_BILLING_DOC_JOINED)

    Public — used by tests and the MCP server handler.
    """
    return "TC_" + tf_name


# ---------------------------------------------------------------------------
# execute — MCP/skill entry point
# ---------------------------------------------------------------------------

def execute(params: dict) -> dict:
    """Skill 7 entry point: create (and optionally deploy) a Task Chain.

    Parameters (from params dict)
    -----------------------------
    tf_name        : str   – Transformation Flow technical name (required, TF_ prefix)
    space_id       : str   – Datasphere space (default: ZZ_BDC_HARNESS_1)
    tc_name        : str   – Override TC name (default: TC_<tf_name>)
    folder         : str   – folderAssignment value for _meta (optional)
    deploy         : bool  – True = deploy via CLI (default: False)
    run            : bool  – True = execute TC immediately after deploy (requires deploy=True)
    confirm        : bool  – Human confirmation gate (required when deploy=True)
    acknowledge_ai : bool  – AI literacy gate (required when deploy=True)
    """
    # ------------------------------------------------------------------
    # 1. Extract and validate parameters
    # ------------------------------------------------------------------
    tf_name: str = params.get("tf_name", "")
    space_id: str = params.get("space_id", DEFAULT_SPACE)
    tc_name_override: str | None = params.get("tc_name")
    folder: str | None = params.get("folder") or None
    deploy: bool = params.get("deploy", False) is True
    run: bool = params.get("run", False) is True
    confirm: bool = params.get("confirm", False) is True
    acknowledge_ai: bool = params.get("acknowledge_ai", False) is True

    errors: list[str] = []

    if not tf_name:
        errors.append("tf_name is required")
    elif not tf_name.upper().startswith("TF_"):
        errors.append(f"tf_name must start with TF_ (got '{tf_name}')")

    if tc_name_override and not tc_name_override.upper().startswith("TC_"):
        errors.append(f"tc_name must start with TC_ (got '{tc_name_override}')")

    if run and not deploy:
        errors.append("run=True requires deploy=True. Set deploy=True to create the Task Chain before running.")

    if errors:
        return {"status": "error", "errors": errors}

    # ------------------------------------------------------------------
    # 2. Derive names
    # ------------------------------------------------------------------
    tf_name = tf_name.upper()
    tc_name = tc_name_override.upper() if tc_name_override else derive_tc_name(tf_name)

    # ------------------------------------------------------------------
    # 3. Build CSN
    # ------------------------------------------------------------------
    tc_csn = build_task_chain_csn(tc_name=tc_name, tf_name=tf_name, folder=folder)

    # ------------------------------------------------------------------
    # 4. Dry-run — return CSN without deploying
    # ------------------------------------------------------------------
    if not deploy:
        return {
            "status": "dry_run",
            "tf_name": tf_name,
            "tc_name": tc_name,
            "space_id": space_id,
            "folder": folder,
            "tc_csn": tc_csn,
            "next_step": (
                "Review the CSN above. "
                "To deploy, call again with deploy=true, confirm=true, acknowledge_ai=true. "
                "Add run=true to deploy and immediately execute the Task Chain."
            ),
        }

    # ------------------------------------------------------------------
    # 5. Deploy guard — governance gate (confirm + acknowledge_ai)
    # ------------------------------------------------------------------
    if not (confirm and acknowledge_ai):
        return {
            "status": "error",
            "errors": [
                "Deploy blocked: set confirm=true and acknowledge_ai=true to proceed."
            ],
        }

    # ------------------------------------------------------------------
    # 6. Write CSN to temp file and deploy via CLI
    # ------------------------------------------------------------------
    from executors.datasphere_cli import create_task_chain as cli_create_task_chain
    from executors.datasphere_cli import update_task_chain as cli_update_task_chain
    from executors.datasphere_cli import run_task_chain as cli_run_task_chain

    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".json",
        delete=False,
        encoding="utf-8",
    ) as tmp:
        json.dump(tc_csn, tmp, indent=2)
        tmp_path = tmp.name

    try:
        cli_output = cli_create_task_chain(
            space_id=space_id,
            csn_json_path=tmp_path,
            technical_name=tc_name,
        )
        # If create fails (object already exists), fall back to update
        if "FAILED" in cli_output or "Status: FAILED" in cli_output:
            cli_output = cli_update_task_chain(
                space_id=space_id,
                csn_json_path=tmp_path,
                technical_name=tc_name,
            )
        task_chain_status = "success" if "Status: OK" in cli_output else "error"

        # ------------------------------------------------------------------
        # 7. Optionally run the Task Chain immediately after deploy
        # ------------------------------------------------------------------
        if run:
            run_output = cli_run_task_chain(
                space_id=space_id,
                technical_name=tc_name,
            )
            run_status = "success" if "Status: OK" in run_output else "error"
            return {
                "status": "deployed_and_running",
                "tf_name": tf_name,
                "tc_name": tc_name,
                "space_id": space_id,
                "folder": folder,
                "results": {
                    "task_chain": {
                        "status": task_chain_status,
                        "message": cli_output,
                    },
                    "run": {
                        "status": run_status,
                        "message": run_output,
                    },
                },
            }

        return {
            "status": "deployed",
            "tf_name": tf_name,
            "tc_name": tc_name,
            "space_id": space_id,
            "folder": folder,
            "results": {
                "task_chain": {
                    "status": task_chain_status,
                    "message": cli_output,
                }
            },
        }
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Self-register on import
# ---------------------------------------------------------------------------

register_skill("create_task_chain", execute)
