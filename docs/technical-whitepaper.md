# Technical Whitepaper: Power BI + AI Assistant Integration

> PBI AI DevKit — Power BI AI Development Toolkit for Claude Code | July 2026 (v1.2)

---

## 1. Abstract

This document compares the technical paths for AI assistants (Claude Code, ChatGPT/Copilot) to interact with Power BI data models. It analyzes the architecture, capability boundaries, and applicable scenarios of each approach, and explains the technical decisions behind building our own PBI AI DevKit.

**v1.2 additions:** Remote REST API connection, BIM-driven remote queries, dual-mode connection strategy.

---

## 2. Power BI Model Access Paths

### 2.1 PBIX File Structure

A PBIX file is a ZIP archive with the following internal structure:

```
file.pbix (ZIP)
+-- DataModel          <- SSAS xmSQL compressed backup (model core)
+-- Report/Layout      <- Visual layout (JSON)
+-- TMDLScripts/       <- Incremental changes (TMDL format, dirty data only)
+-- DataMashup         <- Power Query M code (legacy format, ZIP within ZIP)
+-- Connections        <- Data source connection info
+-- Metadata           <- File metadata
+-- ...
```

### 2.2 Key Constraints

- **DataModel** is xmSQL compressed binary (Microsoft Analysis Services proprietary format), not directly parseable as text
- **DataMashup** only exists in non-enhanced metadata PBIX files; in enhanced format, M code is embedded inside DataModel
- The runtime state is managed by **msmdsrv.exe** (SSAS Tabular engine), listening on `localhost:<random port>`

### 2.3 Three Access Paths

| Path | Protocol | Use Case |
|------|----------|----------|
| **Power BI REST API** | HTTPS | Cloud datasets, reports, workspace management |
| **XMLA Endpoint** | HTTP/XMLA | Local or cloud SSAS instance read/write |
| **ADOMD.NET / TOM** | TCP (localhost) | Direct connection to local Power BI Desktop |

---

## 3. Existing Solutions

### 3.1 Official Power BI MCP Server (Preview)

Released by Microsoft in 2026, with two variants:

**Local Server:**
- Runtime: Node.js 20+, launched via `npx`
- Transport: stdio
- Auth: Microsoft Entra ID (OAuth) or Service Principal
- Capabilities: TMDL-based semantic model read/write (tables, columns, measures, relationships), DAX query validation, batch operations
- File formats: Power BI Desktop, Fabric Workspace, Power BI Project (TMDL)

**Remote Server:**
- Runtime: Fabric-hosted service
- Transport: Streamable HTTP
- Auth: Microsoft Entra ID (OAuth)
- Capabilities: Copilot-driven DAX generation, natural language queries on semantic models

**Limitations:**
- Requires Entra ID authentication, no offline capability
- Node.js ecosystem dependency, extra setup for Python users
- Full-text DAX search and Power Query audit not in scope
- No DAX best practice analysis, no dependency tracking

### 3.2 Community Solutions

Multiple community Power BI MCP implementations exist, all based on:

- Power BI REST API (requires Azure AD)
- pythonnet + ADOMD.NET (local SSAS)
- msmdsrv port discovery + DMV queries

**Common limitation:** All community solutions are read-only for metadata; none support Measure modification (TOM).

### 3.3 ChatGPT/Copilot Integration

ChatGPT and GitHub Copilot use Microsoft's official plugins to call Power BI REST API and XMLA endpoints. These capabilities are bound to their respective ecosystems and unavailable to Claude Code users.

---

## 4. PBI AI DevKit Architecture

### 4.1 Technology Stack

```
+------------------------------------------------+
|  Claude Code (MCP Client)                      |
|    |  MCP JSON-RPC 2.0 (stdio, binary-safe)    |
|    v                                            |
|  server.py (Python 3.11)                       |
|    +-- MCP Protocol Layer (hand-written)        |
|    +-- 26 tool definitions                      |
|    +-- Tool Handler Dispatcher                  |
|         |                                        |
|    +----+--------------------------+            |
|    |    |                          |            |
|    v    v                          v            |
|  ssas_client.py   bpa.py    dependency_        |
|  (ADOMD+TOM+       (18 rules) tracker.py       |
|   REST API+BIM)                    |            |
|    |                               |            |
|    v                               v            |
|  power_query_ssas.py      bim_reader.py         |
|  (DMV Partition)          (BIM JSON)            |
|    |                                            |
|    v                                            |
|  pythonnet (CLR Bridge)                        |
|    |                                            |
|    v                                            |
|  Power BI Desktop DLLs (local)                 |
|    +-- Microsoft.PowerBI.AdomdClient.dll        |
|    +-- Microsoft.AnalysisServices.Server.       |
|    |   Tabular.dll                              |
|    +-- Microsoft.PowerBI.Tabular.dll            |
|         |                                        |
|         v                                        |
|  msmdsrv.exe (TCP localhost:<port>)            |
|    +-- SSAS Tabular Instance                   |
|                                                 |
|  -- OR (remote) --                             |
|                                                 |
|  REST API Client                               |
|    +-- Power BI Cloud (executeQueries)          |
+------------------------------------------------+
```

### 4.2 Core Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| MCP Protocol | Hand-written | Avoid mcp/fastmcp dependency, reduce network deps |
| Transport | Binary-safe stdio | Avoid Windows `\r\n` conversion breaking Content-Length |
| .NET Bridge | pythonnet 3.1 | Directly call PBI Desktop's built-in ADOMD.NET DLLs |
| Instance Discovery | netstat + tasklist | Zero-config auto-discovery of msmdsrv ports |
| Model Reading | DMV queries | `$SYSTEM.TMSCHEMA_*` series, comprehensive coverage |
| Model Modification | TOM (Tabular Object Model) | Direct `model.SaveChanges()`, not XMLA |
| Power Query Reading | TMSCHEMA_PARTITIONS.QueryDefinition | All table M code readable |
| DAX Analysis | Regex + bracket depth tracking | Pure Python static analysis, no SSAS connection needed |
| Dependency Tracking | Graph theory (BFS/DFS) | Forward/reverse/transitive/cycle detection, topological sort |
| Remote DAX | REST API executeQueries | Works with Power BI service datasets |
| Remote Metadata | BIM file | JSON schema cache when DMV unavailable |
| Connection Strategy | Local-first, remote-fallback | Max capability when PBIX is open, graceful degradation |
| Authentication | None (local) / MSAL (remote) | No auth for localhost; username/password for cloud |

### 4.3 Tool Inventory

| # | Tool | Technology | R/W |
|---|------|-----------|:---:|
| 1 | `discover` | netstat + tasklist | Read |
| 2 | `get_model_info` | DMV / BIM + REST API | Read |
| 3 | `get_tables` | DMV / BIM file | Read |
| 4 | `get_measures` | DMV / BIM file | Read |
| 5 | `get_columns` | DMV / BIM file | Read |
| 6 | `search_dax` | DMV / BIM file + Python filter | Read |
| 7 | `run_dax` | ADOMD.NET / REST API | Read |
| 8 | `replace_in_measure` | TOM: Measure.Expression | Write |
| 9 | `get_power_query` | DMV: TMSCHEMA_PARTITIONS.QueryDefinition | Read |
| 10 | `audit_power_query` | Same + pattern analysis | Read |
| 11 | `get_relationships` | DMV / BIM file | Read |
| 12 | `validate_dax` | DEFINE MEASURE ... EVALUATE | Read |
| 13 | `export_model_snapshot` | DMV full + JSON serialize | Read |
| 14 | `create_measure` | TOM: MeasureCollection.Add() | Write |
| 15 | `delete_measure` | TOM: MeasureCollection.Remove() | Write |
| 16 | `get_roles` | TOM: Model.Roles | Read |
| 17 | `create_relationship` | TOM: SingleColumnRelationship | Write |
| 18 | `create_table` | TOM: TableCollection.Add() + Partition | Write |
| 19 | `create_column` | TOM: DataColumn + DataType enum | Write |
| 20 | `batch_operations` | TOM: batch + single SaveChanges | Write |
| 21 | `get_model_graph` | DMV: tables+columns+relationships topology | Read |
| 22 | `bpa_analyze` | Python regex static analysis (18 rules) | Read |
| 23 | `dependency_analyze` | Python graph theory (BFS/DFS + topological) | Read |
| 24 | `get_report_structure` | PBIX zip parsing: pages, visuals, field bindings | Read |
| 25 | `get_report_measures` | Report measure usage + BIM cross-check | Read |
| 26 | `get_report_field_usage` | Impact analysis: measure/column -> page/visual | Read |

---

## 5. DAX Best Practice Analyzer (BPA)

### 5.1 Architecture

```
bpa.py
+-- Severity: error / warning / info
+-- Category: performance / maintainability / correctness / naming
+-- 18 Rules (extensible)
|   +-- Performance (6 rules)
|   |   +-- EARLIER_INSTEAD_OF_VAR
|   |   +-- CALCULATE_NO_FILTER
|   |   +-- FILTER_VALUES_PATTERN
|   |   +-- MULTIPLE_FILTER
|   |   +-- ITERATOR_NO_FILTER
|   |   +-- SELECTCOLUMNS_ADDCOLUMNS
|   +-- Maintainability (4 rules)
|   |   +-- LONG_EXPRESSION
|   |   +-- NO_COMMENTS
|   |   +-- HARDCODED_VALUES
|   |   +-- NESTED_IF_DEPTH
|   +-- Correctness (8 rules)
|   |   +-- DIVIDE_NO_ALTERNATIVE
|   |   +-- SWITCH_NO_ELSE
|   |   +-- ISFILTERED_IN_MEASURE
|   |   +-- ALL_VS_ALLSELECTED
|   |   +-- BLANK_COMPARISON
|   |   +-- USERELATIONSHIP_NO_CALCULATE
|   |   +-- SELECTEDVALUE_NO_ALTERNATIVE
|   |   +-- VAR_NO_RETURN
|   +-- Naming (2 rules)
|       +-- NO_FORMAT_STRING
|       +-- NO_DISPLAY_FOLDER
+-- DaxAnalyzer class
    +-- analyze_expression(expr) -> list[dict]
    +-- analyze_measure(measure_dict) -> list[dict]
    +-- analyze_all(measures) -> dict (stats + issues)
    +-- format_report(stats) -> str (readable report)
```

### 5.2 Implementation Details

- **Pure Python** -- no SSAS connection required; can analyze BIM files offline
- **Regex + bracket depth tracking** -- handles nested function calls, avoids false positives
- **Severity layering** -- error (syntax) / warning (potential bug) / info (style suggestion)
- **Extensible** -- add new rules by implementing `_check_xxx(expr) -> Optional[dict]` and registering in `EXPRESSION_RULES`

### 5.3 Benchmark Data

Tested against a production model with ~1,680 measures across 117 tables:

| Metric | Value |
|--------|-------|
| Total issues found | ~6,000 |
| Errors | 0 |
| Warnings | ~1,000 |
| Info | ~5,000 |
| Measures with issues | 92% |
| Top findings | NO_COMMENTS, CALCULATE_NO_FILTER, NO_DISPLAY_FOLDER |

---

## 6. Measure Dependency Tracker

### 6.1 Architecture

```
dependency_tracker.py
+-- parse_dax_references(expr) -> dict
|   +-- measures: [Name] references
|   +-- columns: 'Table'[Column] references
|   +-- tables: 'Table' references
|   +-- functions: FUNC() calls
|
+-- DependencyTracker class
|   +-- build_graph(measures, tables)
|   |   +-- Build bidirectional adjacency list (forward + reverse)
|   +-- get_dependencies(name, table) -> dict
|   |   +-- BFS: forward deps + transitive closure
|   +-- get_impact(name, table) -> dict
|   |   +-- BFS: reverse impact + transitive closure
|   +-- detect_circular_dependencies() -> list[cycle]
|   |   +-- DFS (3-color marking)
|   +-- get_topological_order() -> list[str]
|   |   +-- Kahn's algorithm (BFS + in-degree)
|   +-- get_most_used(n) -> list[(key, count)]
|   +-- get_orphan_measures() -> list[str]
|   +-- format_summary() / format_dependencies() -> str
```

### 6.2 Implementation Details

- **Graph algorithms** -- BFS transitive closure, DFS cycle detection, Kahn topological sort
- **Measure name disambiguation** -- when multiple tables share a measure name, prefer current table context
- **Pure Python** -- no SSAS connection required; can analyze BIM files offline
- **O(N+E) complexity** -- near-instant analysis of thousands of measures

### 6.3 Benchmark Data

Tested against a production model with ~1,680 measures:

| Metric | Value |
|--------|-------|
| Measures with dependencies | 94% |
| Measures with dependents | 69% |
| Circular dependencies | 0 |
| Orphan references | 0 |
| Most referenced measure | 440 dependents |
| Typical measure impact | 17 deps, 27 direct + 281 transitive = 308 affected |

---

## 7. Remote Connection (REST API)

### 7.1 Architecture

```
ssas_client.py
+-- RemotePowerBI (REST API client)
|   +-- acquire_token() -> MSAL username/password
|   +-- Token cache -> .pbi_token_cache.json (59min expiry)
|   +-- list_workspaces() -> GET /groups
|   +-- list_datasets() -> GET /groups/{id}/datasets
|   +-- execute_dax() -> POST /datasets/{id}/executeQueries
|
+-- RemotePowerBIWithSchema (BIM-enhanced)
    +-- load_schema(bim_path) -> Parse BIM JSON
    +-- get_tables() / get_columns() / get_measures() -> BIM metadata
    +-- search_dax() -> BIM full-text search
    +-- get_column_values() / get_table_row_count() -> Remote live query
```

### 7.2 Authentication Flow

```
[PBI_USERNAME] + [PBI_PASSWORD] (env vars)
  v
acquire_token_by_username_password()
  v
JWT Token (aud = Power BI API scope)
  v
REST API: Authorization: Bearer {token}
  v
GET /groups -> 200 OK (workspace list)
POST /executeQueries -> 200 OK (DAX results)
```

### 7.3 Capability Boundaries

| Capability | REST API | Limitation |
|------------|:---:|------|
| EVALUATE queries | Yes | Standard DAX syntax |
| DMV queries ($SYSTEM.*) | No | Stripped by API |
| INFO functions | No | "Failed to execute DAX query" |
| Metadata read | No | Push API datasets only |
| Write operations | No | REST API is read-only |

### 7.4 XMLA Endpoint Status

The XMLA endpoint for Power BI China (21Vianet) remains under investigation:

- Token is valid (REST API returns 200)
- XMLA endpoint returns 400 (request format mismatch)
- Latest ADOMD.NET 19.114.8 tested, same result
- Likely requires tenant admin to enable "Allow XMLA endpoints" setting

---

## 8. BIM-Driven Remote Queries

### 8.1 Design Motivation

REST API does not support metadata queries (DMV/INFO), but BIM files share the same table structure as the remote model. By combining BIM for metadata and REST API for data, we achieve full remote query capability.

### 8.2 Data Flow

```
+--------------+     +--------------+     +------------------+
|  BIM File     |     |  MCP Server  |     |  Power BI Cloud  |
|  (local JSON) |     |              |     |  (REST API)      |
+--------------+     +--------------+     +------------------+
| N tables      |----->| Schema cache |     |                  |
| N columns     |     |              |     |                  |
| N measures    |     | get_columns()|     |                  |
|               |     | get_measures()|    |                  |
|               |     | search_dax() |     |                  |
|               |     |              |     |                  |
|               |     | execute_dax()|----->| VALUES(Table[...])|
|               |     | COUNTROWS()  |<-----| N rows           |
+--------------+     +--------------+     +------------------+
```

### 8.3 Real-World Validation

Tested against a production model with 117 tables, 1,917 columns, 1,680 measures:

| Query | Source | Result |
|-------|--------|--------|
| Table list | BIM | 117 tables (72 visible) |
| Column info | BIM | 17 columns per table (avg) |
| Column values | REST API | All distinct values retrieved |
| Row counts | REST API | Millions of rows counted |
| Business KPIs | REST API | Revenue, conversion rates, etc. |

---

## 9. Dual-Mode Connection Strategy

### 9.1 Routing Logic

```
_get_connection(mode="auto")
  |
  +-- mode="write" -> Force local (fail if no PBIX open)
  +-- mode="remote" -> Force remote (fail if not configured)
  |
  +-- mode="auto" (default)
      +-- 1. Local PBIX found? -> Local mode (ADOMD.NET)
      |     +-- All 26 tools available
      +-- 2. No local, remote configured? -> Remote mode
      |     +-- BIM configured? -> RemotePowerBIWithSchema
      |     +-- No BIM? -> RemotePowerBI (DAX only)
      +-- 3. Neither -> Error with guidance
```

### 9.2 Mode Capability Matrix

| Capability | Local | Remote | Remote+BIM |
|------------|:---:|:---:|:---:|
| Read metadata | DMV | N/A | BIM file |
| DAX queries | ADOMD.NET | REST API | REST API |
| Create/Modify Measures | TOM | N/A | N/A |
| Full-text DAX search | DMV | N/A | BIM file |
| BPA analysis | Live | N/A | BIM file |
| Dependency tracking | Live | N/A | BIM file |
| Power Query audit | DMV | N/A | N/A |

---

## 10. Solution Comparison

### 10.1 Capability Matrix

| Capability | Official MCP | Community | This Project |
|------------|:---:|:---:|:---:|
| Read model metadata | DMV / REST | DMV / REST | DMV / BIM |
| Modify Measures | TMDL | No | **TOM** |
| Create/Delete Measures | Yes | No | **Yes** |
| Create tables/columns | Yes | No | **Yes** |
| Execute DAX queries | XMLA | ADOMD.NET | ADOMD.NET / REST |
| Full-text DAX search | N/A | Partial | **Full** |
| Power Query audit | N/A | No | **Yes** |
| Relationships | Yes | No | **Yes** |
| Security roles | Yes | No | **Yes** |
| Transactional batch | Yes | No | **Yes** |
| Model topology | Yes | No | **Yes** |
| DAX BPA (18 rules) | N/A | No | **Yes** |
| Dependency tracking | N/A | No | **Yes** |
| Auto-discovery | Yes | Manual | **Zero-config** |
| Auth | Varies | Azure AD | **None / MSAL** |
| Runtime | Node.js 20+ | Python | Python |
| Offline | Varies | Mixed | **Local: Yes** |

### 10.2 Use Case Recommendations

| Scenario | Recommended |
|----------|-------------|
| Enterprise Fabric, Entra ID ready | Official MCP (local) |
| Cloud dataset query & analysis | Official MCP (remote) |
| Local PBIX development, zero-config | **This Project** |
| Batch Measure modification | **This Project** |
| DAX full-text search | **This Project** |
| DAX code quality review | **This Project** |
| Measure impact analysis | **This Project** |
| Power Query audit | **This Project** |
| Offline environment | **This Project** |
| Python environment preference | **This Project** |

---

## 11. Remote Connection Architecture

### 11.1 Dual-Mode Connection Flow

```
+---------------------------------------------------------+
|                    MCP Server                            |
|                                                         |
|  _get_connection(mode)                                   |
|    |                                                    |
|    +-- mode="auto" (default)                            |
|    |   +-- Step 1: discover local PBIX instances        |
|    |   |   +-- Found -> Local mode (ADOMD.NET)           |
|    |   |   |   +-- Read: DMV ($SYSTEM.TMSCHEMA_*)       |
|    |   |   |   +-- Write: TOM (model.SaveChanges)       |
|    |   |   |   +-- All 26 tools available               |
|    |   |   +-- Not found -> Step 2                       |
|    |   |                                                |
|    |   +-- Step 2: check remote config                  |
|    |       +-- PBI_XMLA_SERVER set?                     |
|    |       |   +-- Try XMLA (ADOMD.NET + token)         |
|    |       |   |   +-- Success -> XMLA mode (rare)       |
|    |       |   |   +-- Fail -> REST API fallback         |
|    |       |   |       +-- PBI_BIM_PATH set?            |
|    |       |   |       |   +-- RemotePowerBIWithSchema  |
|    |       |   |       +-- No BIM -> RemotePowerBI       |
|    |       |   +-- Not set -> Error                      |
|    |       +-- Neither -> Error with guidance            |
|    |                                                    |
|    +-- mode="local" -> Force local only                  |
|    +-- mode="remote" -> Force remote only                |
|    +-- mode="write" -> Local required (fail if remote)   |
+---------------------------------------------------------+
```

### 11.2 REST API Authentication

```
+------------------------------------------------------+
|  Token Acquisition                                   |
|                                                      |
|  PBI_USERNAME + PBI_PASSWORD env vars                |
|    v                                                 |
|  acquire_token_by_username_password()                |
|    v                                                 |
|  JWT Token (Bearer)                                  |
|                                                      |
|  Token Cache: .pbi_token_cache.json                  |
|    - Expiry: 59 minutes                              |
|    - 5-minute buffer before refresh                  |
|    - Auto-refresh on expiry                          |
+------------------------------------------------------+
```

### 11.3 BIM Schema Integration

```
+------------------------------------------------------+
|  RemotePowerBIWithSchema                             |
|                                                      |
|  load_schema(bim_path)                               |
|    v                                                 |
|  Parse BIM JSON -> Lookup Tables                      |
|    +-- tables: {name -> {columns, measures, hidden}}  |
|    +-- column_index: {(table, col) -> info}           |
|    +-- measure_index: {(table, measure) -> info}      |
|                                                      |
|  Query Methods:                                      |
|    get_tables() -> BIM schema                         |
|    get_columns(table) -> BIM schema                   |
|    get_measures() -> BIM schema                       |
|    search_dax(pattern) -> BIM schema (fast)           |
|    get_column_values(table, col) -> REST API (live)   |
|    get_table_row_count(table) -> REST API (live)      |
|    execute_dax(query) -> REST API (live)              |
+------------------------------------------------------+
```

## 12. Power Query Research Findings

### 12.1 M Code Storage Location

After investigating multiple paths (DataMashup ZIP extraction, Microsoft.Mashup API, xmSQL parsing), the confirmed location of M code is:

```
$SYSTEM.TMSCHEMA_PARTITIONS.QueryDefinition
```

This is the `QueryDefinition` column in the SSAS DMV partitions table, containing the full Power Query M expression for each table.

### 12.2 Modification Limitations

- `MPartitionSource.Expression` property is **readable and writable** (TOM API)
- Power BI Desktop **validates and reverts** structural M code changes on refresh
- Only comment-level modifications can persist (verified)
- Conclusion: **M code is readable but not structurally modifiable** through TOM. This is Power BI Desktop's design protection mechanism.

---

## 13. References

- Microsoft Learn: [Power BI MCP servers overview (Preview)](https://learn.microsoft.com/en-us/power-bi/developer/mcp/mcp-servers-overview)
- Anthropic: [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- Microsoft Docs: [Tabular Object Model (TOM)](https://learn.microsoft.com/en-us/analysis-services/tom/introduction-to-the-tabular-object-model-tom-in-analysis-services-amo)
- DMV Reference: `$SYSTEM.TMSCHEMA_MEASURES`, `$SYSTEM.TMSCHEMA_PARTITIONS`, `$SYSTEM.TMSCHEMA_TABLES`, `$SYSTEM.TMSCHEMA_COLUMNS`

---

## 14. Appendix: Cost Estimation

### Project Scale

| Metric | Count |
|--------|-------|
| Total files | 90+ |
| Code volume | ~550 KB |
| Tools | 26 |
| Core modules | 6 (ssas_client, bpa, dependency_tracker, bim_reader, power_query_ssas, RemotePowerBI) |
| BPA rules | 18 (extensible) |
| Skill workflows | 12 |
| Test suites | 31 |
| Documentation | 5 documents |

### Time Investment

| Phase | Hours |
|-------|-------|
| Core infrastructure (MCP + Skill + SSAS + 8 core tools) | 8h |
| Power Query (research + reader + audit) | 4h |
| Extended tools (relationships/validation/snapshot/roles/CRUD/batch) | 8h |
| DAX optimization (model graph/context pre-check/channel analysis) | 4h |
| BPA + Dependency Tracker (development + integration + testing) | 4h |
| Remote connection (REST API + BIM + dual-mode + MSAL auth) | 4h |
| **Total** | **~32h** |

### Cost Equivalents

| Item | Estimate |
|------|----------|
| Developer time | 32h x internal hourly rate |
| Claude Code Token | 5 days of intensive conversation |
| Equivalent outsourcing | 23 tools + 5 docs + 31 tests ~ 80-120h x $100-150/h = **$8,000-$18,000** |
| vs Official solution | No Entra ID setup, no Node.js environment |

### Core Value

- **Zero marginal cost distribution** -- one-prompt deployment for teammates
- **Ecosystem gap filled** -- only Python MCP with TOM write + BPA + dependency tracking
- **Reusable** -- applicable to any Power BI Desktop project