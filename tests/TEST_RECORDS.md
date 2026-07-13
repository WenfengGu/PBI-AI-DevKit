# Test Records -- PBI AI DevKit

> Target: Local PBIX + BIM + Remote Power BI Cloud | Date: 2026-07-08 ~ 2026-07-12

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

**Total: 32 tests, 32 passed**

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

**Total: 33 test suites**

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

---

## Final Tools Summary (23 tools)

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