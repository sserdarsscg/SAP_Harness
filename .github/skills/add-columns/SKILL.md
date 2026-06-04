---
name: add-columns
description: 'Add calculated or restricted columns to an existing SQL view (SV_) in SAP Datasphere. Use when: user says "add calculated column", "add restricted column", "add measure", "add a column with expression", "add KPI column", or wants to enhance a view with derived fields. Supports arithmetic expressions and CASE-WHEN logic.'
argument-hint: 'Provide the view name, space, and column definitions with SQL expressions'
---

# Add Columns — Calculated & Restricted (Skill 5)

## When to Use
- User says "add a calculated column", "add a restricted measure", "add KPI"
- User wants to derive a new column from existing fields using an expression
- User provides a SQL expression like `NetAmount + TaxAmount` or `CASE WHEN ... THEN ... END`
- User wants to filter a measure by a condition (restricted column)

## Column Types

| Type | Description | Expression Pattern |
|------|-------------|-------------------|
| `calculated` | Derived value from arithmetic or CASE-ELSE | `A + B`, `CASE WHEN x THEN y ELSE z END` |
| `restricted` | Measure filtered by condition (NULL when false) | `CASE WHEN x THEN y END` (no ELSE) |

**Key rule**: A restricted column is a CASE-WHEN **without** ELSE. The implicit NULL means the measure is excluded when the condition is false — this is the SAP Datasphere restricted measure pattern.

## MCP Tool

**Tool name**: `add_columns`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `view_name` | string | no | `SV_BILLING_DOC_JOINED` | Technical name of the SQL view to enhance |
| `space_id` | string | no | `ZZ_BDC_HARNESS_1` | Datasphere space |
| `columns` | array | yes | — | List of column definitions (see below) |
| `deploy` | boolean | no | `false` | If `true`, save and deploy to Datasphere |
| `confirm` | boolean | no | `false` | Must be `true` to execute a live deploy |
| `acknowledge_ai` | boolean | no | `false` | Must be `true` to confirm AI-generated changes |

### Column Definition Schema

Each item in `columns`:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | yes | — | Technical column name (e.g. `GrossAmount`) |
| `label` | string | no | same as name | Human-readable label |
| `column_type` | string | yes | — | `"calculated"` or `"restricted"` |
| `data_type` | string | no | `cds.Decimal` | CDS type: `cds.Decimal`, `cds.String`, `cds.Integer` |
| `precision` | integer | no | 34 | Decimal precision (for `cds.Decimal`) |
| `scale` | integer | no | 4 | Decimal scale (for `cds.Decimal`) |
| `length` | integer | no | — | String length (for `cds.String`) |
| `expression` | string | yes | — | SQL expression string (see examples below) |

## Expression Syntax

### Calculated — Arithmetic
```
NetAmount + TaxAmount
NetAmount - Discount
Quantity * UnitPrice
```

### Calculated — CASE with ELSE
```
CASE WHEN BillingQuantity > 100 THEN 'High' WHEN BillingQuantity > 10 THEN 'Medium' ELSE 'Low' END
```

### Restricted — CASE without ELSE (implicit NULL)
```
CASE WHEN BillingDocumentType = 'F2' THEN NetAmount END
CASE WHEN NetAmount > 10000 THEN NetAmount END
CASE WHEN SalesOrganization = '1000' THEN BillingQuantity END
```

## Example Prompts → Tool Calls

**"Add a calculated column GrossAmount = NetAmount + TaxAmount"**
```json
{
  "view_name": "SV_BILLING_DOC_JOINED",
  "space_id": "ZZ_BDC_HARNESS_1",
  "columns": [
    {
      "name": "GrossAmount",
      "label": "Gross Amount",
      "column_type": "calculated",
      "data_type": "cds.Decimal",
      "precision": 34,
      "scale": 4,
      "expression": "NetAmount + TaxAmount"
    }
  ],
  "deploy": false
}
```

**"Add a restricted column InvoiceRevenue — only for billing type F2"**
```json
{
  "view_name": "SV_BILLING_DOC_JOINED",
  "space_id": "ZZ_BDC_HARNESS_1",
  "columns": [
    {
      "name": "InvoiceRevenue",
      "label": "Invoice Revenue",
      "column_type": "restricted",
      "data_type": "cds.Decimal",
      "precision": 34,
      "scale": 4,
      "expression": "CASE WHEN BillingDocumentType = 'F2' THEN NetAmount END"
    }
  ],
  "deploy": false
}
```

**"Add both InvoiceRevenue and HighValueRevenue restricted columns"**
```json
{
  "view_name": "SV_BILLING_DOC_JOINED",
  "space_id": "ZZ_BDC_HARNESS_1",
  "columns": [
    {
      "name": "InvoiceRevenue",
      "label": "Invoice Revenue",
      "column_type": "restricted",
      "data_type": "cds.Decimal",
      "precision": 34,
      "scale": 4,
      "expression": "CASE WHEN BillingDocumentType = 'F2' THEN NetAmount END"
    },
    {
      "name": "HighValueRevenue",
      "label": "High Value Revenue",
      "column_type": "restricted",
      "data_type": "cds.Decimal",
      "precision": 34,
      "scale": 4,
      "expression": "CASE WHEN NetAmount > 10000 THEN NetAmount END"
    }
  ],
  "deploy": false
}
```

## Dry-Run vs Live Deploy

- **Default** (`deploy: false`) — shows the updated CSN diff; no changes made to Datasphere
- **Live** (`deploy: true, confirm: true, acknowledge_ai: true`) — saves and deploys to Datasphere

Always show the dry-run to the user first, then ask for confirmation before deploying.

## Workflow (Best Practice)

1. Call `create_backup` (Skill 4) first to snapshot the view
2. Call `add_columns` with `deploy: false` to preview
3. Show the user the new column definitions
4. If approved, call again with `deploy: true, confirm: true, acknowledge_ai: true`

## Governance
- Only `SV_` views are supported (SQL views in Gold Propagation layer)
- Column names must be unique — skill will error if a column already exists
- Expression field references are automatically resolved to table-qualified refs from the live view CSN
