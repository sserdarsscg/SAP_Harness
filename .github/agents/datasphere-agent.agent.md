---
name: datasphere-agent
description: 'SAP Datasphere agent that manages views, spaces, and data transformations via the datasphere CLI. Use when: user wants to interact with SAP Datasphere – create views, read views, list spaces, or transform data between layers. All operations go through the CLI subprocess, not REST API.'
---

# SAP Datasphere Agent

An MCP-compatible agent for SAP Datasphere operations via the CLI.

## Available Skills

| Skill | MCP Tool(s) | Purpose |
|-------|-------------|---------|
| [bronze-to-silver](../skills/bronze-to-silver/SKILL.md) | `bronze_to_silver` | Data layer transformation (bronze → silver) |
| [read-view](../skills/read-view/SKILL.md) | `read_view`, `list_views`, `list_spaces`, `read_space` | Read and discover views/spaces |
| [create-view](../skills/create-view/SKILL.md) | `create_view` | Create new views with CSN definitions |
| [share-to-space](../skills/share-to-space/SKILL.md) | `share_to_space` | Share views to other spaces |

## Setup

### Prerequisites
1. Python 3.11+
2. SAP Datasphere CLI: `npm install -g @sap/datasphere-cli`
3. CLI login: `datasphere login --host <tenant-url> --client-id <id> --client-secret <secret>`

### Configuration
1. Copy `datasphere-agent/.env.example` to `datasphere-agent/.env`
2. Fill in your Datasphere tenant credentials
3. Configure `.vscode/mcp.json` (already provided)

## Execution Modes

### Mock Mode (default)
```
python mcp_server.py
```
Returns dry-run output without making real CLI calls. Safe for testing.

### Live Mode
```
python mcp_server.py --live
```
Executes real `datasphere` CLI commands against your tenant.

## How Others Can Use These Skills

### Option 1: Copy the `.github/skills/` folder
Copy the `.github/skills/` directory into your project. Copilot will discover the skills via SKILL.md files automatically.

### Option 2: Add as MCP server
Add the MCP server configuration to your `.vscode/mcp.json`:
```json
{
  "servers": {
    "datasphere-live": {
      "type": "stdio",
      "command": "python",
      "args": ["mcp_server.py", "--live"],
      "cwd": "<path-to>/datasphere-agent"
    }
  }
}
```

### Option 3: CLI usage
```bash
cd datasphere-agent
python main.py "create a new view V_CUSTOMERS"
python main.py "move bronze customer table to silver"
```
