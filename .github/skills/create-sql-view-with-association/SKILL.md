---
name: create-sql-view-with-association
description: 'Create an SV_ SQL View that INNER JOINs two billing/transactional tables in SAP Datasphere. Use when: user says "create SQL view", "join two tables", "create billing view", "inner join tables", "create a joined view", or wants to combine columns from two source tables into a single SQL view.'
argument-hint: 'Provide the view name, two source table names, and the field to join on. Defaults target billing document tables.'
---

# Create SQL View with Association (Skill)

## When to Use
- User wants to create a new `SV_` SQL View that combines columns from two source tables
- User says "create SQL view", "join two tables", "inner join tables", "create billing view"
- User wants a queryable view over billing documents (header + line items)
- User needs a single flat view merging two related datasets via a shared key

## What It Does
1. Reads the live CSN schema of both source tables from Datasphere via CLI
2. Merges columns: join field taken from table1 only; duplicate columns from table2 are skipped
3. Builds a CSN definition with an `INNER JOIN` on the specified join field
4. Writes the CSN to a temp file
5. Optionally deploys the new view to Datasphere

> **Important**: `SV_` SQL Views do **NOT** support `cds.Association` natively.  
> Associations must be added on a `GV_` (Graphical View) layer above this SQL view.  
> The `include_association` flag is experimental and not recommended for production.

## Naming Rules
- View name must use the `SV_` prefix: e.g. `SV_BILLING_DOC_JOINED`
- Source tables follow source-system naming (no prefix enforcement)
- Only valid in the **Gold Propagation** layer (`30_GP_`)
- Do not place `SV_` views in Bronze or Silver spaces

## MCP Tool

**Tool name**: `create_sql_view_with_association`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `view_name` | string | no | `SV_BILLING_DOC_JOINED` | Technical name of the new SQL view (must start with `SV_`) |
| `source_table_1` | string | no | `VR1_BILLING_DOC_ITEM_TD_001` | First source table (e.g. line items) |
| `source_table_2` | string | no | `VR1_BILLING_DOC_TD_001` | Second source table (e.g. header) |
| `join_field` | string | no | `BillingDocument` | Field name used in the INNER JOIN condition |
| `association_field` | string | no | `CompanyCode` | Field used for the optional association (experimental) |
| `master_data_view` | string | no | `SV_COMPANYCODE` | Target master-data view for the optional association |
| `master_data_key` | string | no | `Company_Code` | Key field on the master-data view |
| `space_id` | string | no | `ZZ_BDC_HARNESS_1` | Datasphere space ID |
| `deploy` | boolean | no | `false` | If `true`, saves and deploys the view |
| `confirm` | boolean | no | `false` | Must be `true` to execute a live deploy |
| `acknowledge_ai` | boolean | no | `false` | Must be `true` to confirm AI-generated changes |
| `include_association` | boolean | no | `false` | Experimental: attempt to embed `cds.Association` in the SQL view |

## Example Prompts → Tool Calls

**"Create a SQL view joining billing line items and header on BillingDocument"**
```json
{
  "view_name": "SV_BILLING_DOC_JOINED",
  "source_table_1": "VR1_BILLING_DOC_ITEM_TD_001",
  "source_table_2": "VR1_BILLING_DOC_TD_001",
  "join_field": "BillingDocument",
  "space_id": "ZZ_BDC_HARNESS_1",
  "deploy": false
}
```

**"Create and deploy SV_SALES_JOINED joining SALES_ITEMS and SALES_HEADER on SalesOrder"**
```json
{
  "view_name": "SV_SALES_JOINED",
  "source_table_1": "SALES_ITEMS",
  "source_table_2": "SALES_HEADER",
  "join_field": "SalesOrder",
  "space_id": "ZZ_BDC_HARNESS_1",
  "deploy": true,
  "confirm": true,
  "acknowledge_ai": true
}
```

## Dry-Run vs Live Deploy

- **Default** (`deploy: false`) — generates the CSN and shows it; no changes made to Datasphere
- **Live** (`deploy: true, confirm: true, acknowledge_ai: true`) — creates and deploys the view

Always show the dry-run CSN output to the user before requesting deploy confirmation.

## Governance
- Space is locked to `ZZ_BDC_HARNESS_1`; requests for other spaces are rejected
- All three flags (`deploy`, `confirm`, `acknowledge_ai`) must be `true` simultaneously to trigger a live deploy
- Duplicate columns (same name in both tables) are silently dropped from table2 to prevent CSN conflicts
- `include_association: true` is **experimental** — SV_ views have no native association support; use `create_association` skill on a GV_ layer instead
