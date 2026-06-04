---
name: create-association
description: 'Add a cds.Association to an existing view in SAP Datasphere so it can navigate to a master-data view. Use when: user says "add association", "link view to", "add navigation property", "join view to master data", or wants to connect two views via a foreign key.'
argument-hint: 'Provide the source view name, target view name, and the field(s) to join on'
---

# Create Association (Skill 3)

## When to Use
- User wants to link two views via a foreign key relationship
- User says "add association", "add navigation", "link view to master data"
- User wants a view to navigate to a dimension view (e.g. company code, customer)

## What It Does
Follows the **four-step CSN protocol** precisely:
1. Adds `@ObjectModel.foreignKey.association` annotation on the FK field in `elements`
2. Adds the `cds.Association` element to `elements` with bare `on` condition
3. Appends the association ref to `query.SELECT.columns`
4. Adds a `mixin` entry to `query.SELECT` with `$projection`-prefixed source refs

The skill fetches the source view's live CSN from Datasphere, injects the association, and optionally deploys the updated view.

## Naming Rules
- Association name is derived automatically: `_` + first 9 chars of target view name
  - `SV_COMPANY_CODE` → `_SV_COMPAN`
  - `GV_CUSTOMER` → `_GV_CUSTOM`
- Source and target views must follow standard prefixes (`SV_`, `GV_`, `AM_`, etc.)

## MCP Tool

**Tool name**: `create_association`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `source_view` | string | yes | — | Technical name of the view to add the association to (e.g. `SV_BILLING_DOC_JOINED`) |
| `target_view` | string | yes | — | Technical name of the master-data view to navigate to (e.g. `GV_COMPANY_CODE`) |
| `join_fields` | array | yes | — | List of `{source_field, target_field}` pairs defining the join condition |
| `space_id` | string | no | `ZZ_BDC_HARNESS_1` | Datasphere space |
| `source_label` | string | no | same as source_view | Human-readable label for source view |
| `target_label` | string | no | same as target_view | Human-readable label for target view |
| `deploy` | boolean | no | `false` | If `true`, save and deploy; if `false`, dry-run only |
| `confirm` | boolean | no | `false` | Must be `true` to execute a live deploy |
| `acknowledge_ai` | boolean | no | `false` | Must be `true` to confirm AI-generated changes |

### `join_fields` Item Schema

```json
{ "source_field": "CompanyCode", "target_field": "CompanyCode" }
```

## Example Prompts → Tool Calls

**"Add an association from SV_BILLING_DOC_JOINED to GV_COMPANY_CODE on CompanyCode"**
```json
{
  "source_view": "SV_BILLING_DOC_JOINED",
  "target_view": "GV_COMPANY_CODE",
  "join_fields": [
    { "source_field": "CompanyCode", "target_field": "CompanyCode" }
  ],
  "space_id": "ZZ_BDC_HARNESS_1",
  "deploy": false
}
```

**"Link SV_SALES to GV_CUSTOMER on CustomerID and SalesOrg"**
```json
{
  "source_view": "SV_SALES",
  "target_view": "GV_CUSTOMER",
  "join_fields": [
    { "source_field": "CustomerID", "target_field": "CustomerID" },
    { "source_field": "SalesOrg", "target_field": "SalesOrg" }
  ],
  "space_id": "ZZ_BDC_HARNESS_1",
  "deploy": false
}
```

## Dry-Run vs Live Deploy

- **Default** (`deploy: false`) — generates the updated CSN and shows it; no changes made
- **Live** (`deploy: true, confirm: true, acknowledge_ai: true`) — saves and deploys to Datasphere

Always show the dry-run output to the user before asking for deploy confirmation.

## Governance
- Only `SV_` and `GV_` views can have associations added
- Target must be a valid dimension/master-data view
- All three flags (`deploy`, `confirm`, `acknowledge_ai`) must be `true` simultaneously to trigger a live deploy
