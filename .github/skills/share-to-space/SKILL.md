---
name: share-to-space
description: 'Share views from one SAP Datasphere space to another. Use when: user says "share view", "share to space", "share object to another space". Updates @DataWarehouse.shareTo CSN annotation via the datasphere CLI.'
argument-hint: 'Provide the view names and target space(s)'
---

# Share to Space

## When to Use
- User wants to share one or more views to another space
- User says "share view", "share to space", "share object"
- User wants to make views accessible from a different space

## What It Does
1. Reads the current CSN definition of each view from the source space
2. Adds/merges `@DataWarehouse.shareTo` annotation with the target space(s)
3. Writes updated CSN to a temporary file
4. Calls `datasphere objects views update` via the CLI to persist the change
5. Returns success/failure status for each view

## Prerequisites
- Views must be **deployed** before they can be shared
- User must have DW Modeler role or equivalent permissions
- Source space must contain the views being shared

## CSN Annotation

Sharing is controlled by the `@DataWarehouse.shareTo` annotation at the entity level:

```json
{
  "definitions": {
    "GV_BILLING_DOC_ITEM": {
      "kind": "entity",
      "@DataWarehouse.shareTo": ["ZZ_BDC_HARNESS_2"],
      "@EndUserText.label": "Billing Document Item",
      ...
    }
  }
}
```

Multiple target spaces can be specified:
```json
"@DataWarehouse.shareTo": ["ZZ_BDC_HARNESS_2", "ZZ_BDC_HARNESS_3"]
```

The skill merges new targets with existing ones (idempotent).

## MCP Tool

**Tool name**: `share_to_space`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `view_names` | array[string] | yes | — | List of view technical names to share |
| `target_spaces` | array[string] | yes | — | List of target space IDs |
| `source_space` | string | no | `ZZ_BDC_HARNESS_1` | Space where views reside |

### Example Call

```json
{
  "name": "share_to_space",
  "arguments": {
    "view_names": [
      "GV_BILLING_DOC_ITEM",
      "GV_BILLING_DOC_HEADER",
      "GV_OPS_ACCT_DOC_ITEM",
      "GV_CHART_OF_ACCOUNT",
      "GV_DOC_ITEM"
    ],
    "target_spaces": ["ZZ_BDC_HARNESS_2"],
    "source_space": "ZZ_BDC_HARNESS_1"
  }
}
```

## CLI Commands Used

| Step | Command |
|------|---------|
| Read view | `datasphere objects views read --space <SPACE> --technical-name <NAME>` |
| Update view | `datasphere objects views update --space <SPACE> --technical-name <NAME> --file-path <CSN_FILE> --save-anyway` |

## Naming Conventions

All view names follow the standard naming conventions:
- Graphical Views: `GV_<NAME>`
- SQL Views: `SV_<NAME>`
- Analytic Models: `AM_<NAME>`

See full naming rules: [naming-conventions.instructions.md](../../instructions/naming-conventions.instructions.md)

## Available Spaces

| Space ID | Description |
|----------|-------------|
| `ZZ_BDC_HARNESS_1` | Default source space |
| `ZZ_BDC_HARNESS_2` | Default target space |

## Error Handling

- If a view cannot be read from the source space, it is skipped with an error message
- If the update fails (e.g. permissions), the error is reported per view
- The skill is idempotent — re-sharing an already-shared view is safe (merges targets)
