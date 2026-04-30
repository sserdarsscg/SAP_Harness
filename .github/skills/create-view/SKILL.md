---
name: create-view
description: 'Create new views in SAP Datasphere using CSN (Core Schema Notation) format. Use when: user says "create view", "new view", "define view", or wants to create a Datasphere entity with columns. Generates CSN JSON and calls the datasphere CLI.'
argument-hint: 'Provide the view name, business name, and column definitions'
---

# Create View

## When to Use
- User wants to create a new view in SAP Datasphere
- User says "create view", "new view", "define view"
- User wants to define a Datasphere entity with custom columns

## What It Does
1. Generates a CSN (Core Schema Notation) JSON definition
2. Writes it to a temporary file
3. Calls `datasphere objects views create` via the CLI
4. Returns the creation result (saved view name)

## Naming Conventions (MANDATORY)

View names MUST follow these prefixes based on type:

| View Type | Prefix | Pattern | Example |
|-----------|--------|---------|---------|
| Graphical View | `GV_` | `GV_<NAME>` | `GV_CUSTOMERS` |
| SQL View | `SV_` | `SV_<NAME>` | `SV_SALES_AGG` |
| Analytic Model | `AM_` | `AM_<NAME>` | `AM_REVENUE` |
| Entity Relationship | `ER_` | `ER_<NAME>` | `ER_ORDER_ITEMS` |

**Rules**:
- SQL Views (`SV_`) → ONLY in Gold Propagation layer (`30_GP_*` spaces)
- Graphical Views (`GV_`) → Silver and Gold layers
- Analytic Models (`AM_`) → Gold Reporting layer only
- ALWAYS uppercase, underscore separator
- If user says just "create a view called CUSTOMERS" → use `GV_CUSTOMERS`
- Default prefix is `GV_` (Graphical View) unless user specifies otherwise
- Do NOT use `V_` prefix — use `GV_`, `SV_`, or `AM_`

See full naming rules: [naming-conventions.instructions.md](../../instructions/naming-conventions.instructions.md)

## MCP Tool

**Tool name**: `create_view`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `view_name` | string | yes | — | Technical name (e.g. `V_SALES_ITEMS`) |
| `business_name` | string | no | same as view_name | Human-readable label |
| `space_id` | string | no | `ZZ_BDC_HARNESS_1` | Space to create the view in |
| `columns` | array | yes | — | Column definitions (see below) |

### Column Definition

Each column is an object:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | yes | — | Column technical name |
| `type` | string | no | `cds.String` | CDS type |
| `key` | boolean | no | `false` | Primary key flag |
| `length` | integer | no | — | String length |
| `label` | string | no | same as name | Human-readable column label |

### Supported CDS Types
- `cds.Integer` – Integer numbers
- `cds.String` – Text (use `length` for max chars)
- `cds.Decimal` – Decimal numbers
- `cds.Timestamp` – Date and time
- `cds.Date` – Date only
- `cds.Boolean` – True/false

## CSN Format

The generated CSN follows Datasphere's required format:

```json
{
  "definitions": {
    "V_EXAMPLE": {
      "kind": "entity",
      "@EndUserText.label": "Example View",
      "query": {
        "SELECT": {
          "from": { "ref": ["V_EXAMPLE"] },
          "columns": [{ "ref": ["COL1"] }, { "ref": ["COL2"] }]
        }
      },
      "elements": {
        "COL1": { "type": "cds.Integer", "key": true },
        "COL2": { "type": "cds.String", "length": 100 }
      }
    }
  }
}
```

## Procedure

1. Call the `create_view` MCP tool with view name and columns
2. In **mock mode**: returns a dry-run showing the generated CSN
3. In **live mode**: writes CSN to temp file → calls CLI → cleans up temp file

## Important Notes

- View names MUST use correct prefix: `GV_`, `SV_`, or `AM_` (NOT `V_`)
- The CLI uses `--save-anyway --no-deploy` (saves without deploying)
- To deploy after creation, use the Datasphere frontend or a separate deploy call
- No namespace prefix in the definition key (just the view name)

## Example

```
User: "Create a view called CUSTOMERS with ID, name, and email"
→ Tool call: create_view(
    view_name="GV_CUSTOMERS",
    business_name="Customers",
    columns=[
      {"name": "ID", "type": "cds.Integer", "key": true},
      {"name": "NAME", "type": "cds.String", "length": 100},
      {"name": "EMAIL", "type": "cds.String", "length": 255}
    ]
  )
→ Returns: "Saved 'V_CUSTOMERS'"
```

## Source

- Skill implementation: [create_view.py](../../datasphere-agent/skills/create_view.py)
- CSN generator: `generate_csn(view_name, columns, business_name)`
- CLI executor: [datasphere_cli.py](../../datasphere-agent/executors/datasphere_cli.py) → `create_view(space_id, csn_json_path)`
