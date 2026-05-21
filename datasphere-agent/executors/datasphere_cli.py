"""
Datasphere CLI executor.

Runs SAP Datasphere CLI commands via subprocess.
All interaction with Datasphere goes through the `datasphere` CLI tool.

Requires:
  - npm install -g @sap/datasphere-cli
  - datasphere login (already authenticated)

Supported operations:
  - spaces list / read
  - objects views list / read
  - dbusers list
"""

import json
import subprocess
import logging
import shutil
import os
from pathlib import Path

log = logging.getLogger("datasphere-cli")

# Datasphere tenant URL
HOST = "https://vp-dsp-poc23.eu10.hcs.cloud.sap"


def _find_cli() -> str:
    """Locate the datasphere CLI executable on PATH."""
    cli_path = shutil.which("datasphere")
    if cli_path is None:
        # Try common locations on Windows when PATH is not initialized.
        # Order matters: prefer workspace-local portable CLI first.
        current_file = Path(__file__).resolve()
        workspace_root = current_file.parents[2]
        candidates = [
            workspace_root / ".tools" / "node" / "datasphere.cmd",
            Path(os.environ.get("APPDATA", "")) / "npm" / "datasphere.cmd",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        raise FileNotFoundError(
            "datasphere CLI not found. Install with: npm install -g @sap/datasphere-cli"
        )
    return cli_path


def _build_cli_env(cli_path: str) -> dict[str, str]:
    """Build subprocess environment with resilient PATH entries for Node/npm."""
    env = os.environ.copy()
    current_file = Path(__file__).resolve()
    workspace_root = current_file.parents[2]

    extra_paths = [
        str(workspace_root / ".tools" / "node"),
        str(Path(os.environ.get("APPDATA", "")) / "npm"),
        str(Path(cli_path).parent),
    ]

    existing = env.get("PATH", "")
    env["PATH"] = os.pathsep.join([*extra_paths, existing])
    return env


def _run_cli(args: list[str]) -> dict:
    """
    Run a datasphere CLI command and return structured output.
    Always appends --host to target the configured tenant.
    """
    cli = _find_cli()
    full_cmd = [cli] + args + ["--host", HOST]
    env = _build_cli_env(cli)

    log.info("Running: datasphere %s", " ".join(args))

    try:
        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode != 0:
            return {
                "status": "error",
                "exit_code": result.returncode,
                "command": f"datasphere {' '.join(args)}",
                "error": stderr or stdout or "Unknown error",
                "stdout": stdout,
                "stderr": stderr,
            }

        # Try to parse as JSON (most CLI commands return JSON)
        # CLI may append WARNING lines after JSON — extract only the JSON block
        try:
            data = json.loads(stdout)
            return {
                "status": "success",
                "command": f"datasphere {' '.join(args)}",
                "data": data,
            }
        except json.JSONDecodeError:
            # Try extracting JSON before WARNING lines
            json_part = stdout.split("\nWARNING")[0].strip()
            try:
                data = json.loads(json_part)
                return {
                    "status": "success",
                    "command": f"datasphere {' '.join(args)}",
                    "data": data,
                }
            except json.JSONDecodeError:
                return {
                    "status": "success",
                    "command": f"datasphere {' '.join(args)}",
                    "output": stdout,
                }

    except subprocess.TimeoutExpired:
        return {
            "status": "error",
            "command": f"datasphere {' '.join(args)}",
            "error": "Command timed out after 60 seconds",
        }
    except FileNotFoundError:
        return {
            "status": "error",
            "command": f"datasphere {' '.join(args)}",
            "error": "datasphere CLI not found on PATH",
        }


def _format_result(result: dict) -> str:
    """Format a CLI result dict into human-readable text."""
    separator = "=" * 60
    lines = [separator]

    lines.append(f"[Datasphere CLI] Command: {result.get('command', '?')}")
    lines.append(separator)

    if result["status"] == "error":
        lines.append(f"[Datasphere CLI] ERROR (exit code {result.get('exit_code', '?')}):")
        lines.append(result.get("error", "Unknown error"))
    elif "data" in result:
        lines.append(json.dumps(result["data"], indent=2))
    else:
        lines.append(result.get("output", ""))

    lines.append(separator)
    status_label = "OK" if result["status"] == "success" else "FAILED"
    lines.append(f"[Datasphere CLI] Status: {status_label}")
    lines.append(separator)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API – each function maps to a CLI command
# ---------------------------------------------------------------------------


def list_spaces() -> str:
    """Run: datasphere spaces list"""
    result = _run_cli(["spaces", "list"])
    return _format_result(result)


def read_space(space_id: str) -> str:
    """Run: datasphere spaces read --space <space_id>"""
    result = _run_cli(["spaces", "read", "--space", space_id])
    return _format_result(result)


def list_views(space_id: str) -> str:
    """Run: datasphere objects views list --space <space_id>"""
    result = _run_cli(["objects", "views", "list", "--space", space_id])
    return _format_result(result)


def read_view(space_id: str, technical_name: str) -> str:
    """Run: datasphere objects views read --space <space_id> --technical-name <name>"""
    result = _run_cli([
        "objects", "views", "read",
        "--space", space_id,
        "--technical-name", technical_name,
    ])
    return _format_result(result)


def list_dbusers() -> str:
    """Run: datasphere dbusers list"""
    result = _run_cli(["dbusers", "list"])
    return _format_result(result)


def create_view(space_id: str, csn_json_path: str) -> str:
    """Run: datasphere objects views create --space <space_id> --file-path <path> --save-anyway --no-deploy"""
    result = _run_cli([
        "objects", "views", "create",
        "--space", space_id,
        "--file-path", csn_json_path,
        "--save-anyway",
        "--no-deploy",
    ])
    return _format_result(result)


def deploy_view(space_id: str, csn_json_path: str) -> str:
    """Run: datasphere objects views create --space <space_id> --file-path <path> --save-anyway (with deploy)"""
    result = _run_cli([
        "objects", "views", "create",
        "--space", space_id,
        "--file-path", csn_json_path,
        "--save-anyway",
    ])
    return _format_result(result)


def read_local_table(space_id: str, technical_name: str) -> dict | None:
    """
    Read a local table definition and return parsed JSON.
    Returns None on error.
    """
    result = _run_cli([
        "objects", "local-tables", "read",
        "--space", space_id,
        "--technical-name", technical_name,
    ])
    if result["status"] == "error":
        return None
    return result.get("data")


def read_view_raw(space_id: str, technical_name: str) -> dict | None:
    """
    Read a view definition and return the parsed CSN dict.
    Returns None on error.
    """
    result = _run_cli([
        "objects", "views", "read",
        "--space", space_id,
        "--technical-name", technical_name,
    ])
    if result["status"] == "error":
        return None
    return result.get("data")


def update_view(space_id: str, csn_json_path: str, technical_name: str) -> str:
    """Run: datasphere objects views update --space <space_id> --technical-name <name> --file-path <path> --save-anyway"""
    result = _run_cli([
        "objects", "views", "update",
        "--space", space_id,
        "--technical-name", technical_name,
        "--file-path", csn_json_path,
        "--save-anyway",
    ])
    return _format_result(result)


def update_view_no_deploy(space_id: str, csn_json_path: str, technical_name: str) -> str:
    """Run: datasphere objects views update ... --save-anyway --no-deploy (save only, skip deployment)"""
    result = _run_cli([
        "objects", "views", "update",
        "--space", space_id,
        "--technical-name", technical_name,
        "--file-path", csn_json_path,
        "--save-anyway",
        "--no-deploy",
    ])
    return _format_result(result)
