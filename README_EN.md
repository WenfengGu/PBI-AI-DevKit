# PBI AI DevKit

> Power BI AI Development Toolkit for Claude Code -- read, search, and modify Power BI models with dual-mode local/remote connectivity.

---

## Overview

### The Power BI + AI Landscape

As of July 2026, there are three main paths for AI assistants to interact with Power BI:

| Solution | Type | Connection | Write Capability |
|----------|------|------------|:---:|
| **Official Power BI MCP (Preview)** | Microsoft | Local modeling / Cloud query | **Read + Write + Query** |
| **Community Power BI MCP** | Open-source | REST API / Local SSAS | Read-only |
| **This Project (PBI AI DevKit)** | Open-source | Local SSAS + Remote REST API | **Read + Write (local)** |

### Feature Comparison

| Capability | Official MCP | Community | This MCP |
|------------|:---:|:---:|:---:|
| Read model metadata | Yes | Yes | Yes |
| Modify Measures | Yes (TMDL) | No | **Yes (TOM)** |
| Create/Delete Measures | Yes | No | **Yes** |
| Create tables/columns | Yes | No | **Yes** |
| Execute DAX queries | Yes | Yes | Yes |
| Full-text DAX search | Not mentioned | Partial | **Full-text** |
| Power Query audit | Not mentioned | No | **Yes** |
| Relationship management | Yes | No | **Yes** |
| Security roles | Yes | No | **Yes** |
| Transactional batch | Yes | No | **Yes** |
| Model topology graph | Yes | No | **Yes** |
| DAX best practice analysis | Not mentioned | No | **Yes (18 rules)** |
| Measure dependency tracking | Not mentioned | No | **Yes (fwd/rev/cycles)** |
| Report layout parsing | No | No | **Yes (pages/visuals/fields)** |
| Report measure usage audit | No | No | **Yes (+ BIM cross-check)** |
| DAX change safety preview | Not mentioned | No | **Yes** |
| PBIX safe modification | Not mentioned | No | **Yes (anti-corruption)** |
| Remote DAX queries | Yes | No | **Yes (REST API)** |
| BIM-driven remote queries | Not mentioned | No | **Yes** |
| Local/remote dual-mode | Yes | No | **Yes (local-first)** |
| Auto-discovery | Yes | Manual | **Zero-config** |
| Authentication | Varies | Azure AD | **Local: none / Remote: MSAL** |
| Deployment | npx + config | Manual | **One prompt to Claude** |

---

## Deployment

### Automatic (Recommended)

Send the following to Claude Code:

> Please download and deploy PBI AI DevKit from GitHub:
> https://github.com/WenfengGu/PBI-AI-DevKit
>
> 1. Download and extract to `%USERPROFILE%\PBI-AI-DevKit`
> 2. Run `pip install pythonnet msal`
> 3. Auto-detect Power BI Desktop installation path
> 4. Generate `.mcp.json` configuration
> 5. Install Power BI Skill to `~/.claude/skills/`
> 6. Run `test_connection.py` to verify

Open a PBIX file in Power BI Desktop and you're ready to go.

### Manual Setup

1. `git clone` this repo
2. `pip install pythonnet msal`
3. Copy `.mcp.json.template` to `.mcp.json`, update paths
4. Restart Claude Code

---

## Dual-Mode Connection

The server uses a **local-first, remote-fallback** strategy:

| Mode | Trigger | Read | Write | Metadata |
|------|---------|:---:|:---:|----------|
| **Local** | PBIX open in Power BI Desktop | Full | Full | DMV (real-time) |
| **Remote** | No local PBIX + env var configured | DAX queries | N/A | BIM file |

### Remote Connection Configuration

Add to your `.mcp.json`:

```json
{
  "env": {
    "PBI_XMLA_SERVER": "powerbi://api.powerbi.cn/v1.0/myorg/MyWorkspace",
    "PBI_XMLA_DATABASE": "My Semantic Model",
    "PBI_USERNAME": "your.email@company.com",
    "PBI_PASSWORD": "your-password",
    "PBI_BIM_PATH": "path/to/model.bim"
  }
}
```

---

## What Can It Do?

### Explore Your Model

> "What tables and measures are in this model?"

### Find Hidden Dependencies

> "Which measures reference the 'Sales[Amount]' column?"

### Batch Modify Measures (local only)

> "Replace all 'OldColumn' with 'NewColumn' in every measure."

### Write Correct DAX

> "Create a MTD New Customers measure."
> -> Finds existing logic -> builds on it

### DAX Code Quality Review

> "Run a best practice analysis on all my DAX measures."
> -> 18 rules: performance, correctness, maintainability, naming

### Measure Impact Analysis

> "What will break if I change the 'Total Sales' measure?"
> -> Forward dependencies, backward impact, transitive effects

### Analyze Report Structure

> "Which measures are used on the 'Sales Overview' page?"
> -> Lists all visuals, fields, and measure bindings on that page

### Cross-Check Report vs Model

> "Are there any unused measures in this report?"
> -> BIM cross-check against report layout, identifies dead code

### Preview DAX Changes Safely

> "Preview what happens if I replace 'LY' with 'PY' in all measures."
> -> Detects comment-scope conflicts, bracket mismatches, before any write

### Query Remote Models

> "Show me this year's sales by product category."
> -> REST API query against the configured remote dataset

---

## 27 Tools

| Category | Tools |
|----------|-------|
| Discovery | `discover`, `get_model_info`, `get_model_graph` |
| Read | `get_tables`, `get_measures`, `get_columns`, `get_relationships`, `get_roles` |
| Search | `search_dax`, `audit_power_query` |
| Query | `run_dax`, `validate_dax` |
| Analysis | `bpa_analyze`, `dependency_analyze` |
| Report | `get_report_structure`, `get_report_measures`, `get_report_field_usage` |
| Export | `export_model_snapshot`, `get_power_query` |
| Create | `create_measure`, `create_table`, `create_column`, `create_relationship` |
| Modify | `replace_in_measure`, `validate_dax_change` |
| Delete | `delete_measure` |
| Batch | `batch_operations` |

---

## FAQ

### Q: "No Power BI Desktop instances found"
**A:** Make sure Power BI Desktop is running with a PBIX file open. Or configure a remote connection.

### Q: Can I modify measures in remote mode?
**A:** No. Write operations require a local PBIX file.

### Q: Does this work on Mac?
**A:** Local mode requires Windows (SSAS engine). Remote mode works cross-platform.

### Q: "pythonnet not found"
**A:** Run `pip install pythonnet`

---

## Recent Updates

See [CHANGELOG.md](CHANGELOG.md) for full history.

| Version | Date | Highlights |
|---------|------|------------|
| **1.4.3** | 2026-07-14 | PBIX safe modification (`pbix_safe.py`), anti-corruption |
| **1.4.2** | 2026-07-13 | DAX change safety preview (`validate_dax_change`) |
| **1.4.0** | 2026-07-13 | Report layout parsing — 3 new tools |
| **1.2.0** | 2026-07-13 | Remote REST API, BIM-driven queries, dual-mode connection |

---

## Technical Info

| Item | Detail |
|------|--------|
| Version | 1.4.3 |
| License | MIT |
| Python | 3.11+ |
| Dependencies | pythonnet, msal, Power BI Desktop |
| Security | Local: offline / Remote: MSAL encrypted auth |

---

## File Structure

```
+-- server.py               MCP server (27 tools, dual-mode)
+-- ssas_client.py           Connection layer (local + remote + BIM)
+-- bpa.py                   DAX Best Practice Analyzer (18 rules)
+-- dependency_tracker.py    Measure dependency tracker
+-- bim_reader.py            BIM file reader/writer
+-- power_query.py           Power Query extraction
+-- power_query_ssas.py      Power Query SSAS reader
+-- report_parser.py         PBIX report layout parser
+-- dax_safe_modify.py       DAX modification safety utility
+-- pbix_safe.py             PBIX safe modification (anti-corruption)
+-- setup.bat                One-click deployment
+-- deploy.ps1               Auto-deployment script
+-- requirements.txt
+-- .mcp.json.template       Configuration template
+-- LICENSE
+-- docs/
|   +-- technical-whitepaper.md
|   +-- why-we-built-our-own-mcp.md
+-- tests/
    +-- TEST_RECORDS.md
```