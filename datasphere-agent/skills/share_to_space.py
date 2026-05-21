"""
Skill: share_to_space

Shares a view (or list of views) from one SAP Datasphere space to another
by adding the @DataWarehouse.shareTo CSN annotation and updating the view
via the datasphere CLI.

The workflow:
1. Read the current CSN definition of the view
2. Add/merge @DataWarehouse.shareTo with the target space(s)
3. Write updated CSN to a temp file
4. Try CLI deploy; if fails, try Playwright UI; last resort save-only
"""

import json
import logging
import os
import tempfile
from agent.skill_registry import register_skill
from executors.datasphere_cli import (
    read_view_raw,
    update_view,
    update_view_no_deploy,
)
from executors.playwright_share import (
    deploy_views as ui_deploy_views,
    share_views_to_space as ui_share_views,
)

log = logging.getLogger("skill.share_to_space")


def build_share_csn(view_csn: dict, target_spaces: list[str]) -> dict:
    """
    Take an existing view CSN and add/merge @DataWarehouse.shareTo annotation.

    Args:
        view_csn:      Full CSN dict as returned by `views read`
        target_spaces: List of space IDs to share to

    Returns:
        Updated CSN dict with shareTo annotation merged.
    """
    definitions = view_csn.get("definitions", {})
    for view_name, view_def in definitions.items():
        existing = view_def.get("@DataWarehouse.shareTo", [])
        merged = list(set(existing) | set(target_spaces))
        view_def["@DataWarehouse.shareTo"] = sorted(merged)

    return view_csn


def share_csn_to_temp_file(csn: dict) -> str:
    """Write updated CSN to a temporary file and return the path."""
    fd, path = tempfile.mkstemp(suffix=".json", prefix="share_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(csn, f, indent=2)
    return path


def execute(params: dict) -> dict:
    """
    Share views to target spaces.
    Fallback chain: CLI deploy -> Playwright UI -> CLI save-only.
    """
    view_names = params.get("view_names", [])
    target_spaces = params.get("target_spaces", [])
    source_space = params.get("source_space", "ZZ_BDC_HARNESS_1")

    if not view_names or not target_spaces:
        return {
            "status": "error",
            "message": "view_names and target_spaces are required.",
        }

    results = []
    for vn in view_names:
        log.info("Sharing %s from %s to %s", vn, source_space, target_spaces)

        # 1. Read current view definition
        view_csn = read_view_raw(source_space, vn)
        if view_csn is None:
            results.append({"view": vn, "status": "error", "message": f"Could not read view {vn} in space {source_space}"})
            continue

        # 2. Add shareTo annotation
        updated_csn = build_share_csn(view_csn, target_spaces)

        # 3. Write to temp file
        temp_path = share_csn_to_temp_file(updated_csn)
        try:
            # 4. Try update + deploy
            output = update_view(source_space, temp_path, vn)

            if "FAILED" not in output:
                results.append({"view": vn, "status": "shared_and_deployed", "message": output})
                continue

            # 5. Fallback: Playwright UI (playwright_share handles missing credentials internally)
            log.warning("CLI deploy failed for %s, trying Playwright UI", vn)
            try:
                deploy_result = ui_deploy_views([vn], source_space)
                share_result = ui_share_views([vn], target_spaces[0], source_space)
                ui_ok = (
                    vn in deploy_result.get("deployed", [])
                    and vn in share_result.get("shared", [])
                )
                if ui_ok:
                    results.append({"view": vn, "status": "shared_and_deployed", "message": "Deployed and shared via Playwright UI."})
                    continue
                else:
                    log.warning("Playwright also failed for %s, falling back to save-only", vn)
            except Exception as ui_exc:
                log.warning("Playwright error for %s: %s", vn, ui_exc)

            # 6. Last resort: CLI save-only (annotation persisted, not deployed)
            output_nd = update_view_no_deploy(source_space, temp_path, vn)

            if "FAILED" not in output_nd:
                results.append({
                    "view": vn,
                    "status": "partial",
                    "message": f"Share annotation saved but NOT deployed. Fix the view query and redeploy manually.\n{output_nd}",
                })
            else:
                results.append({
                    "view": vn,
                    "status": "error",
                    "message": f"All methods failed (CLI deploy, Playwright UI, CLI save-only).\nCLI deploy:\n{output}\nCLI save-only:\n{output_nd}",
                })
        finally:
            os.unlink(temp_path)

    overall = "ok" if all(r["status"] != "error" for r in results) else "error"
    return {
        "status": overall,
        "results": results,
    }


register_skill("share_to_space", execute)
