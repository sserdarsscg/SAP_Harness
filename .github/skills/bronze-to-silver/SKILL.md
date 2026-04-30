---
name: bronze-to-silver
description: 'Generate SQL transformations that move data from a raw/landing (bronze) layer to a cleansed/harmonized (silver) layer in SAP Datasphere. Use when: user says "bronze to silver", "raw to cleansed", "landing to harmonized", or asks about layer transformations.'
argument-hint: 'Provide the table name, source layer, and target layer'
---

# Bronze to Silver Transformation

## When to Use
- User wants to move data from bronze (raw/landing) to silver (cleansed/harmonized) layer
- User mentions "bronze to silver", "raw to cleansed", "landing to harmonized"
- User asks to transform or cleanse raw data in SAP Datasphere

## What It Does
Generates an `INSERT INTO ... SELECT` SQL statement that:
1. Reads from the source (bronze) layer table
2. Applies basic cleansing (e.g. `TRIM`, null filtering)
3. Adds a silver-layer timestamp
4. Writes to the target (silver) layer table

## Naming Conventions (MANDATORY)

When generating bronze-to-silver transformations, object names MUST follow these rules:

| Object | Prefix | Pattern | Example |
|--------|--------|---------|---------|
| Bronze Space | `10_BL_` | `10_BL_<SOURCE_NAME>` | `10_BL_S4_FSX800` |
| Silver Space | `20_SL_` | `20_SL_<SOURCE_NAME>` | `20_SL_S4_FSX800` |
| Replication Flow | `RF_` | `RF_<SOURCE>_<TARGET>_<NAME>_<DELTA/FULL>` | `RF_S4_DSP_FINANCE_FULL` |
| Data Flow (ELT) | `DF_` | `DF_<SOURCE>_<TARGET>_<NAME>` | `DF_S4_DSP_CUSTOMERS` |
| Transformation Flow | `TF_` | `TF_<NAME>` | `TF_SALES_CALC` |
| Local Table | `TL_` | `TL_<NAME>` | `TL_CUSTOMERS` |
| Graphical View | `GV_` | `GV_<NAME>` | `GV_CUSTOMERS` |

**Rules**:
- Bronze layer is ONLY inbound into Datasphere
- Silver/Gold layers are ONLY outbound from Datasphere
- Data Flows: No transformation logic allowed
- Transformation Flows: Only internal (GV/SQL → Local Table)
- ALWAYS uppercase, underscore separator

See full naming rules: [naming-conventions.instructions.md](../../instructions/naming-conventions.instructions.md)

## MCP Tool

**Tool name**: `bronze_to_silver`

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `table_name` | string | yes | — | Name of the table (e.g. CUSTOMER, ORDERS) |
| `source_layer` | string | no | `bronze` | Source schema/layer |
| `target_layer` | string | no | `silver` | Target schema/layer |

## Procedure

1. Call the `bronze_to_silver` MCP tool with the table name
2. In **mock mode**: returns a dry-run SQL preview
3. In **live mode**: returns a dry-run SQL (CLI does not execute SQL directly)

## Example

```
User: "Move the CUSTOMER table from bronze to silver"
→ Tool call: bronze_to_silver(table_name="CUSTOMER", source_layer="10_BL", target_layer="20_SL")
→ Returns: INSERT INTO 20_SL.CUSTOMER SELECT ... FROM 10_BL.CUSTOMER
```

## Source

- Skill implementation: [bronze_to_silver.py](../../datasphere-agent/skills/bronze_to_silver.py)
- SQL generator: `generate_sql(table_name, source_layer, target_layer)`
