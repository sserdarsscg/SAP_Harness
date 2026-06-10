# SKILL.md — Skill 7: Create Task Chain

## Skill Identity

| Attribute | Value |
|-----------|-------|
| Skill ID | `create_task_chain` |
| MCP Tool Name | `create_task_chain` |
| Python Module | `datasphere-agent/skills/create_task_chain.py` |
| Registered via | `register_skill("create_task_chain", execute)` |

---

## Purpose

Creates a **Task Chain** (`TC_`) in SAP Datasphere that wraps an existing Transformation Flow (`TF_`):

1. Generates the Task Chain CSN in the `taskchains` format (not `definitions`)
2. Optionally deploys it to Datasphere via the CLI

The Task Chain contains exactly:
- A **START** node (id 0)
- A **TASK** node (id 1) that executes the Transformation Flow via `applicationId: "TRANSFORMATION_FLOWS"` and `activity: "EXECUTE"`

---

## Naming Convention

| Input | Derived Name |
|-------|-------------|
| `TF_BILLING_DOC_JOINED` | `TC_TF_BILLING_DOC_JOINED` |
| `TF_TEST_COPY` | `TC_TF_TEST_COPY` |
| `TF_SALES_AGG` | `TC_TF_SALES_AGG` |

**Rule**: `tc_name = "TC_" + tf_name`

> **Note**: This intentionally deviates from the general project naming convention (`TC_<MD/TD>_<NAME>`) to ensure a **1:1 traceable relationship** between each Task Chain and its source Transformation Flow. The `TF_` segment within the name makes the dependency explicit and prevents naming collisions.

Use the `tc_name` override parameter to supply a fully custom name when required.

---

## Trigger Phrases

This skill is invoked when the user says something like:

| Example Phrase | Why It Matches |
|----------------|----------------|
| "Create a task chain for TF_BILLING_DOC_JOINED" | `task chain` keyword |
| "Wrap transformation flow in a task chain" | `task chain`, `transformation flow` |
| "Create TC_ for TF_SALES_AGG" | `tc_` keyword |
| "Schedule transformation flow TF_TEST" | `task chain` / `schedule` |
| "Create orchestration for TF_BILLING" | `task chain` intent |

---

## Parameters

| Parameter | Type | Default | Required | Description |
|-----------|------|---------|----------|-------------|
| `tf_name` | string | — | **Yes** | Technical name of the Transformation Flow to execute (must start with `TF_`) |
| `space_id` | string | `ZZ_BDC_HARNESS_1` | No | Datasphere space ID |
| `tc_name` | string | `TC_<tf_name>` | No | Override the generated Task Chain name (must start with `TC_`) |
| `folder` | string | `null` | No | Folder assignment for `_meta.dependencies.folderAssignment` |
| `deploy` | bool | `false` | No | `true` = deploy to Datasphere |
| `run` | bool | `false` | No | `true` = execute TC immediately after deploy (requires `deploy=true`) |
| `confirm` | bool | `false` | No | Human confirmation (required for deploy) |
| `acknowledge_ai` | bool | `false` | No | AI literacy acknowledgement (required for deploy) |

**Name derivation**: if `tf_name = TF_BILLING_DOC_JOINED`, then:
- `tc_name = TC_TF_BILLING_DOC_JOINED`

---

## Response Structure

### Dry-run (`deploy=false`)

```json
{
  "status": "dry_run",
  "tf_name": "TF_BILLING_DOC_JOINED",
  "tc_name": "TC_TF_BILLING_DOC_JOINED",
  "space_id": "ZZ_BDC_HARNESS_1",
  "folder": null,
  "tc_csn": { ... },
  "next_step": "Review the CSN above. To deploy, call again with deploy=true, confirm=true, acknowledge_ai=true."
}
```

### Deployed (`deploy=true`)

```json
{
  "status": "deployed",
  "tf_name": "TF_BILLING_DOC_JOINED",
  "tc_name": "TC_TF_BILLING_DOC_JOINED",
  "space_id": "ZZ_BDC_HARNESS_1",
  "results": {
    "task_chain": { "status": "success", "message": "..." }
  }
}
```

### Deployed and Running (`deploy=true, run=true`)

```json
{
  "status": "deployed_and_running",
  "tf_name": "TF_BILLING_DOC_JOINED",
  "tc_name": "TC_TF_BILLING_DOC_JOINED",
  "space_id": "ZZ_BDC_HARNESS_1",
  "results": {
    "task_chain": { "status": "success", "message": "..." },
    "run": { "status": "success", "message": "..." }
  }
}
```

---

## Deployment Workflow

```
Step 1: Derive tc_name from tf_name (TC_ + tf_name)

Step 2: Build Task Chain CSN
  - START node (id: 0)
  - TASK node (id: 1, applicationId: "TRANSFORMATION_FLOWS", activity: "EXECUTE", objectId: tf_name)
  - Link: 0 → 1 (statusRequired: "ANY")
  - Options: {layout: "VERTICAL"}
  - _meta.dependencies.folderAssignment only if folder param provided

Step 3 (if deploy=true):
  datasphere objects task-chains create --space <space> --technical-name <tc_name> --file-path <tmp.json>

Step 4 (if run=true):
  datasphere objects task-chains run --space <space> --technical-name <tc_name>
```

---

## Naming Convention

Follows project naming conventions (see `.github/instructions/naming-conventions.instructions.md`):

| Object | Prefix | Layer |
|--------|--------|-------|
| Task Chain | `TC_` | Any |

> The Task Chain uses `MD` for master data flows and `TD` for transactional flows in the general convention.
> This skill uses `TC_<TF_NAME>` to ensure 1:1 correspondence with the Transformation Flow.

---

## Generated CSN Example

### Task Chain (`TC_TF_BILLING_DOC_JOINED`)

```json
{
  "version": { "csn": "1.0" },
  "meta": { "creator": "CDS Compiler v1.19.2" },
  "$version": "1.0",
  "taskchains": {
    "TC_TF_BILLING_DOC_JOINED": {
      "kind": "sap.dwc.taskChain",
      "@EndUserText.label": "TC_TF_BILLING_DOC_JOINED",
      "nodes": [
        { "id": 0, "type": "START" },
        {
          "id": 1,
          "type": "TASK",
          "taskIdentifier": {
            "applicationId": "TRANSFORMATION_FLOWS",
            "activity": "EXECUTE",
            "objectId": "TF_BILLING_DOC_JOINED"
          },
          "ignoreError": false
        }
      ],
      "links": [
        {
          "startNode": { "nodeId": 0, "statusRequired": "ANY" },
          "endNode": { "nodeId": 1 },
          "id": 0
        }
      ],
      "options": { "layout": "VERTICAL" },
      "schemaVersion": 2,
      "_meta": {
        "dependencies": {
          "folderAssignment": "Folder_KJTYBRLA"
        }
      }
    }
  }
}
```

> `_meta.dependencies` is omitted entirely when no `folder` parameter is supplied.

---

## Error Cases

| Error | Cause | Resolution |
|-------|-------|------------|
| `tf_name must start with TF_` | Invalid TF name provided | Ensure name starts with `TF_` |
| `tc_name must start with TC_` | Invalid override name | Ensure override starts with `TC_` |
| `run=True requires deploy=True` | run without deploy | Set `deploy=true` alongside `run=true` |
| `Deploy blocked: set confirm=true and acknowledge_ai=true` | Safety guard not satisfied | Pass both flags |
| `Space not allowed: create_task_chain only permitted in ZZ_BDC_HARNESS_1` | Wrong space | Use `ZZ_BDC_HARNESS_1` |
| `datasphere CLI not found` | CLI not installed | Run `npm install -g @sap/datasphere-cli` |

---

## Usage Examples

```python
# Dry-run (safe, default)
result = execute({
    "tf_name": "TF_BILLING_DOC_JOINED",
    "space_id": "ZZ_BDC_HARNESS_1"
})

# With folder assignment
result = execute({
    "tf_name": "TF_BILLING_DOC_JOINED",
    "folder": "Folder_KJTYBRLA"
})

# Custom tc_name override
result = execute({
    "tf_name": "TF_BILLING_DOC_JOINED",
    "tc_name": "TC_TD_BILLING_JOINED"
})

# Deploy to Datasphere
result = execute({
    "tf_name": "TF_BILLING_DOC_JOINED",
    "deploy": True,
    "confirm": True,
    "acknowledge_ai": True
})

# Deploy and immediately run via CLI
result = execute({
    "tf_name": "TF_BILLING_DOC_JOINED",
    "deploy": True,
    "run": True,
    "confirm": True,
    "acknowledge_ai": True
})
```
