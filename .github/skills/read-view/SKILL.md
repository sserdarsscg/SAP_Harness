---
name: read-view
description: 'Read and inspect view definitions from SAP Datasphere. Use when: user says "read view", "select from view", "query view", "show view definition", or asks about views in a space. Also use for listing views and reading space details.'
argument-hint: 'Provide the view name and optionally the space ID'
---

# Read View

## When to Use
- User wants to read a view definition from SAP Datasphere
- User says "read view", "select from view", "query view", "list views"
- User wants to inspect the CSN/JSON definition of a deployed view
- User asks what views exist in a space

## What It Does
- **read_view**: Fetches the JSON/CSN definition of a specific view from Datasphere
- **list_views**: Lists all views in a given space
- **list_spaces**: Lists all available spaces in the tenant
- **read_space**: Reads detailed information about a space

## MCP Tools

### `read_view`
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `view_name` | string | no | `ADSO_Sales_Document_Item_Data_V` | Technical view name |
| `space_id` | string | no | `ZZ_BDC_HARNESS_1` | Datasphere space ID |

### `list_views`
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `space_id` | string | no | `ZZ_BDC_HARNESS_1` | Space to list views from |

### `list_spaces`
No parameters. Lists all spaces in the tenant.

### `read_space`
| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `space_id` | string | no | `ZZ_BDC_HARNESS_1` | Space to read details of |

## Naming Conventions Reference

When interpreting view names, be aware of the standard prefixes:

| Type | Prefix | Layer |
|------|--------|-------|
| Graphical View | `GV_` | Silver/Gold |
| SQL View | `SV_` | Gold Propagation only |
| Analytic Model | `AM_` | Gold Reporting only |
| Entity Relationship | `ER_` | Any |

Space prefixes: `10_BL_` (Bronze), `20_SL_` (Silver), `30_GP_` (Gold Propagation), `40_GR_` (Gold Reporting)

See full naming rules: [naming-conventions.instructions.md](../../instructions/naming-conventions.instructions.md)

## Procedure

1. To discover views, call `list_views` with the space ID
2. To inspect a specific view, call `read_view` with the view name and space ID
3. In **mock mode**: returns a dry-run SELECT SQL
4. In **live mode**: calls `datasphere objects views read` via the CLI

## Available Spaces
- `ZZ_BDC_HARNESS_1` (default)
- `ZZ_BDC_HARNESS_2`

## Example

```
User: "List all views in ZZ_BDC_HARNESS_1"
→ Tool call: list_views(space_id="ZZ_BDC_HARNESS_1")

User: "Read view V_TEST_HELLO"
→ Tool call: read_view(view_name="V_TEST_HELLO", space_id="ZZ_BDC_HARNESS_1")
```

## Source

- Skill implementation: [read_view.py](../../datasphere-agent/skills/read_view.py)
- SQL generator: `generate_read_sql(view_name, space_id, columns, limit)`
