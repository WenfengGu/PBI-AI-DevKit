# PBI AI DevKit

> Power BI AI Development Toolkit for Claude Code — read, search, and modify Power BI models with dual-mode local/remote connectivity.

---

## Overview

### The Power BI + AI Landscape

As of July 2026, there are three main paths for AI assistants to interact with Power BI:

| Solution | Type | Connection | Write Capability |
|----------|------|------------|:---:|
| **Official Power BI MCP (Preview)** | Microsoft | Local modeling / Cloud query | **Read + Write + Query** |
| **Community Power BI MCP** | Open-source | REST API / Local SSAS | Read-only |
| **This Project (PBI AI DevKit)** | Open-source | Local SSAS + Remote REST API | **Read + Write (local)** |

### Key Findings

1. **Official MCP exists** -- with local (modeling) and remote (query) servers, authentication varies by target
2. **Community solutions are read-only** -- can read metadata, but none support Measure modification
3. **ChatGPT/Copilot integration** -- tied to their respective ecosystems, not available to Claude Code users

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
| Remote DAX queries | Yes | No | **Yes (REST API)** |
| BIM-driven remote queries | Not mentioned | No | **Yes** |
| Local/remote dual-mode | Yes | No | **Yes (local-first)** |
| Auto-discovery | Yes | Manual | **Zero-config** |
| Authentication | Varies | Azure AD | **Local: none / Remote: MSAL** |
| Runtime | Node.js 20+ | Python | Python |
| Deployment | npx + config | Manual | **One prompt to Claude** |
| Offline | Varies | Mixed | **Local: yes / Remote: no** |

### Why Use This?

- **Unified toolchain** -- stay in Claude Code, no need to switch to other AI tools
- **One-prompt deployment** -- non-technical teammates can deploy by sending a GitHub link to Claude
- **Time efficient** -- tool-based access is orders of magnitude faster than manually unzipping PBIX files
- **Reusable** -- works with any Power BI Desktop project

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

### Architecture

```
Skill Layer (Auto-triggered)
  Trigger words -> Power BI tools
  -------------------------------------------
MCP Server (26 tools)
  discover, get_measures, search_dax
  replace_in_measure, run_dax, create_measure
  get_power_query, audit_power_query
  bpa_analyze, dependency_analyze
  batch_operations, get_model_graph
  get_report_structure, get_report_measures
  -------------------------------------------
Connection Layer (Local-first, Remote-fallback)
  Local:  ADOMD.NET + TOM -> msmdsrv.exe
  Remote: BIM Schema + REST API -> Power BI Cloud
```

---

## Dual-Mode Connection

The server uses a **local-first, remote-fallback** strategy:

| Mode | Trigger | Read | Write | Metadata |
|------|---------|:---:|:---:|----------|
| **Local** | PBIX open in Power BI Desktop | Full | Full | DMV (real-time) |
| **Remote** | No local PBIX + `PBI_XMLA_SERVER` configured | DAX queries | N/A | BIM file |
| **Remote+BIM** | Remote + `PBI_BIM_PATH` configured | DAX queries | N/A | BIM file |

### Remote Connection Configuration

Add to your `.mcp.json`:

```json
{
  "env": {
    "PBI_XMLA_SERVER": "powerbi://api.powerbi.cn/v1.0/myorg/MyWorkspace",
    "PBI_XMLA_DATABASE": "My Semantic Model Name",
    "PBI_USERNAME": "your.email@company.com",
    "PBI_PASSWORD": "your-password",
    "PBI_BIM_PATH": "path/to/model.bim"
  }
}
```

---

## What Can It Do?

### Explore Your Model

Ask Claude to understand the model structure instantly:

> "What tables and measures are in this model?"

### Find Hidden Dependencies

Search across all DAX expressions:

> "Which measures reference the 'Sales[Amount]' column?"

### Batch Modify Measures

Rename columns across dozens of measures at once (local mode only):

> "Replace all references to 'OldColumn' with 'NewColumn' in every measure."

### Write Correct DAX

Claude understands existing business logic before creating new measures:

> "Create a MTD New Customers measure."
> -> Finds existing `[NEW CLIENTS]` logic -> builds on it

### Audit Power Query

Get optimization suggestions for your M code:

> "Audit my Power Query for query folding issues."

### DAX Code Quality Review

18 rules covering performance, correctness, maintainability, and naming:

> "Run a best practice analysis on all my DAX measures."

### Measure Impact Analysis

Understand ripple effects before making changes:

> "What will break if I change the 'Total Sales' measure?"
> -> Shows forward dependencies, backward impact, and transitive effects

### Query Remote Models

When no local PBIX is open, automatically query cloud datasets:

> "Show me this year's sales by product category."
> -> REST API query against the configured remote dataset

### BIM-Driven Remote Exploration

Combine BIM schema knowledge with live data:

> "What columns does the Customer table have? What are the distinct regions?"
> -> BIM provides schema (column names), REST API provides data (values)

---

## FAQ

### Q: "No Power BI Desktop instances found"
**A:** Make sure Power BI Desktop is running with a PBIX file open. Or configure a remote connection.

### Q: Can I use both local and remote simultaneously?
**A:** Local takes priority. Open a PBIX -> local mode. Close PBIX -> remote fallback.

### Q: Can I modify measures in remote mode?
**A:** No. Write operations require a local PBIX file. The server will tell you.

### Q: Does this work on Mac?
**A:** Local mode requires Windows (SSAS engine). Remote mode works cross-platform via REST API.

### Q: "pythonnet not found"
**A:** Re-run `setup.bat` or manually: `pip install pythonnet`

---

## Technical Info

| Item | Detail |
|------|--------|
| Version | 1.2.0 (2026-07) |
| License | MIT |
| Python | 3.11+ |
| Dependencies | pythonnet, msal, Power BI Desktop |
| Security | Local: fully offline / Remote: MSAL encrypted auth |
| Test Suites | 31 |

---

## File Structure

```
PBI-AI-DevKit/
+-- server.py               MCP server (26 tools, dual-mode)
+-- ssas_client.py           Connection layer (local + remote + BIM)
+-- bpa.py                   DAX Best Practice Analyzer (18 rules)
+-- dependency_tracker.py    Measure dependency tracker
+-- bim_reader.py            BIM file reader/writer
+-- power_query.py           Power Query extraction module
+-- power_query_ssas.py      Power Query SSAS reader
+-- setup.bat                One-click deployment
+-- test_connection.py       Connection test
+-- deploy.ps1               Auto-deployment script
+-- requirements.txt         Python dependencies
+-- .mcp.json.template       Configuration template (incl. remote)
+-- CHANGELOG.md              Version history
+-- LICENSE
+-- .claude/
|   +-- skills/
|       +-- powerbi-model.md Skill file (dual-mode triggers)
+-- docs/
|   +-- technical-whitepaper.md
|   +-- ...
+-- tests/                   31 test suites
+-- README.md
```