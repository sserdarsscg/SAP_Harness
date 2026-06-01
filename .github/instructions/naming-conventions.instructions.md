---
applyTo: "**"
description: 'SAP Datasphere naming conventions. MUST be followed for ALL object names: spaces, tables, views, flows, connections, models. Use when: creating, validating, or refactoring any Datasphere object name.'
---

# SAP Datasphere Naming Conventions

## General Rules
- Use UPPERCASE for all prefixes
- Use underscore `_` as separator
- Do not shorten prefixes
- Names must be descriptive but concise
- Respect inbound vs outbound direction rules

## Spaces / Data Objects

| Layer | Prefix | Pattern | Example |
|-------|--------|---------|---------|
| Bronze / Inbound | `10_BL_` | `10_BL_<SOURCE_NAME>` | `10_BL_S4_FSX800` |
| Silver / Harmonisation | `20_SL_` | `20_SL_<SOURCE_NAME>` | `20_SL_S4_FSX800` |
| Gold / Propagation | `30_GP_` | `30_GP_<FUNCTIONAL_AREA>` | `30_GP_O2C` |
| Gold / Reporting | `40_GR_` | `40_GR_<FUNCTIONAL_AREA>` | `40_GR_O2C` |

**Rule**: Bronze is ONLY inbound into Datasphere.

## Tables

| Type | Prefix | Pattern | Example |
|------|--------|---------|---------|
| Remote Tables | — | Follow source system naming | — |
| Local Tables (Replication Flow) | — | Follow source system naming | — |
| Local Tables (Manual/Custom) | `TL_` | `TL_<NAME>` | `TL_CUSTOMERS` |

## Flows

| Type | Prefix | Pattern | Example |
|------|--------|---------|---------|
| Replication Flow | `RF_` | `RF_<SOURCE>_<TARGET>_<NAME>_<DELTA/FULL>` | `RF_S4_DSP_FINANCE_FULL` |
| Data Flow (ELT) | `DF_` | `DF_<SOURCE>_<TARGET>_<NAME>` | `DF_S4_DSP_CUSTOMERS` |
| Transformation Flow | `TF_` | `TF_<NAME>` | `TF_SALES_CALC` |

**Rules**:
- Replication Flow: Bronze → ONLY inbound into Datasphere; Silver/Gold → ONLY outbound from Datasphere
- Data Flow: No transformation logic allowed. Name should be descriptive of the source dataset being loaded (ELT paradigm)
- Transformation Flow: Processes internal data only — between GV_ or SQL View to a Local Table

## Models & Views

| Type | Prefix | Pattern | Layer |
|------|--------|---------|-------|
| Entity Relationship Model | `ER_` | `ER_<NAME>` | Any |
| Graphical View | `GV_` | `GV_<NAME>` | Silver/Gold |
| SQL View | `SV_` | `SV_<NAME>` | Gold Propagation ONLY |
| Analytic Model | `AM_` | `AM_<NAME>` | Gold Reporting |

**Rules**:
- SQL Views: ONLY in Gold Propagation layer, even for simple cases. For complex calculations — aggregations on large datasets or KPIs that cannot be done with a Graphical View. Can be persisted for performance.
- Graphical Views: For associations & hierarchies. To create semantic data objects (e.g. customer) from SAP tables where no CDS-view is available (Silver layer). For on-the-fly aggregations and KPI calculations (Gold layers).
- Analytic Models: RKF, CKF, exception aggregation, consumed by reporting tools

## Orchestration & Security

| Type | Prefix | Pattern | Example |
|------|--------|---------|---------|
| Task Chain | `TC_` | `TC_<MD/TD>_<NAME>` | `TC_MD_SALES` |
| Data Access Control | `DC_` | `DC_<NAME>` | `DC_REGION` |
| Intelligent Lookup | `IL_` | `IL_<NAME>` | `IL_COUNTRY` |

**Rules**:
- Task Chain: Use `MD` for master data flows, `TD` for transactional data flows.
- Intelligent Lookup: Used for harmonization of data across sources.

## Connections

| Direction | Prefix | Pattern |
|-----------|--------|---------|
| Inbound | `CN_IN_` | `CN_IN_<SOURCE>_<CONNECTIONTYPE>_<NAME>` |
| Outbound | `CN_OT_` | `CN_OT_<TARGET>_<CONNECTIONTYPE>_<NAME>` |
| Both | `CN_IO_` | `CN_IO_<CONNECTIONTYPE>_<NAME>` |

## Business / Semantic Models

| Type | Prefix | Pattern |
|------|--------|---------|
| Dimension | `DI_` | `DI_<NAME>` |
| Fact | `FA_` | `FA_<NAME>` |
| Fact Model | `FM_` | `FM_<NAME>` |
| Consumption Model | `CM_` | `CM_<NAME>` |
| Authorization Scenario | `AU_` | `AU_<NAME>` |

## Restrictions
- Business Builder usage is NOT recommended
- Do not mix layers or prefixes
- If unsure, ask for clarification instead of guessing
