---
applyTo: "datasphere-agent/**/*.py"
description: 'Python conventions for SAP Datasphere agent code. Use when editing Python files in the datasphere-agent directory.'
---

# Datasphere Agent Python Conventions

## Architecture Rules
- All Datasphere interactions go through the `datasphere` CLI subprocess, NEVER REST API
- Stdout is reserved for JSON-RPC messages; all logs go to stderr
- Python 3.11+, standard library only (no external pip dependencies)

## Skill Pattern
Every skill module must:
1. Live in `datasphere-agent/skills/`
2. Expose a public generator function (e.g. `generate_sql()`, `generate_csn()`)
3. Expose an `execute(params: dict) -> dict` entry point
4. Self-register via `register_skill("skill_name", execute)` at module level
5. Be imported in `skills/__init__.py`

## MCP Integration
When adding a new skill to the MCP server:
1. Add imports to `mcp_server.py` (public generator functions)
2. Add tool definition to `TOOLS` list (with `inputSchema`)
3. Add `_handle_<skill_name>()` function
4. Register handler in `TOOL_HANDLERS` dict
5. Add intent keywords to `agent/intents.py`

## Executor Pattern
- `executors/datasphere_cli.py` – real CLI subprocess calls (live mode)
- `executors/mock_datasphere_cli.py` – dry-run output (mock mode)
- CLI executor functions use `subprocess.run()` with `capture_output=True`

## CSN Format (Views)
Views use Core Schema Notation with `query.SELECT` syntax:
- No namespace prefix in definition key
- `kind: "entity"`
- `@EndUserText.label` for business names
- `elements` for column definitions with `cds.*` types
