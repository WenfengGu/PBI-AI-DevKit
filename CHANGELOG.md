# Changelog

All notable changes to the PBI AI DevKit project.

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