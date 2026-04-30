"""
Mock executor for SAP Datasphere CLI.

Instead of connecting to a real Datasphere instance, this module
prints the SQL that *would* be executed. Useful for development
and testing without cloud access.
"""


def format_dry_run(sql: str) -> str:
    """
    Format the dry-run output for a given SQL statement.
    Returns text only – does NOT print.  Safe for MCP stdio transport.
    """
    separator = "=" * 60
    output_lines = [
        separator,
        "[Mock Datasphere CLI] Received SQL for execution:",
        separator,
        sql,
        separator,
        "[Mock Datasphere CLI] Status: OK (dry-run, not executed)",
        separator,
    ]
    return "\n".join(output_lines)


def execute_sql(sql: str) -> str:
    """
    Simulate executing SQL against SAP Datasphere.
    Prints AND returns the formatted output (used by the CLI flow).
    """
    output = format_dry_run(sql)
    print(output)
    return output
