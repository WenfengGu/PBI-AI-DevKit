# Changelog

All notable changes to the PBI AI DevKit project.

---

## [1.7.1] - 2026-08-11

### Fixed
- **Remote mode crash**: `get_tables`, `get_measures`, `get_columns`, `search_dax`, `bpa_analyze`, `dependency_analyze`, `get_relationships` all crashed with `AttributeError: 'RemotePowerBI' object has no attribute 'CreateCommand'` when running in remote-only mode (no local PBIX). Root cause: `RemotePowerBI` lacked metadata methods, and `_connect_remote()` only used `RemotePowerBIWithSchema` when `PBI_BIM_PATH` was explicitly set.
- **`RemotePowerBI.Close()` missing**: `finally` blocks in tool handlers called `conn.Close()` which didn't exist on `RemotePowerBI`, causing secondary `AttributeError` that masked the original error.

### Added
- **`_find_bim_file(database_name, search_roots)`** in `ssas_client.py`: Auto-discovers the best matching BIM file by extracting keywords from the database name and scoring `.bim` files in the search path. Returns the latest matching file by modification time.
- **`RemotePowerBI.Close()`** method: Alias for existing `close()` to match the convention used in `server.py` exception handlers.
- **`_no_bim_error(tool_name, database)`** helper in `server.py`: Returns a friendly error message when BIM schema is unavailable for a remote tool, guiding users to export and place a BIM file.

### Changed
- **`_connect_remote()`** now auto-searches for BIM files when `PBI_BIM_PATH` is not set. Uses `_find_bim_file()` to match the database name against `.bim` files in `D:\LVMH_Max\` (configurable via `PBI_BIM_SEARCH_PATH` env var).
- **Tool handlers** (`get_tables`, `get_measures`, `get_columns`, `search_dax`, `bpa_analyze`, `dependency_analyze`, `get_relationships`): Added graceful error handling for remote-without-BIM case instead of crashing with DMV errors.
- **`bpa_analyze` and `dependency_analyze`**: Now support remote mode via BIM schema data, not just local DMV queries.

---

## [1.7.0] - 2026-07-23

### Added
- **Live Connection Auto-Detection & Auto-Fallback**: `_get_connection()` in `server.py` now detects when a local PBIX is a live connection (thin report) and automatically falls back to remote mode using the connection info from the PBIX's `Connections` file. No more cryptic "CurrentCatalog XML/A property was not specified" errors.
- **`_extract_pbix_path()`** helper in `ssas_client.py`: Extracts the PBIX file path from the running PBIDesktop.exe process command line via `wmic`.
- **`_read_pbix_connections()`** helper in `ssas_client.py`: Reads the `Connections` file from inside a PBIX ZIP to detect live connection details (remote server URL, database name).
- **`_parse_connection_string()`** helper in `ssas_client.py`: Parses Power BI connection strings to extract `Data Source` and `Initial Catalog`.
- **`_get_database_name_via_tom()`** helper in `ssas_client.py`: Gets the database name via TOM for local models (more reliable than DMV when catalog is properly set).
- **`_clean_column_name()`** helper in `server.py`: Strips `[Table].[Column]` prefix from column names in `run_dax` output, showing just `Column`.
- **`discover` tool** now shows `pbix_path`, live connection status, and remote server/database info for each local instance.

### Changed
- **`discover_pbi_instances()`** now returns `pbix_path`, `remote_server`, and `remote_database` fields in each instance dict.
- **`get_database_name()`** now tries TOM first for local models, falls back to DMV, and logs a clear warning for empty databases (live connections).
- **`RemotePowerBI.__init__()`** now detects cloud (China vs Global) from the server URL instead of hardcoding `api.powerbi.cn`.
- **`RemotePowerBI.execute_dax()`** now parses HTTP 400 JSON responses to extract just the `DetailsMessage` instead of dumping the full JSON blob.
- **`execute_dmv()`** now catches `CurrentCatalog` XML/A errors and re-raises with a clear message about live connections.
- **Report Parser** formatting methods now use ASCII `->` instead of Unicode `→` for Windows terminal compatibility.
- **Report tools unified**: `get_report_structure`, `get_report_measures`, `get_report_field_usage` merged into single `report_analyze` tool with `mode` parameter (structure/measures/field_usage). Total tools: 27 → 25.

### Fixed
- **`.mcp.json`** server path corrected from `C:\Users\user\` to `d:\LVMH_Max\`.
- **Live connection write errors**: `mode="write"` now gives a clear error message when the PBIX is a live connection (no local database).

---

## [1.4.3] - 2026-07-14

### Added
- **`pbix_safe.py`**: PBIX Safe Modification Utility. Uses config-string replacement to avoid Layout JSON corruption. Auto-backup before save. Prevents the `json.dumps` Layout escaping bug.

### Fixed
- **PBIX corruption bug**: `json.dumps` on entire Layout JSON changes Power BI's original JSON escaping format, causing "file is corrupted" error. Fixed by replacing only the config string in the raw Layout text.

---

## [1.4.2] - 2026-07-13

### Added
- **`dax_safe_modify.py`**: DAX modification safety utility with defensive checks (comment scope detection, bracket validation, human confirmation)
- **`validate_dax_change`** (MCP tool): preview DAX modifications before applying, detects // comment scope and bracket mismatches

### Changed
- Total MCP tools: 26 -> 27 (later unified to 25 in v1.7.0)

---

## [1.4.1] - 2026-07-13

### Added
- **`_extract_report_measures()`** (`report_parser.py`): auto-extracts report-level measures from PBIX `modelExtensions` (Live Connection PBIX local measures)
- **`get_report_measures_dax()`** API: returns full DAX expressions for all report-level measures
- **`--report-measures`** CLI flag: outputs complete DAX for all measures defined in the PBIX

### Fixed
- Live Connection PBIX measure discovery: measures in `modelExtensions` are now detected automatically, no longer falsely reported as "missing from BIM"

---

## [1.4.0] - 2026-07-13

### Added
- **`report_parser.py`** — new module for parsing PBIX report layouts (pages, visuals, field/measure bindings, slicers, filters)
- **`report_analyze`** (MCP tool) — unified report analysis with three modes: `structure` (pages/visuals), `measures` (usage + BIM cross-check), `field_usage` (impact analysis)

### Changed
- Total MCP tools: 23 → 24 (later 27, then unified to 25 in v1.7.0)
- `build_release.py` now includes `report_parser.py`

---

## [1.3.0] - 2026-07-13

### Added
- **`row_val()` helper** (`ssas_client.py`): handles REST API `[Key]` bracket-format column names
- **`execute_dax_scalar()` helper** (`ssas_client.py`): single-value DAX query convenience method
- **`smoke_test.py`** (`tests/`): 6-test connectivity check (Token, Workspace, Dataset, DAX, Business Query, Freshness) — completes in ~10s
- **`dq_preselling.py`** (`tests/`): reusable data quality check for Preselling Reporting CN, auto-discovers column names from BIM, supports `--quick` and `--output` modes
- **`VERSION` file**: single source of truth for version number

### Changed
- `build_release.py` now reads version from `VERSION` file
- `build_release.py` includes new test files (`smoke_test.py`, `dq_preselling.py`)
- `.gitignore` expanded to exclude Claude IDE artifacts
- **Git initialized** — full version control with `git tag` for each release

### Fixed
- `release/` folder is now tracked in git (was previously gitignored)

---

## [1.2.0] - 2026-07-13

### Added
- **Remote REST API connection** (`ssas_client.py`): `RemotePowerBI` class for querying Power BI cloud datasets via `executeQueries` endpoint
- **BIM-driven remote queries** (`ssas_client.py`): `RemotePowerBIWithSchema` class combining BIM metadata with REST API data
- **Dual-mode connection strategy** (`server.py`): `_get_connection()` with local-first, remote-fallback routing
- **MSAL username/password authentication** (`ssas_client.py`): `acquire_token()` with token caching to `.pbi_token_cache.json`
- Workspace discovery via `list_workspaces()` and `list_datasets()`
- BIM schema methods: `get_tables()`, `get_columns()`, `get_measures()`, `search_dax()` from BIM file
- Remote live query methods: `get_column_values()`, `get_table_row_count()`
- `PBI_XMLA_SERVER`, `PBI_XMLA_DATABASE`, `PBI_USERNAME`, `PBI_PASSWORD`, `PBI_BIM_PATH` environment variables
- `discover` tool now shows both local and remote connection status
- Write operations (`create_measure`, `delete_measure`, etc.) properly fail in remote mode with a clear message

### Changed
- Refactored `_get_connection()` to support `mode` parameter: `auto`, `local`, `remote`, `write`
- `discover` tool now shows local PBIX instances, remote config status, and active mode
- Metadata handlers (`get_model_info`, `get_tables`, `get_measures`, `get_columns`, `search_dax`) support BIM schema fallback
- `run_dax` handler supports remote REST API execution
- Updated all documentation to English + Chinese bilingual versions
- Removed device code authentication flow (username/password only)

### Fixed
- `export_model_snapshot` tool definition syntax error (missing closing brace)
- Box-drawing character alignment issues in all documentation diagrams

---

## [1.1.0] - 2026-07-11

### Added
- **DAX Best Practice Analyzer** (`bpa.py`): 18 rules covering performance, maintainability, correctness, and naming
  - Performance rules: `EARLIER_INSTEAD_OF_VAR`, `CALCULATE_NO_FILTER`, `FILTER_VALUES_PATTERN`, `MULTIPLE_FILTER`, `ITERATOR_NO_FILTER`, `SELECTCOLUMNS_ADDCOLUMNS`
  - Maintainability rules: `LONG_EXPRESSION`, `NO_COMMENTS`, `HARDCODED_VALUES`, `NESTED_IF_DEPTH`
  - Correctness rules: `DIVIDE_NO_ALTERNATIVE`, `SWITCH_NO_ELSE`, `ISFILTERED_IN_MEASURE`, `ALL_VS_ALLSELECTED`, `BLANK_COMPARISON`, `USERELATIONSHIP_NO_CALCULATE`, `SELECTEDVALUE_NO_ALTERNATIVE`, `VAR_NO_RETURN`
  - Naming rules: `NO_FORMAT_STRING`, `NO_DISPLAY_FOLDER`
- **Measure Dependency Tracker** (`dependency_tracker.py`): forward/backward dependency analysis, circular dependency detection, topological ordering, impact analysis
- **`bpa_analyze`** tool: Run DAX best practice analysis across all measures
- **`dependency_analyze`** tool: Analyze measure dependencies and impact
- BPA unit tests (22 rules) and Dependency Tracker unit tests (4 scenarios)
- Skill Context Boundaries mechanism (LIGHTWEIGHT / FULL mode switching)

### Changed
- Tool count increased from 21 to 23
- `server.py` updated to v1.1.0
- Updated README, technical whitepaper, test records, and Skill file

---

## [1.0.0] - 2026-07-10

### Added
- **MCP Server** (`server.py`): Hand-written MCP JSON-RPC 2.0 protocol over binary-safe stdio
- **SSAS Client** (`ssas_client.py`): Auto-detection of Power BI Desktop installation, SSAS instance discovery via `netstat` + `tasklist`, DMV queries, DAX execution, TOM model modification
- **Power Query SSAS Reader** (`power_query_ssas.py`): M code extraction from `$SYSTEM.TMSCHEMA_PARTITIONS.QueryDefinition`
- **BIM Reader** (`bim_reader.py`): Read/write Tabular Model Schema (BIM) JSON files
- **21 tools**: `discover`, `get_model_info`, `get_tables`, `get_measures`, `get_columns`, `search_dax`, `run_dax`, `replace_in_measure`, `get_power_query`, `audit_power_query`, `get_relationships`, `validate_dax`, `export_model_snapshot`, `create_measure`, `delete_measure`, `get_roles`, `create_relationship`, `create_table`, `create_column`, `batch_operations`, `get_model_graph`
- **Skill file** (`.claude/skills/powerbi-model.md`): Auto-triggered with 23 keywords, workflow guidelines, DAX troubleshooting
- **Deployment**: `setup.bat` (one-click), `deploy.ps1` (auto-deploy), `test_connection.py` (connection test), `.mcp.json.template`
- **Documentation**: README (Chinese + English), technical whitepaper, project proposal, team survey
- Power Query research: Confirmed M code location, modification limitations
- BIM workspace server: Deploy BIM files to local SSAS instances

### Technical Highlights
- Zero-config, zero-auth for local connections
- TOM (Tabular Object Model) for measure modification
- Power Query M code reading via DMV
- Multi-instance safety confirmation before modifications
- DAX pre-flight checklist (model graph, relationship direction, column ownership)