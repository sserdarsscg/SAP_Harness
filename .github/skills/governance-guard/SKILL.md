---
name: governance-guard
description: 'Cross-cutting governance utility automatically applied to all mutating skill calls in SAP Datasphere. NOT a directly callable skill — it runs automatically. Understand this when: debugging why a deploy was rejected, understanding what validations are enforced, or checking what audit logs are written.'
argument-hint: 'This module is not invoked directly. It wraps all mutating skill calls. To pass governance, set confirm=true and acknowledge_ai=true.'
---

# Governance Guard (Cross-Cutting Utility)

## Overview
`governance_guard` is **not a callable skill** — it is a mandatory validation layer that runs automatically before any mutating skill executes. It enforces space rules, naming constraints, and audit logging for every tool call that modifies Datasphere.

> Entry point: `datasphere-agent/agent/governance_guard.py`  
> Thin alias: `datasphere-agent/skills/governance_guard.py` (backward-compatibility wrapper)

---

## When It Runs
Governance Guard intercepts **all mutating skill calls** before execution:

| Skill | Guarded? |
|-------|----------|
| `create_view` | ✅ yes |
| `share_to_space` | ✅ yes |
| `create_association` | ✅ yes |
| `create_backup` | ✅ yes |
| `create_sql_view_with_association` | ✅ yes |
| `add_calculated_fields` | ✅ yes |
| `read_view`, `list_views`, `list_spaces` | ❌ read-only, not guarded |

---

## Validations Enforced

### 1. Input Type Validation
- All parameters must be correct types (string, boolean, etc.)
- Malformed input is rejected with a descriptive error before any CLI call

### 2. Space Rules
| Skill | Allowed Space(s) |
|-------|-----------------|
| `create_view` | `ZZ_BDC_HARNESS_1` only |
| `create_association` | `ZZ_BDC_HARNESS_1` only |
| `create_sql_view_with_association` | `ZZ_BDC_HARNESS_1` only |
| `add_calculated_fields` | `ZZ_BDC_HARNESS_1` only |
| `create_backup` | `ZZ_BDC_HARNESS_1` only |
| `share_to_space` | source = `ZZ_BDC_HARNESS_1`, target = `ZZ_BDC_HARNESS_2` |

Any request targeting an unlisted space is rejected.

### 3. SQL-Only Constraint (`create_view`)
- `create_view` only accepts views with `SV_` prefix (SQL Views)
- Graphical views (`GV_`), Analytic Models (`AM_`), etc. must not be created via this skill

### 4. No-JOIN in Parameters
- Free-text SQL or query parameters must not contain raw `JOIN` keywords
- Prevents SQL injection-style abuse of the `sql`/`query` parameters

### 5. Confirmation Gate (Deploy)
All mutating skills require **all three** of the following to be `true` simultaneously before any live deploy is executed:

| Flag | Purpose |
|------|---------|
| `deploy` | Intent to deploy |
| `confirm` | Human confirms the operation |
| `acknowledge_ai` | User acknowledges AI-generated output |

If any flag is missing or `false`, the skill executes in **dry-run mode** only.

---

## Audit Logging

Every skill call (pass or reject) is appended to:
```
datasphere-agent/logs/governance_audit.jsonl
```

Each log entry is a JSON object with:
- `timestamp` — ISO 8601 UTC
- `skill_name` — name of the invoked skill
- `params` — sanitized input parameters
- `status` — `"allowed"` | `"rejected"` | `"dry_run"`
- `message` — human-readable reason

---

## How to Pass Governance (Checklist)

For a **live deploy** to succeed:

```json
{
  "deploy": true,
  "confirm": true,
  "acknowledge_ai": true,
  "space_id": "ZZ_BDC_HARNESS_1"
}
```

For a **dry-run** (default safe mode), omit or set `deploy: false`.

---

## Debugging Rejections

If a skill call is rejected, check:
1. `logs/governance_audit.jsonl` — look at the last entry's `message` field
2. Is `space_id` set to an allowed value?
3. Are all three deploy flags (`deploy`, `confirm`, `acknowledge_ai`) set to `true`?
4. Does the view name start with `SV_` for `create_view`?
5. Does any parameter contain a raw `JOIN` keyword?
