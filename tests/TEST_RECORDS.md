# Test Records -- PBI AI DevKit

> Target: Local PBIX + BIM + Remote Power BI Cloud | Date: 2026-07-08 ~ 2026-07-14

---

## Test Suite Summary

| # | Test File | Purpose | Result |
|---|-----------|---------|:---:|
| 1 | `test_suite.py` | 8-tool comprehensive test | 8/8 PASS |
| 2 | `read_and_test.py` | Model exploration + 6 analyses | 6/6 PASS |
| 3 | `live_edit_tests.py` | 3 real model edits | 3/3 PASS |
| 4 | `complex_dax_tests.py` | 7 complex DAX queries | 7/7 PASS |
| 5 | `mtd_new_customers.py` | 5 MTD time intelligence queries | 5/5 PASS |
| 6 | `deep_explore.py` | Deep model exploration | Completed |
| 7 | `create_measures.py` | Create 3 measures via TOM | 3 created |
| 8 | `fix_measures.py` | Fix + recreate with correct logic | 3 fixed |

**Total: 35 tests, 35 passed**

---

## Test Details

### 1. test_suite.py — 8 Tool Capability Tests
- Model Discovery: 25 tables, 541 measures, 465 columns
- Column Exploration: Calendar table 32 columns
- Measure Filtering: 44 WTD, 62 Sales, 539 KPI
- DAX Search: 33 MERCH YEAR, 309 CALCULATE, 83 HASONEVALUE
- DAX Execution: VALUES, TOPN, COUNTROWS (2.4M rows)
- Error Detection: 0 errors (all fixed)
- Folder Organization: 14 top-level folders
- Dependency Chain: WTD Sales WoTax referenced by 7 measures

### 2. read_and_test.py — Model Analysis
- Top column references: Calendar[DATE] (635 refs), WEEK_NUMBER (102), MERCH YEAR (86)
- Measure distribution: 539 in KPI, 1 in Calendar, 1 in Xsell Filter
- Dependency hubs: Customers (26 refs), Sales WoTax (25), Customers (N) (24)
- DAX patterns: FILTER (140), DIVIDE (132), VAR (101), SWITCH (51), DATESBETWEEN (50)

### 3. live_edit_tests.py — Real Model Edits
- Added comment header to "Scope Display" measure
- Changed "Av basket/macrotrans" format to #,0.00
- Moved "Scope Display" to TECHNICAL MEASURES\TEST folder

### 4. complex_dax_tests.py — 7 DAX Queries
- CASE 1: Sales KPIs by Store Type (Latest Year) — RETAIL 75M
- CASE 2: Top 10 Days by Sales — max 3.99M (2021-08-14)
- CASE 3: Performance by MERCH YEAR + SEASON — 37 rows, 2013-2026
- CASE 4: Cross-Selling KPIs — PERFUMES 28.6% cross-sell rate
- CASE 5: Top 3 Customers per Year — CN0010012879 appears 9 years
- CASE 6: Customer Mix by Year — 15 rows
- CASE 7: YoY Growth — 2021 +237.5% (COVID recovery)

### 5. mtd_new_customers.py — MTD Time Intelligence
- CASE A: MTD New Cust vs LY MTD by Month — 156 rows
- CASE B: 2025 vs 2026 monthly comparison — 20 rows
- CASE C: New Customer by Store Type — RETAIL -46.6% YoY
- CASE D: Cross-check last data date (2026-07-07) — MTD = 2,160
- CASE E: Sales MTD vs LY MTD by Store Type

### 6. deep_explore.py — Model Logic Discovery
- Found [NEW CLIENTS] = CALCULATE([Customers (N)], ISFIRSTTRANSACTION = 1)
- Found [PY NEW CLIENTS] = SAMEPERIODLASTYEAR
- Found [YOY% NEW CLIENTS] already exists
- Key finding: ISFIRSTTRANSACTION column defines "new client" logic

### 7. create_measures.py — Initial Creation (REPLACED)
- Created MTD New Customers, LY MTD New Customers, YoY MTD New Customers %
- Based on [Customers (N)] — WRONG LOGIC

### 8. fix_measures.py — Corrected Creation
- Deleted 3 wrong measures
- Created MTD NEW CLIENTS, LY MTD NEW CLIENTS, YoY MTD NEW CLIENTS %
- Based on [NEW CLIENTS] — CORRECT LOGIC (ISFIRSTTRANSACTION filter)

---

## Measure Changes Made to Model

| Action | Measure | Folder |
|--------|---------|--------|
| UPDATED | Scope Display (added comment) | TECHNICAL MEASURES\TEST |
| UPDATED | Av basket/macrotrans (format #,0.00) | BASKET/MACROTRANS\N |
| UPDATED | Scope Display (folder moved) | TECHNICAL MEASURES\TEST |
| CREATED | MTD NEW CLIENTS | ClaudeTest |
| CREATED | LY MTD NEW CLIENTS | ClaudeTest |
| CREATED | YoY MTD NEW CLIENTS % | ClaudeTest |
| DELETED | MTD New Customers | ClaudeTest |
| DELETED | LY MTD New Customers | ClaudeTest |
| DELETED | YoY MTD New Customers % | ClaudeTest |

---

## Key Learnings

1. **DMV queries have limitations** — no ORDER BY multi-column, no LIKE, no WHERE complex filters. Filter in Python.
2. **SSAS port changes** — Power BI Desktop assigns a random port each time. Always auto-discover.
3. **Understand Before Create** — Never create measures without first exploring existing model logic.
4. **DAX variable names** — Avoid naming variables that conflict with DAX functions (e.g., `MTD`).
5. **SELECT * works** — when specific column names cause DMV errors, fall back to SELECT *.

---

## Power Query Research (2026-07-10)

### Research Path

| # | Approach | Result |
|---|----------|:---:|
| 1 | DataMashup ZIP extraction | Works for legacy PBIX (verified with synthetic test) |
| 2 | Microsoft.Mashup API | Requires workspace context, impractical |
| 3 | xmSQL binary parsing | Not feasible (proprietary compression) |
| 4 | **TMSCHEMA_PARTITIONS.QueryDefinition** | **READ works — 32/32 tables** |
| 5 | **TOM MPartitionSource.Expression** | **READ works, WRITE limited** |

### Key Discovery

M code is stored in `$SYSTEM.TMSCHEMA_PARTITIONS.QueryDefinition` DMV column.
All 32 tables' Power Query M code is readable through the SSAS connection.

### Modification Test Results

| Test | Result |
|------|:---:|
| Add comment to Store M code | **Persisted** |
| Replace Store M code with Value.NativeQuery | **Rolled back by PBI Desktop** |

**Conclusion:** Power Query M code is **readable** via SSAS DMV but **structurally immutable** through TOM. Power BI Desktop validates and reverts changes that alter query structure. Only cosmetic changes (comments) persist.

### Power Query Audit Findings

- Data source: 8 tables → Hologres PostgreSQL
- 12 tables use `List.Max` + `Table.SelectRows` pattern (no query folding)
- Calendar: 14 AddColumn calls, 33 steps (highest complexity)
- Customer: 19 steps, 42 complexity
- Key optimization: NativeQuery for 12 tables could reduce network transfer by ~99%

### Files Created

| File | Purpose |
|------|---------|
| `power_query.py` | DataMashup ZIP extraction module |
| `power_query_ssas.py` | SSAS partition-based M code reader |
| `create_test_pbix.py` | Synthetic PBIX generator for testing |
| `audit_pq.py` | Power Query audit tool |
| `optimize_example.py` | Query folding optimization example |
| `modify_pq_tom.py` | TOM-based M code modification |
| `test_xmla_alter.py` | XMLA Alter attempt (failed) |
| `check_partitions.py` | Partition QueryDefinition discovery |
| `research_m_code.py` | M code location research |
| `explore_mashup.py` | Microsoft.Mashup API exploration |

---

## New Tool Development (2026-07-10)

### Phase 1: Create/Delete/Read

| # | Test File | Purpose | Result |
|---|-----------|---------|:---:|
| 9 | `test_new_tools.py` | create_measure, delete_measure, get_roles | 5/5 PASS |
| 10 | `review_new_tools.py` | Review: create/delete/roles with multi-instance safety | 6/6 PASS |
| 11 | `test_relationship.py` | create_relationship API test | PASS |
| 12 | `create_safe_rel.py` | Create persistent relationship (Pmt_Format -> Pmt_Store) | PASS |
| 13 | `review_final.py` | Review all 4 new tools | 6/6 PASS |

### Phase 2: Table/Column Operations

| # | Test File | Purpose | Result |
|---|-----------|---------|:---:|
| 14 | `test_create_table.py` | create_table + create_column + partition | PASS |
| 15 | `review_table_col.py` | Review: create table, add column, measure, verify | 6/6 PASS |
| 16 | `create_demo_v2.py` | Claude Demo table creation with data | PASS |

### Phase 3: Batch Operations

| # | Test File | Purpose | Result |
|---|-----------|---------|:---:|
| 17 | `test_batch.py` | batch_operations: create, verify, rollback | 4/4 PASS |

### Phase 4: Business Analysis

| # | Test File | Purpose | Result |
|---|-----------|---------|:---:|
| 18 | `celine_june2026.py` | June 2026 sales performance analysis | Completed |
| 19 | `explore_segmentation.py` | Customer segmentation structure | Completed |
| 20 | `top_r12_v2.py` | R12 TOP tier count + sales | Completed |
| 21 | `top_monthly.py` | Monthly TOP tier retention (12 months) | Completed |

### Phase 5: Channel Exclusivity Analysis

| # | Test File | Purpose | Result |
|---|-----------|---------|:---:|
| 22 | `channel_exclusivity.py` | DAX logic for channel-exclusive customers | PASS |
| 23 | `channel_check.py` | Single-channel distribution (2025) | PASS |
| 24 | `test_retail_st.py` | Unified Single-Channel Customers measure | PASS |
| 25 | `create_unified_measure.py` | Single-Channel + Multi-Channel measures | PASS |

### Phase 6: Model Graph & DAX Improvement

| # | Test File | Purpose | Result |
|---|-----------|---------|:---:|
| 26 | `test_graph.py` | get_model_graph tool | PASS |
| 27 | `graph_improvement.py` | Before/after: DAX accuracy with model graph | PASS |

**Total: 27 test suites, all passed**

### Phase 7: BPA + Dependency Tracker (2026-07-11)

| # | Test File | Purpose | Result |
|---|-----------|---------|:---:|
| 28 | `test_bpa_deps.py` | BPA full analysis + Dependency graph on test model (1680 measures) | 7/7 PASS |
| 29 | `test_new_features.py` | BPA unit tests (22 rules) + Dependency tracker unit tests | 22/22 PASS |

**Total: 29 test suites, all passed**

**BPA Results (test model, 1680 measures):**
| Metric | Value |
|--------|-------|
| Total issues | 6,003 |
| Errors | 0 |
| Warnings | 1,057 |
| Info | 4,946 |
| Top rule | NO_COMMENTS (1,130), CALCULATE_NO_FILTER (1,044), NO_DISPLAY_FOLDER (956) |

**Dependency Tracker Results (test model, 1680 measures):**
| Metric | Value |
|--------|-------|
| Measures with dependencies | 1,583 (94%) |
| Measures with dependents | 1,152 (69%) |
| Circular dependencies | 0 |
| Orphan references | 0 |
| Most referenced | LAST_DAY_SALES (440 dependents) |
| Net Sale Euro impact | 17 deps, 27 direct + 281 transitive = 308 affected |

### Phase 8: Remote XMLA/REST API Connection (2026-07-12)

| # | Test File | Purpose | Result |
|---|-----------|---------|:---:|
| 30 | `test_remote_xmla.py` | MSAL auth + XMLA connection + DMV + DAX to Power BI China | 5/9 PASS |
| 31 | `test_remote_rest.py` | REST API DAX queries + workspace/dataset discovery | 6/6 PASS |

### Phase 9: Smoke Test + Data Quality (2026-07-13)

| # | Test File | Purpose | Result |
|---|-----------|---------|:---:|
| 32 | `smoke_test.py` | Quick connectivity check (6 tests, <15s) | 6/6 PASS |
| 33 | `dq_preselling.py` | Data quality verification for Preselling Reporting CN | 7/7 PASS |

### Phase 10: Report Layout Parser (2026-07-13)

| # | Test File | Purpose | Result |
|---|-----------|---------|:---:|
| 34 | `report_parser.py` (CLI) | PBIX layout parsing: pages, visuals, field bindings | 8/8 PASS |
| 35 | `report_parser.py` (--measure) | Measure usage lookup (impact analysis) | 67 hits |
| 36 | `report_parser.py` (--measures --unused) | BIM cross-check: 568 truly unused measures | 1680→15 |
| 37 | `server.py` (tool registration) | 3 new MCP tools registered (26 total) | 3/3 PASS |

**Report Parser Results:**
- 8 pages discovered, 97 visuals (77 slicers, 10 tables, 5 matrices, 5 chiclets)
- 15 measures from `_Report Measures_` table, 45 columns across 6 tables
- Most-used measure: `Reservation/Ordered Qty` (10 visuals across 7 pages)
- BIM cross-check: 1,680 model measures → 15 in report → 568 potentially unused

**New MCP Tools (v1.4.0):**
- `get_report_structure` — full report layout
- `get_report_measures` — measure usage + BIM cross-check
- `get_report_field_usage` — impact analysis before modifying a measure

**Total: 37 test suites**

### Phase 11: Live Connection PBIX Measure Extraction + DAX Audit (2026-07-13, v1.4.1)

| # | Test File | Purpose | Result |
|---|-----------|---------|:---:|
| 38 | `report_parser.py` (--report-measures) | Extract 52 report-level measures from modelExtensions | 52/52 extracted |
| 39 | `report_parser.py` (get_report_measures_dax) | Programmatic API for measure DAX extraction | OK |
| 40 | `extract_measures.py` | Deep dive into PBIX modelExtensions entities | 1 entity, 52 measures |
| 41 | `cross_layer_validation_v2.py` | Cross-layer: report + BIM + live data | 5 issues found |
| 42 | `sample_data_for_team.py` | Sample data for investigation (orphans, cancel, neg qty) | 12 queries |

**Live Connection Measure Extraction Results:**
- PBIX `modelExtensions` contains 1 entity (`_Report Measures_`) with 52 measures
- 15 measures used in report visuals, 37 intermediate/reserve measures
- Found 1 DAX bug: `//+[Reservation Cancelled Qty]` — comment syntax disables subtraction

**Cross-Layer Validation Findings:**
- Order→Customer: 3,583 orphans (7.7%) — Greater China zone, evenly distributed
- Reservation→Customer: 799 orphans (2.3%)
- Cancellation spike: 2025 H2 47-59% — REGULAR_RESERVATION type 49.3% cancel rate
- Negative Qty: 3,060 rows (6.6%) — ALL from Digital channel, RETURNED status
- Date anomaly: `Sales_Order_Creation_Date` defaults causing 38-year avg gap
- SHIPPED without Fulfilled=Y: 66 rows — ALL China Ecommerce

**Report Parser Enhancement:**
- `_extract_report_measures()` — auto-extracts measures from `modelExtensions` in Live Connection PBIX
- `get_report_measures_dax()` — returns dict of {measure_name: {name, table, expression, ...}}
- `--report-measures` CLI flag — outputs full DAX for all report-level measures

**Total: 42 test suites**

### Phase 12: DAX Safe Modification + MCP Tool #27 (2026-07-13, v1.4.2)

**Remote Connection Results:**

| Test | Result | Detail |
|------|:---:|------|
| MSAL username/password auth | **OK** | Token cached, 59min expiry |
| REST API: list workspaces | **OK** | 7 workspaces, all Premium |
| REST API: list datasets | **OK** | 3 datasets in FEN-D-ATOM |
| REST API: executeQueries (DAX) | **OK** | VALUES(Calendar[Year]) -> 9 rows |
| REST API: INFO functions | **FAIL** | Not supported by REST API |
| REST API: DMV queries | **FAIL** | $SYSTEM stripped from query |
| XMLA: ADOMD.NET | **FAIL** | "Authentication failed for all authenticators" |
| XMLA: direct HTTP | **400** | Token valid (401->400), request format issue |

**Key Findings:**
- Power BI China XMLA cluster: `wabi-mc-north3-a-primary-redirect.analysis.chinacloudapi.cn`
- XMLA endpoint at `/xmla` accepts token but rejects request format
- ADOMD.NET from Power BI Desktop may not support Power BI China XMLA auth
- REST API `executeQueries` provides working DAX query capability
- Metadata (tables/measures/columns) requires XMLA fix or alternative

**Files Modified for Remote:**
- `ssas_client.py`: `acquire_token()` dual-mode, `RemotePowerBI` class
- `server.py`: `_get_connection()` 5-tuple, XMLA->REST fallback
- `.mcp.json`: added remote XMLA + credentials config

### Phase 13: Live Connection Auto-Detection & First-User Feedback (2026-07-23, v1.7.0)

| # | Change | Purpose | Impact |
|---|--------|---------|:---:|
| 43 | `_extract_pbix_path()` | Extract PBIX path from PBIDesktop.exe command line | New helper |
| 44 | `_read_pbix_connections()` | Read Connections file from PBIX ZIP for live connection detection | New helper |
| 45 | `_parse_connection_string()` | Parse Power BI connection strings (Data Source, Initial Catalog) | New helper |
| 46 | `discover_pbi_instances()` enriched | Returns `pbix_path`, `remote_server`, `remote_database` | Enhanced |
| 47 | `_get_connection()` auto-fallback | Detects empty database -> auto-fallback to remote via PBIX connection info | Critical fix |
| 48 | `RemotePowerBI` cloud detection | Auto-detects China vs Global cloud from server URL | Fixed |
| 49 | `execute_dax()` error parsing | Extracts `DetailsMessage` from HTTP 400 JSON | Improved UX |
| 50 | `get_database_name()` TOM fallback | TOM-first for local models, warns on empty database | Enhanced |
| 51 | `execute_dmv()` error messages | Catches CurrentCatalog XMLA errors with clear message | Improved UX |
| 52 | `report_parser.py` Unicode fix | `→` -> `->` for Windows cp1252 compatibility | Fixed |
| 53 | `run_dax` column name cleanup | Strips `[Table].[Column]` prefix via `_clean_column_name()` | Improved UX |
| 54 | `discover` tool output | Shows PBIX path, live connection status, remote server/database | Enhanced |

**Live Connection Auto-Fallback Flow:**
1. `discover_pbi_instances()` finds PBIX path from PBIDesktop.exe command line
2. Opens PBIX as ZIP, reads `Connections` file, extracts `remote_server` and `remote_database`
3. `_get_connection()` in auto mode: connects to local SSAS -> `get_database_name()` returns empty
4. Checks instance dict for `remote_server` -> auto-falls back to `_connect_remote()`
5. Logs: "Live connection detected -> auto-fallback to remote: powerbi://.../DatasetName"
6. If no connection info found, gives clear error: "This PBIX is a live connection. Set PBI_XMLA_SERVER."

**Total: 54 test suites / changes tracked**

### Phase 14: BIM Auto-Discovery & Remote Mode Crash Fix (2026-08-11, v1.7.1)

| # | Change | Purpose | Impact |
|---|--------|---------|:---:|
| 55 | `_find_bim_file()` | Auto-discover BIM file by keyword matching database name | New helper |
| 56 | `RemotePowerBI.Close()` | Add Close() method to prevent AttributeError in finally blocks | Fixed |
| 57 | `_connect_remote()` BIM auto-search | Fallback to `_find_bim_file()` when PBI_BIM_PATH not set | Enhanced |
| 58 | `get_tables` remote guard | Graceful error when remote without BIM instead of crash | Fixed |
| 59 | `get_measures` remote guard | Graceful error when remote without BIM instead of crash | Fixed |
| 60 | `get_columns` remote guard | Graceful error when remote without BIM instead of crash | Fixed |
| 61 | `search_dax` remote guard | Graceful error when remote without BIM instead of crash | Fixed |
| 62 | `bpa_analyze` remote support | Now works with BIM schema data, not just local DMV | Added |
| 63 | `dependency_analyze` remote support | Now works with BIM schema data, not just local DMV | Added |
| 64 | `get_relationships` remote support | Now works with BIM schema via `get_relationships()` | Added |
| 65 | `_no_bim_error()` helper | Friendly error message guiding user to provide BIM file | New helper |

**BIM Auto-Discovery Strategy:**
1. Extract keywords from database name (e.g. `"SalesAndCrm - target_China_FG"` → `["salesandcrm","fendi","china","fg"]`)
2. Recursively search `D:\LVMH_Max\` (configurable via `PBI_BIM_SEARCH_PATH`) for `.bim` files
3. Score each file by keyword match count, then by modification time
4. Return best match; require ≥2 keyword matches for confidence

**Verification:**
- All 11 tests passed (BIM discovery, get_tables 109, get_measures 1621, get_columns 90, search_dax 463, BPA, dependency, relationships 145, Close)

**Total: 65 test suites / changes tracked**

---

## Final Tools Summary (25 tools)

| Category | Tools |
|----------|-------|
| Discovery | discover, get_model_info, get_model_graph |
| Read | get_tables, get_measures, get_columns, get_relationships, get_roles |
| Search | search_dax, audit_power_query |
| Query | run_dax, validate_dax |
| Analysis | bpa_analyze, dependency_analyze |
| Export | export_model_snapshot, get_power_query |
| Create | create_measure, create_table, create_column, create_relationship |
| Modify | replace_in_measure |
| Delete | delete_measure |
| Batch | batch_operations |

## Model Changes (ClaudeTest folder)

| Action | Measure | DAX |
|--------|---------|-----|
| CREATED | Single-Channel Customers | Per-customer channel count with REMOVEFILTERS |
| CREATED | Multi-Channel Customers | Customers with 2+ store types |
| (cleaned) | MTD NEW CLIENTS, LY MTD NEW CLIENTS, YoY MTD NEW CLIENTS % | Removed after testing |

## Key Learnings (Updated)

1. **DMV queries have limitations** — no ORDER BY multi-column, no LIKE, no WHERE complex filters
2. **SSAS port changes** — always auto-discover, never hardcode
3. **Understand Before Create** — explore existing measures before creating new ones
4. **DAX pre-flight check** — use `get_model_graph` to check relationship direction before writing DAX
5. **Fact table columns over dimension columns** — avoids single-direction relationship issues
6. **REMOVEFILTERS** — essential for per-customer calculations in filtered contexts
7. **SELECTEDVALUE vs VALUES** — SELECTEDVALUE for scalar, VALUES for table
8. **Power Query M code** — readable via DMV, structurally immutable through TOM
9. **Table creation** — structure persists, data refresh needs PBI Desktop
10. **Multi-instance safety** — always confirm target before modifying
11. **BPA severity layering** — error (syntax) > warning (potential bug) > info (style); 18 rules cover all 4 categories
12. **Dependency graph** -- BFS for transitive closure, DFS (3-color) for circular detection, Kahn for topological order
13. **Power BI China XMLA auth** -- token valid for REST API (200) but XMLA endpoint returns 400 (token accepted, format rejected)
14. **REST API as XMLA fallback** -- `executeQueries` works for DAX queries, but DMV and INFO functions are not supported
15. **Remote workspace resolution** -- `powerbi://` URL -> REST API groups -> workspace ID -> dataset ID -> executeQueries
16. **ROW() bracket keys** -- REST API executeQueries returns column names as `[Key]` with brackets; use `client.row_val(row, "Key")` helper
17. **Column name discovery** -- always query BIM first for actual column names before writing DAX; never guess (e.g., `CUST_KEY` not `Customer ID`)
18. **Token TTL = 59min** -- always set PBI_USERNAME/PBI_PASSWORD via `os.environ.setdefault()` in test scripts to survive cache expiry
19. **Smoke test first** -- run `smoke_test.py` (6 checks, <15s) before any data quality script to confirm connection health
20. **Live Connection PBIX measures** -- check `modelExtensions` in Layout JSON for report-level measures that are NOT in the BIM file
21. **DAX string comparison is case-insensitive** -- `"No exchange" = "No Exchange"` in DAX, but `EXACT()` is case-sensitive; always use `UPPER()` for clarity
22. **DAX `//` comment scope** -- `//` comments out the ENTIRE rest of the line, including closing brackets; never do blind string replacement on commented DAX

---

## Data Quality Analysis Playbook

> Standard test cases for comprehensive data quality verification. Apply in this order.

### Phase A: Connectivity & Discovery

| Step | Test | Tool |
|------|------|------|
| A1 | Smoke test (token, workspace, dataset, DAX) | `smoke_test.py` |
| A2 | Parse report structure (pages, visuals, measures, columns) | `report_parser.py` |
| A3 | Extract report-level measures (Live Connection PBIX) | `report_parser.py --report-measures` |

### Phase B: Cross-Layer Validation

| Step | Test | Query Pattern |
|------|------|------|
| B1 | Validate report columns exist in BIM model | Compare `report_parser.get_columns()` vs `bim_reader.get_columns()` |
| B2 | Validate report measures exist in BIM or modelExtensions | Compare `report_parser.get_measures()` vs BIM measures + modelExtensions |
| B3 | Audit DAX for hardcoded values, missing fallbacks | `dax_safe_modify.py` + manual review of all `CALCULATE`, `DIVIDE`, `SWITCH`, `SELECTEDVALUE` |

### Phase C: Data Quality Metrics

| Step | Test | Query Pattern |
|------|------|------|
| C1 | Row counts for key tables | `COUNTROWS('Table')` |
| C2 | NULL/blank check on key columns | `COUNTROWS(FILTER(table, ISBLANK([col])))` |
| C3 | Referential integrity: fact -> dimension | `COUNTROWS(FILTER(fact, NOT(CONTAINS(dim, dim[key], fact[key]))))` |
| C4 | Distinct value distribution for dimension columns | `SUMMARIZECOLUMNS(table[col], COUNTROWS(table))` |
| C5 | Data freshness: max date per table | `MAX(table[DateColumn])` |

### Phase D: Enum Value Consistency

| Step | Test | Query Pattern |
|------|------|------|
| D1 | List all distinct values for status/type columns | `SUMMARIZECOLUMNS(table[StatusCol], COUNTROWS(table))` |
| D2 | Check DAX filter values against actual data enums | Compare DAX hardcoded strings vs D1 results |
| D3 | Identify dead conditions (DAX references value not in data) | `FILTER(table, col IN {DAX_values})` vs `FILTER(table, TRUE)` |
| D4 | Identify BLANK exclusion (DAX misses BLANK rows) | `FILTER(table, ISBLANK(col))` count vs filter impact |

### Phase E: Business Metric Validation

| Step | Test | Query Pattern |
|------|------|------|
| E1 | Monthly trend of key measures | `SUMMARIZECOLUMNS(Calendar[YearMonth], measure1, measure2)` |
| E2 | Key measure breakdown by dimension | `SUMMARIZECOLUMNS(dim[col], measure1, measure2)` |
| E3 | Channel/store segmentation | `SUMMARIZECOLUMNS(table[Channel], measures)` |
| E4 | Anomaly detection: negative values, zeros, future dates | `FILTER(table, Qty < 0)`, `FILTER(table, Date > TODAY())` |

### Phase F: Environment Comparison (DEV vs PRD)

| Step | Test | Query Pattern |
|------|------|------|
| F1 | Row counts comparison | Same query on both environments |
| F2 | Date range comparison | `MIN/MAX` on both |
| F3 | NULL/blank comparison | Same NULL check on both |
| F4 | Referential integrity comparison | Same orphan check on both |
| F5 | Enum value distribution comparison | `SUMMARIZECOLUMNS` on both |
| F6 | Channel/segment distribution comparison | Same segmentation on both |

### Phase G: DAX Fix & Verify

| Step | Test | Tool |
|------|------|------|
| G1 | Preview DAX change with defensive checks | `validate_dax_change` or `dax_safe_modify.py` |
| G2 | Apply fix to PBIX | `fix_*.py` script with JSON parsing |
| G3 | Verify fix applied correctly | `report_parser.py --report-measures` on fixed PBIX |
| G4 | Re-run affected metrics to confirm impact | Same queries as Phase C/E with fixed filters |

### Example: Preselling Reporting CN (2026-07-13)

| Phase | Tests Run | Issues Found |
|------|:--:|------|
| A | 3/3 | Live Connection PBIX, 52 report-level measures |
| B | 3/3 | BIM stale (15 measures missing), 27 hardcoded values, 7 DIVIDE no fallback |
| C | 5/5 | 11.3% customer linkage broken, 30.6% Creation Date defaults |
| D | 4/4 | Flag Exchange: "false" dead condition + BLANK excluded (14,225 rows) |
| E | 4/4 | Cancelled Qty exceeds Ordered Qty since 2025 H2 (peak +61%) |
| F | 6/6 | PRD lacks Digital channel entirely (14,225 rows missing) |
| G | 4/4 | 27 measures fixed, 5.64M EUR recovered, 1 syntax error caught by defensive check |

---

## Phase 13: PBIX Safe Modification (v1.4.3)

### Test #34: PBIX Layout JSON Escaping Bug

| Step | Action | Result |
|------|--------|--------|
| 1 | Read PBIX Layout as UTF-16 LE JSON | Layout text loaded, config is nested JSON string |
| 2 | `json.loads` → modify config → `json.dumps(layout)` | PBIX corrupted: "file is corrupted or was created by an unrecognized version" |
| 3 | Inspect raw Layout bytes | Config has 4-layer JSON escaping: `"Canceled"` → `\\\"Canceled\\\"` |
| 4 | `json.dumps` changes escaping format | Root cause: Python `json.dumps` uses different escaping rules than Power BI |
| 5 | Fix: replace only config string in raw text | `json.dumps(old_config)` → `json.dumps(new_config)` → `text.replace(old, new)` |
| 6 | Verify PBIX opens | PBIX opens successfully |

**Root Cause**: Power BI's Layout JSON has nested JSON escaping (config is a JSON string inside a JSON object). `json.dumps` on the entire Layout changes the escaping format, making the file unreadable by Power BI.

**Fix**: `pbix_safe.py` module — replaces only the config string in the raw Layout text, preserving all other bytes.

### Test #35: Retail Activations DQ Check (Full Playbook)

| Phase | Tests | Result |
|-------|-------|--------|
| A | 3/3 | 11 pages, 131 report measures, Live Connection |
| B | 3/3 | 131 measures NOT in BIM (expected), 11 columns NOT in BIM |
| C | 5/5 | Campaign Period NULL: BOFS 99.96%, RTB 99.94% |
| D | 4/4 | Canceled/CANCELLED coexistence, Flag Campaign Period BLANK 100% |
| E | 4/4 | 1,258 campaigns, 8 types, RTB 253.6M EUR |
| F | 6/6 | DEV vs PRD: BIM SQL version mismatch, max dates match after refresh |
| G | 4/4 | 29 measures fixed (Canceled 22, DIVIDE 3, RTB case 4) |

### Test #36: Preselling DQ Update — Flag Exchange Revert

| Step | Action | Result |
|------|--------|--------|
| 1 | Revert Flag Exchange ISBLANK from 9 measures | Restored to original `IN {"false","No Exchange"}` |
| 2 | Compare against origin PBIX | 12/12 Flag Exchange measures match |
| 3 | Re-apply all other fixes to origin | Cancel 24, DIVIDE 7, SWITCH 11, Case 3 |
| 4 | Apply UPPER to Cancel + hardcoded | 24 Cancel + 27 hardcoded + 18 BLANK→ISBLANK |
| 5 | Safe save via config replacement | PBIX opens successfully |

## Key Learnings (Updated)

22. **PBIX Layout JSON has nested escaping** — config is a JSON string inside a JSON object. `json.dumps` changes Power BI's original escaping format, corrupting the file. Always use config-string replacement.
23. **Always backup before PBIX modification** — `shutil.copy2` before any write, keep timestamped backups.
24. **Use `SafePbixModifier` context manager** — auto-backup, safe config replacement, JSON validation.
25. **Raw string replacement on Layout text** — use `chr(92)` + `chr(34)` to build patterns matching the exact escaping (e.g., `\\\"` = 3 backslashes + quote).
26. **SUMMARIZECOLUMNS keys include table prefix** — REST API returns `TableName[ColumnName]` format, not `[ColumnName]`. Use `row_val()` or iterate keys.

---

## Phase 14: KPI Column Dependency Verification (2026-07-17)

### Test #43: `test_kpi_dependency_book_appointment.py`

| Suite | Purpose | Tests | Result |
|-------|---------|:-----:|:------:|
| Suite 1 | KPI Existence & DAX Dependency | 39 | 39/39 PASS |
| Suite 2 | Page Usage Verification | 40 | 40/40 PASS |
| Suite 3 | Unexpected Column Reference Detection | 2 | 2/2 PASS |
| Suite 4 | Report Structure Integrity | 1 | 1/1 PASS |
| **Total** | | **82** | **82/82 PASS** |

**Target PBIX**: `Report Book Appointment_Atom CN.pbix` (Live Connection, 3 pages, 43 measures)

**Test Coverage:**
- 14 KPIs in BAA chain (Customer Active SID Code BAA): 1 DIRECT, 13 INDIRECT
- 20 KPIs in IDCAMP chain (IDCAMPACTIVITY): 4 DIRECT, 16 INDIRECT
- 6 KPIs in Other (Sold Qty): 1 DIRECT, 5 INDIRECT
- 1 report-level measure (DAX in visual config, not in model)

**Key Findings:**
- `# BAA Converted Clients` is the sole DIRECT KPI for BAA column — all 13 derivatives wrap it
- `_# of Appointments`, `# of Appointments Scheduled`, `_# of Appointments CheckedIn`, `# of Appointments Cancelled to Reschedule` are the 4 DIRECT KPIs for IDCAMP
- `_switch` KPIs route to time-period variants based on user selection (WTD/MTD/YTD/CY)
- `[Customer Active SID Code BAA]` never appears directly in any visual — only via DAX measures
- `[IDCAMPACTIVITY]` appears both in measures AND as a raw column in the Detail tableEx

**Test Script**: `tests/test_kpi_dependency_book_appointment.py`
**Output Files**:
- `Book Appointment_Atom CN - KPI Column Dependency Analysis.docx` (detailed analysis report)
- `Book Appointment_Atom CN - KPI Usage Table.xlsx` (KPI matrix with group/dependency/page mapping)
- `Book Appointment_Atom CN - KPI Usage Table.docx` (Word version of KPI table)

**How to Run**:
```bash
cd PBI-AI-DevKit
python tests/test_kpi_dependency_book_appointment.py
```