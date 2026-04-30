# The Forge – SAP Datasphere Agent

This project provides an MCP-compatible agent skill system for SAP Datasphere.
All Datasphere interactions go through the `datasphere` CLI (subprocess), NOT REST API.

## Architecture

- **MCP Server**: `datasphere-agent/mcp_server.py` – stdio JSON-RPC 2.0 transport
- **Skills**: `datasphere-agent/skills/` – each skill generates SQL or CSN definitions
- **Executors**: `datasphere-agent/executors/` – CLI subprocess wrappers
- **Agent**: `datasphere-agent/agent/` – intent detection, skill registry, planner

## Modes

- **Mock mode** (default): Dry-run output, no real CLI calls
- **Live mode** (`--live` flag): Executes real `datasphere` CLI commands

## Conventions

- Python 3.11+, standard library only (no external dependencies)
- SAP Datasphere CLI installed via `npm install -g @sap/datasphere-cli`
- Views use CSN (Core Schema Notation) with `query.SELECT` syntax
- All skills self-register via `agent.skill_registry.register_skill()`
- Stdout is reserved for JSON-RPC; all logs go to stderr

## Available Spaces

- `ZZ_BDC_HARNESS_1` (default)
- `ZZ_BDC_HARNESS_2`
