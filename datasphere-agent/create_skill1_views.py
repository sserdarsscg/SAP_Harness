"""
Batch script: Create and deploy one pass-through GV_ view
for each source table in ZZ_BDC_HARNESS_1.

Usage:
    cd datasphere-agent
    python create_skill1_views.py
"""

import json
import subprocess
import shutil
import os
import tempfile
import sys

HOST = "https://vp-dsp-poc23.eu10.hcs.cloud.sap"
SPACE = "ZZ_BDC_HARNESS_1"


def find_cli():
    cli = shutil.which("datasphere")
    if cli:
        return cli
    npm_path = os.path.join(os.environ.get("APPDATA", ""), "npm", "datasphere.cmd")
    if os.path.exists(npm_path):
        return npm_path
    raise FileNotFoundError("datasphere CLI not found")


def run_cli(args):
    cli = find_cli()
    full_cmd = [cli] + args + ["--host", HOST]
    result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=120)
    return result


def read_table(table_name):
    """Read a local table definition to get its columns."""
    result = run_cli([
        "objects", "local-tables", "read",
        "--space", SPACE,
        "--technical-name", table_name,
    ])
    if result.returncode != 0:
        print(f"  ERROR reading table {table_name}: {result.stderr}", file=sys.stderr)
        return None
    # CLI may append WARNING lines after JSON — extract only the JSON block
    stdout = result.stdout.strip()
    # Find the end of the JSON object
    brace_count = 0
    json_end = 0
    for i, ch in enumerate(stdout):
        if ch == '{':
            brace_count += 1
        elif ch == '}':
            brace_count -= 1
            if brace_count == 0:
                json_end = i + 1
                break
    return json.loads(stdout[:json_end])


def build_passthrough_csn(view_name, business_name, source_table, table_def):
    """Build a CSN for a pass-through view from a table definition."""
    source_elements = table_def["definitions"][source_table]["elements"]

    # Build column refs and elements
    columns = []
    elements = {}
    for col_name, col_def in source_elements.items():
        columns.append({"ref": [col_name]})
        # Copy element definition, keeping type, key, length, precision, scale, label
        elem = {"type": col_def["type"]}
        if col_def.get("key"):
            elem["key"] = True
        if col_def.get("notNull"):
            elem["notNull"] = True
        if "length" in col_def:
            elem["length"] = col_def["length"]
        if "precision" in col_def:
            elem["precision"] = col_def["precision"]
        if "scale" in col_def:
            elem["scale"] = col_def["scale"]
        elem["@EndUserText.label"] = col_def.get("@EndUserText.label", col_name)
        elements[col_name] = elem

    csn = {
        "definitions": {
            view_name: {
                "kind": "entity",
                "@EndUserText.label": business_name,
                "query": {
                    "SELECT": {
                        "from": {"ref": [source_table]},
                        "columns": columns,
                    }
                },
                "elements": elements,
            }
        }
    }
    return csn


def create_and_deploy_view(view_name, csn):
    """Save and deploy a view via CLI."""
    fd, path = tempfile.mkstemp(suffix=".json", prefix="csn_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(csn, f, indent=2)

        # Save and deploy (no --no-deploy flag)
        result = run_cli([
            "objects", "views", "create",
            "--space", SPACE,
            "--file-path", path,
            "--save-anyway",
        ])

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode == 0:
            # Extract just the JSON part (CLI may append WARNING lines)
            try:
                data = json.loads(stdout.split("\nWARNING")[0].strip())
                return True, json.dumps(data)
            except json.JSONDecodeError:
                return True, stdout.split("\nWARNING")[0].strip()
        else:
            return False, (stderr or stdout).split("\nWARNING")[0].strip()
    finally:
        os.unlink(path)


# ============================================================
# View definitions: GV_ prefix per naming conventions
# ============================================================
VIEWS = [
    {
        "view_name": "GV_BILLING_DOC_ITEM",
        "business_name": "Billing Document Item",
        "source_table": "VR1_BILLING_DOC_ITEM_TD_001",
    },
    {
        "view_name": "GV_BILLING_DOC_HEADER",
        "business_name": "Billing Document Header",
        "source_table": "VR1_BILLING_DOC_TD_001",
    },
    {
        "view_name": "GV_OPS_ACCT_DOC_ITEM",
        "business_name": "Operational Accounting Document Item",
        "source_table": "VR1_OPS_ACCT_DOC_TD_01",
    },
    {
        "view_name": "GV_CHART_OF_ACCOUNT",
        "business_name": "Chart Of Account",
        "source_table": "VR1_CHART_OF_ACCOUNT_TD_01",
    },
    {
        "view_name": "GV_DOC_ITEM",
        "business_name": "Document Item",
        "source_table": "VR1_DOC_ITEM_TD_001_1",
    },
]


def main():
    print(f"Creating {len(VIEWS)} pass-through views in space {SPACE}")
    print("=" * 60)

    results = []

    for v in VIEWS:
        view_name = v["view_name"]
        source_table = v["source_table"]
        business_name = v["business_name"]

        print(f"\n[{view_name}] Reading source table {source_table}...")
        table_def = read_table(source_table)
        if table_def is None:
            print(f"[{view_name}] SKIP - could not read source table")
            results.append((view_name, False, "Could not read source table"))
            continue

        print(f"[{view_name}] Building CSN (pass-through from {source_table})...")
        csn = build_passthrough_csn(view_name, business_name, source_table, table_def)

        print(f"[{view_name}] Creating and deploying...")
        ok, msg = create_and_deploy_view(view_name, csn)

        status = "OK" if ok else "FAILED"
        print(f"[{view_name}] {status}: {msg}")
        results.append((view_name, ok, msg))

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, ok, msg in results:
        status = "DEPLOYED" if ok else "FAILED"
        print(f"  {name}: {status}")

    success_count = sum(1 for _, ok, _ in results if ok)
    print(f"\n{success_count}/{len(VIEWS)} views deployed successfully.")


if __name__ == "__main__":
    main()
