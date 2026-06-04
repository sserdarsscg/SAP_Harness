---
name: create-backup
description: 'Create a logical backup of an existing SAP Datasphere view before modifying it. Use when: user says "backup view", "take a backup", "save a copy before changing", or any modification skill should back up the view first. Generates a timestamped backup name and optionally saves a copy of the CSN.'
argument-hint: 'Provide the view or object name to back up'
---

# Create Backup (Skill 4)

## When to Use
- User says "backup", "take a backup", "save a copy before changing"
- **Any destructive or modifying operation on a view should call this skill first**
- User wants to preserve the current state of a view before adding columns, associations, or other changes

## What It Does
1. Generates a timestamped backup name: `<OBJECT_NAME>_<YYYYMMDD>_<HHMM>`
2. If the current CSN of the view is provided, saves a copy under the backup name in the `Back-up/` folder
3. Does NOT modify the original view — read-only operation on the live object

## Naming Convention
Backup names follow the pattern: `<ORIGINAL_NAME>_<YYYYMMDD>_<HHMM>`

| Original | Backup Example |
|----------|---------------|
| `SV_BILLING_DOC_JOINED` | `SV_BILLING_DOC_JOINED_20260603_1430` |
| `GV_CUSTOMERS` | `GV_CUSTOMERS_20260603_1430` |

- Object name is normalized: if it already has a `XX_` prefix, it is kept as-is
- Timestamp uses local time at moment of backup

## MCP Tool

**Tool name**: `create_backup`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `object_name` | string | yes | — | Technical name of the view/object to back up (e.g. `SV_BILLING_DOC_JOINED`) |
| `space_id` | string | no | `ZZ_BDC_HARNESS_1` | Datasphere space |
| `csn` | object | no | — | The current CSN definition (if provided, saves a copy to `Back-up/`) |
| `timestamp` | string | no | current time | Override timestamp in `YYYYMMDD_HHMM` format |

## Example Prompts → Tool Calls

**"Back up SV_BILLING_DOC_JOINED before I change it"**
```json
{
  "object_name": "SV_BILLING_DOC_JOINED",
  "space_id": "ZZ_BDC_HARNESS_1"
}
```

**Expected output:**
```
Backup name: SV_BILLING_DOC_JOINED_20260603_1430
Saved to: datasphere-agent/Back-up/SV_BILLING_DOC_JOINED_20260603_1430.json
```

## Integration with Other Skills

When Skills 3, 5, or any view-modifying skill is used:
1. Call `create_backup` first to record the current state
2. Then call the modifying skill
3. If the modification fails, the backup file can be used to restore

## Important Notes
- Backup is **local only** — it is NOT deployed to Datasphere
- The `Back-up/` folder is in `datasphere-agent/Back-up/`
- Backup files follow the same CSN format as the live view
