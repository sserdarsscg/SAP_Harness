# Datasphere Agent – MCP Skill System

Minimal MCP-compatible agent skill system for SAP Datasphere.
All operations run **LIVE** against your Datasphere tenant.

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
│  ├─ datasphere_cli.py      # Live Datasphere CLI executor
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
   next to the `datasphere-agent` server entry.
3. Click **Start** to launch the MCP server.
4. Open **Copilot Chat → Agent Mode**.
5. The available tools appear in the tool list – enable them.
6. Prompt: *"Create a SQL view named SV_CUSTOMERS from VR1_CUSTOMER_TD_001 in ZZ_BDC_HARNESS_1"* – Copilot will invoke the tool and create the view live in Datasphere.

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
        "name": "create_view",
        "description": "Create a new Graphical (GV_) or SQL (SV_) view in Datasphere …",
        "inputSchema": { "…": "…" }
      }
    ]
  }
}
```

Call the tool:

```powershell
echo '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"create_view","arguments":{"view_name":"TEST_VIEW","view_type":"GV","space_id":"ZZ_BDC_HARNESS_1"}}}' | python mcp_server.py
```

Expected response contains the created view CSN and success status (view is created live in Datasphere).

---

## 3. Running Tests

```bash
cd datasphere-agent
python -m unittest tests.test_tool_descriptor_contract -v
```
