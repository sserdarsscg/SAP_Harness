# Datasphere Agent – MCP Skill System

Minimal MCP-compatible agent skill system for SAP Datasphere.
Everything is a **safe dry-run mock** – no real Datasphere connection.

## Project Structure

```
datasphere-agent/
├─ agent/
│  ├─ __init__.py
│  ├─ planner.py             # Orchestrates: intent → skill → executor
│  ├─ intents.py             # Keyword-based intent detection
│  ├─ skill_registry.py      # Central skill lookup registry
│
├─ skills/
│  ├─ __init__.py
│  ├─ bronze_to_silver.py    # Generates bronze→silver SQL
│
├─ executors/
│  ├─ __init__.py
│  ├─ mock_datasphere_cli.py # Dry-run executor (no real access)
│
├─ mcp_tools/
│  ├─ bronze_to_silver_tool.json  # MCP tool descriptor
│
├─ tests/
│  ├─ test_tool_descriptor_contract.py
│
├─ mcp_server.py             # MCP server (stdio JSON-RPC 2.0)
├─ cli.py                    # CLI argument parsing
├─ main.py                   # CLI entry point
├─ README.md
```

## Requirements

- Python 3.11+
- No external dependencies (standard library only)

---

## 1. CLI Usage

```bash
cd datasphere-agent
python main.py "move bronze customer table to silver"
```

Flow: `User Prompt → Planner → Skill → Executor → Output`

---

## 2. MCP Server (stdio)

The MCP server exposes skills as tools over a JSON-RPC 2.0 stdio transport.
GitHub Copilot Agent Mode (or any MCP client) can discover and call them.

### Start in VS Code

1. Open the workspace in VS Code.
2. A `.vscode/mcp.json` is provided – VS Code will show a **Start** button
   next to the `datasphere-mock` server entry.
3. Click **Start** to launch the MCP server.
4. Open **Copilot Chat → Agent Mode**.
5. The `bronze_to_silver` tool appears in the tool list – enable it.
6. Prompt: *"Move the bronze CUSTOMER table to silver"* – Copilot will
   invoke the tool and display the generated SQL + dry-run status.

### Manual terminal test

Pipe a JSON-RPC request into the server to verify it works:

```powershell
cd datasphere-agent
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | python mcp_server.py
```

Expected response (single line, formatted here for readability):

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "bronze_to_silver",
        "description": "Generate and dry-run a SQL transformation …",
        "inputSchema": { "…": "…" }
      }
    ]
  }
}
```

Call the tool:

```powershell
echo '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"bronze_to_silver","arguments":{"table_name":"CUSTOMER"}}}' | python mcp_server.py
```

Expected response contains the generated SQL and:

```
[Mock Datasphere CLI] Status: OK (dry-run, not executed)
```

---

## 3. Running Tests

```bash
cd datasphere-agent
python -m unittest tests.test_tool_descriptor_contract -v
```
