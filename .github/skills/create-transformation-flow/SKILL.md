# SKILL.md — Skill 6: Create Transformation Flow

## Skill Identity

| Attribute | Value |
|-----------|-------|
| Skill ID | `create_transformation_flow` |
| MCP Tool Name | `create_transformation_flow` |
| Python Module | `datasphere-agent/skills/create_transformation_flow.py` |
| Registered via | `register_skill("create_transformation_flow", execute)` |

---

## Purpose

Creates an **aggregated data pipeline** in SAP Datasphere from an existing SQL View:

1. **`TL_<NAME>_AGG`** — Local Table to receive the aggregated rows
2. **`TF_<NAME>`** — Transformation Flow (FULL load, no delta): source view → local table

The skill auto-classifies columns from the source view into:
- **Dimensions** (`GROUP BY`) — `cds.String`, `cds.Date`, `cds.Timestamp`, etc.
- **Measures** (`SUM`) — `cds.Decimal`, `cds.Integer`, `cds.Int32`, `cds.Int64`, `cds.Double`

Columns listed in `exclude_columns` (plus default exclusions) are dropped entirely.

---

## Trigger Phrases

This skill is invoked when the user says something like:

| Example Phrase | Why It Matches |
|----------------|----------------|
| "Create a transformation flow on SV_BILLING_DOC_JOINED" | `transformation flow` keyword |
| "Build aggregated flow without billing document and items" | `without`, `billing document`, `aggregated` |
| "Create TF_BILLING_DOC_JOINED without document-level keys" | `create`, `tf_` |
| "Aggregate billing data by company code and material" | `aggregated`, `flow` |

---

## Column Auto-Classification

| CDS Type | Classification | SQL Action |
|----------|---------------|------------|
| `cds.String` | Dimension | `GROUP BY` |
| `cds.Date` | Dimension | `GROUP BY` |
| `cds.Timestamp` | Dimension | `GROUP BY` |
| `cds.Decimal` | Measure | `SUM(col)` |
| `cds.Integer` | Measure | `SUM(col)` |
| `cds.Int32` | Measure | `SUM(col)` |
| `cds.Int64` | Measure | `SUM(col)` |
| `cds.Double` | Measure | `SUM(col)` |

**Default exclusions**: `BillingDocument`, `BillingDocumentItem`
(excluded regardless of type — they are transaction-level keys not useful post-aggregation)

---

## Parameters

| Parameter | Type | Default | Required | Description |
|-----------|------|---------|----------|-------------|
| `source_view` | string | `SV_BILLING_DOC_JOINED` | No | Source SQL View (`SV_` prefix expected) |
| `space_id` | string | `ZZ_BDC_HARNESS_1` | No | Datasphere space ID |
| `exclude_columns` | array | `[]` | No | Additional columns to exclude |
| `tf_name` | string | `TF_<base>` | No | Override Transformation Flow name |
| `tl_name` | string | `TL_<base>_AGG` | No | Override Local Table name |
| `deploy` | bool | `false` | No | `true` = deploy to Datasphere |
| `confirm` | bool | `false` | No | Human confirmation (required for deploy) |
| `acknowledge_ai` | bool | `false` | No | AI literacy acknowledgement (required for deploy) |

**Name derivation**: if `source_view = SV_BILLING_DOC_JOINED`, then:
- `base = BILLING_DOC_JOINED`
- `tf_name = TF_BILLING_DOC_JOINED`
- `tl_name = TL_BILLING_DOC_JOINED_AGG`

---

## Response Structure

### Dry-run (`deploy=false`)

```json
{
  "status": "dry_run",
  "source_view": "SV_BILLING_DOC_JOINED",
  "space_id": "ZZ_BDC_HARNESS_1",
  "excluded_columns": ["BILLINGDOCUMENT", "BILLINGDOCUMENTITEM"],
  "tf_name": "TF_BILLING_DOC_JOINED",
  "tl_name": "TL_BILLING_DOC_JOINED_AGG",
  "dimensions": ["CompanyCode", "SalesOrganization", ...],
  "measures": ["NetAmount", "TaxAmount", "GrossAmount", ...],
  "tl_csn": { ... },
  "tf_csn": { ... },
  "next_step": "Review the CSN above. To deploy, call again with deploy=true, confirm=true, acknowledge_ai=true."
}
```

### Deployed (`deploy=true`)

```json
{
  "status": "deployed",
  "tf_name": "TF_BILLING_DOC_JOINED",
  "tl_name": "TL_BILLING_DOC_JOINED_AGG",
  "source_view": "SV_BILLING_DOC_JOINED",
  "dimensions": [...],
  "measures": [...],
  "columns_deployed": 23,
  "results": {
    "local_table": { "status": "success", "message": "..." },
    "transformation_flow": { "status": "success", "message": "..." }
  }
}
```

---

## Deployment Workflow

```
Step 1: Read source view CSN from Datasphere
        datasphere objects views read --space <space> --technical-name <SV_>

Step 2: Auto-classify columns → dimensions / measures

Step 3: Build TL_ CSN (Local Table)

Step 4: Build TF_ CSN (Transformation Flow with GROUP BY + SUM)

Step 5 (if deploy=true):
  5a: datasphere objects local-tables create --space <space> --technical-name TL_ --file-path ...
  5b: datasphere objects transformation-flows create --space <space> --technical-name TF_ --file-path ...
```

---

## Naming Convention

Follows project naming conventions (see `.github/instructions/naming-conventions.instructions.md`):

| Object | Prefix | Layer |
|--------|--------|-------|
| Local Table | `TL_` | Silver/Gold |
| Transformation Flow | `TF_` | Silver/Gold |

The Transformation Flow is **internal**: source and target are both inside Datasphere.  
**Do not use** `RF_` (Replication Flow) or `DF_` (Data Flow) for this use case.

---

## Generated CSN Examples

### Local Table (`TL_BILLING_DOC_JOINED_AGG`)

```json
{
  "definitions": {
    "TL_BILLING_DOC_JOINED_AGG": {
      "kind": "entity",
      "@EndUserText.label": "Tl Billing Doc Joined Agg",
      "elements": {
        "CompanyCode": { "type": "cds.String", "key": true, "length": 4, "@EndUserText.label": "Company Code" },
        "NetAmount": { "type": "cds.Decimal", "precision": 16, "scale": 3, "@EndUserText.label": "Net Amount" }
      }
    }
  }
}
```

### Transformation Flow (`TF_BILLING_DOC_JOINED`)

```json
{
  "definitions": {
    "TF_BILLING_DOC_JOINED": {
      "kind": "entity",
      "@EndUserText.label": "Tf Billing Doc Joined",
      "@DataWarehouse.taskType": "TF",
      "@DataWarehouse.etlLoad": {
        "sourceEntity": "SV_BILLING_DOC_JOINED",
        "targetEntity": "TL_BILLING_DOC_JOINED_AGG",
        "loadType": "FULL"
      },
      "query": {
        "SELECT": {
          "from": { "ref": ["SV_BILLING_DOC_JOINED"] },
          "columns": [
            { "ref": ["SV_BILLING_DOC_JOINED", "CompanyCode"] },
            { "xpr": [{"func": "SUM", "args": [{"ref": ["SV_BILLING_DOC_JOINED", "NetAmount"]}]}], "as": "NetAmount" }
          ],
          "groupBy": [
            { "ref": ["SV_BILLING_DOC_JOINED", "CompanyCode"] }
          ]
        }
      }
    }
  }
}
```

---

## Error Cases

| Error | Cause | Resolution |
|-------|-------|------------|
| `Cannot read view '...'` | View not found in space | Check view name and space ID |
| `No elements in '...'` | View CSN has empty elements | Verify source view is deployed |
| `No dimension columns remain after exclusions` | All columns excluded or are measures | Reduce `exclude_columns` |
| `Deploy blocked: set confirm=true and acknowledge_ai=true` | Safety guard not satisfied | Pass both flags |

---

## Usage Examples

```python
# Dry-run (safe, default)
result = execute({
    "source_view": "SV_BILLING_DOC_JOINED",
    "space_id": "ZZ_BDC_HARNESS_1"
})

# Exclude additional column
result = execute({
    "source_view": "SV_BILLING_DOC_JOINED",
    "exclude_columns": ["AccountingDocument"]
})

# Deploy to Datasphere
result = execute({
    "source_view": "SV_BILLING_DOC_JOINED",
    "deploy": True,
    "confirm": True,
    "acknowledge_ai": True
})
```
