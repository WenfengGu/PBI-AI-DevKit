---
name: powerbi-model
description: >
  Read, search, and modify Power BI Desktop models. Use this skill when the
  user asks to directly interact with an open PBIX file (read/write measures,
  tables, DAX, Power Query, relationships) via the MCP server.
trigger:
  - "open PBIX"
  - "PBIX file"
  - "get_measures"
  - "run_dax"
  - "discover instance"
  - "validate_dax"
  - "create_measure"
  - "replace_in_measure"
  - "search_dax"
  - "Power Query audit"
  - "model snapshot"
  - "MCP server"
model: claude-sonnet-5
---

# Power BI Model Skill

You have access to the **PBI AI DevKit** tools. Use them whenever
the user asks to directly interact with an open PBIX file (reading/writing
measures, DAX, tables, Power Query, relationships).

The MCP server supports **dual-mode** connection:
- **Local mode** (default): PBIX open in Power BI Desktop -> 23 tools, full read/write
- **Remote mode** (auto-fallback): No PBIX open -> BIM schema + REST API, read-only DAX queries

---

## 🔴 MODE SELECTOR -- READ THIS FIRST

### Connection Mode

**Always start with `discover` to determine the active mode:**

| `discover` output | Mode | Capabilities |
|-------------------|------|--------------|
| Shows local PBIX instances | **Local** | Full 23 tools: read + write + metadata |
| "No Power BI Desktop instances" + remote configured | **Remote** | Read-only: BIM metadata + REST API DAX queries |
| Neither | **None** | Tell user to open PBIX or configure remote |

**Write operations (create_measure, delete_measure, replace_in_measure, etc.) ONLY work in local mode.**
In remote mode, tell the user: "This requires a local PBIX. Please open the file in Power BI Desktop."

### Step 1: Context Quick-Exit (方案 D)

**Immediately exit detailed instructions if ANY of these are true:**

| Detection Signal | Action |
|-----------------|--------|
| User is writing/editing a **document** (技术文档, spec, BRD, JIRA, handover, README) | -> Stay in **LIGHTWEIGHT** mode |
| User is discussing **architecture** or **model design** (方案, 架构, 设计, roadmap) | -> Stay in **LIGHTWEIGHT** mode |
| User is discussing the **skill itself** (skill 配置, trigger, MCP 工具改进) | -> Stay in **LIGHTWEIGHT** mode |
| User is doing **code review** of a file that mentions MCP tools | -> Stay in **LIGHTWEIGHT** mode |
| User mentions MCP tools in a **planning context** ("Phase 2 用 create_measure") | -> Stay in **LIGHTWEIGHT** mode |
| Multiple recent turns are about non-PBIX topics (文件操作, Git, 文档编写) | -> Stay in **LIGHTWEIGHT** mode |

### Step 2: Intent Classification (方案 B)

**If context is ambiguous, classify the user's intent:**

| User says (examples) | Intent | Mode |
|---------------------|--------|------|
| "帮我改一下这个 measure" / "执行这个 DAX" / "查一下模型里有哪些表" | **Operate PBIX** | -> **FULL** mode |
| "这个方案里 measure 怎么写" / "文档中需要描述 create_measure 的用法" / "技术规范怎么写" | **Discuss/Document** | -> **LIGHTWEIGHT** mode |
| Ambiguous: "帮我看看这个 DAX" (no PBIX open) | **Unclear** | -> Ask: "你要我操作打开的 PBIX 模型还是讨论这段代码？" |

### Step 3: Mode Activation (方案 C)

| Mode | What's Loaded | Trigger to Expand |
|------|--------------|-------------------|
| **LIGHTWEIGHT** (default) | Context Boundaries + Tools list + Basic rules + Important Notes | User says action words: "执行", "操作", "修改", "帮我改", "帮我写", "run", "create", "do it" |
| **FULL** | All of the above + Workflow Guidelines + DAX Troubleshooting + Common Patterns | (Full mode loads when confirmed via Step 1/2) |

**In LIGHTWEIGHT mode, you MUST NOT:**
- Run pre-flight checks on DAX code
- Apply context control checklists
- Dive into DAX syntax troubleshooting
- Explain DAX pitfalls unless explicitly asked
- Apply MANDATORY workflow rules from the FULL mode section

---

## ⚠️ Context Boundaries

**This skill is for DIRECT PBIX MODEL INTERACTION only.** It is NOT for:

| Scenario | Use Skill? | Reason |
|----------|-----------|--------|
| User asks to write/modify a measure in an open PBIX | ✅ YES | MCP tool needed |
| User asks to run DAX against an open model | ✅ YES | MCP tool needed |
| User asks to audit Power Query in an open model | ✅ YES | MCP tool needed |
| User is writing a **technical document or spec** about Power BI | ❌ NO | No MCP interaction |
| User is discussing **architecture or model design** | ❌ NO | No MCP interaction |
| User is reviewing a document that happens to mention DAX | ❌ NO | No MCP interaction |
| User asks a general DAX syntax question (no open PBIX) | ❌ NO | No MCP interaction |
| User is planning a **development roadmap** | ❌ NO | No MCP interaction |
| User is discussing the **skill configuration** itself | ❌ NO | Meta-discussion |
| User mentions tool names in a **JIRA/BRD/spec** context | ❌ NO | Documentation context |

---

## DAX: Measure vs Query

When the user asks for DAX, distinguish between two different things:

| User says | They want | Return |
|-----------|-----------|--------|
| "写一个 DAX" / "DAX 逻辑" / "Measure 怎么写" | Measure 定义 | `Measure = CALCULATE(...)` |
| "查询一下" / "跑个数" / "EVALUATE" | DAX 查询 | `EVALUATE SUMMARIZECOLUMNS(...)` |

**Default rule:** When the user asks for DAX without specifying, assume they want a **Measure definition** (not a query). Only use EVALUATE when they explicitly ask for data/numbers/statistics.

---

## Available Tools

| Tool | Use When |
|------|----------|
| `discover` | User asks "what PBI files are open?" |
| `get_model_info` | User asks "tell me about this model" |
| `get_tables` | User asks "what tables are in this model?" |
| `get_measures` | User asks "show me all measures" or "find measures with WTD in name" |
| `get_columns` | User asks "what columns does the Calendar table have?" |
| `search_dax` | User asks "which measures reference YEAR WEEK?" or "find all DAX with X" |
| `run_dax` | User asks "run this DAX query" or "what does EVALUATE X return?" |
| `replace_in_measure` | User asks "fix this measure" or "replace X with Y in measure Z" |
| `get_power_query` | User asks "show me the Power Query for this table" or "what M code is behind X?" |
| `audit_power_query` | User asks "are there any Power Query optimizations?" or "audit my M code" |
| `get_relationships` | User asks "how are tables connected?" or "show me the model relationships" |
| `validate_dax` | User asks "is this DAX correct?" or "validate this expression before creating" |
| `export_model_snapshot` | User asks "save a snapshot" or "export the model structure" |
| `run_dax` (multi-query) | User asks "give me a performance summary" or "analyze June sales" |
| `create_measure` | User asks "create a new measure" or "add a KPI" |
| `delete_measure` | User asks "remove this measure" or "delete the test measure" |
| `get_roles` | User asks "show me security roles" or "what RLS is configured?" |
| `create_table` | User asks "create a new table" |
| `create_column` | User asks "add a column to this table" |
| `batch_operations` | User asks "do multiple changes at once" or "batch create these measures" |

---

## Important Notes

- The MCP server connects to **localhost** -- no network, no auth required
- Power BI Desktop must be **running with the PBIX file open**
- The SSAS port is auto-discovered -- no manual configuration needed
- Modifications via `replace_in_measure` are **immediately saved** to the model
- Always verify changes in Power BI Desktop after batch modifications

---

# ⬇️ FULL MODE ONLY -- DO NOT READ BELOW IN LIGHTWEIGHT MODE ⬇️

> **GATE CHECK:** You should only be reading this section if:
> 1. The user explicitly asked to operate on an open PBIX model, AND
> 2. The context is NOT about documentation/planning/code review, AND
> 3. The user has confirmed intent (or it's unambiguous)

---

## Workflow Guidelines

### 1. Discovery First
Always start with `discover` to find running Power BI Desktop instances.
If no instances found, tell the user to open a PBIX file in Power BI Desktop.

### 2. Confirm Target Before Modify
**Before ANY modification (Measure, Power Query, or model structure), you MUST:**

1. **Identify the target** -- use `discover` to list all open PBI instances with their window titles, ports, and database names
2. **Present a confirmation** -- show the user exactly which instance you will modify:
   ```
   I will modify:
     PBIX: PBIX: Sales Report.pbix
     Port: 50079
     Database: d9557f83-...
     Table:  Store
     Action: Replace Power Query M code with optimized version
   ```
3. **Wait for explicit approval** -- do NOT proceed until the user says "yes", "go ahead", "confirm", etc.
4. **If multiple instances are open** -- list ALL instances and ask the user to confirm which one to target. Do NOT proceed until the user explicitly selects one. Example:
   ```
   Warning: 2 Power BI instances are open:
     [1] Port 50079 -- Database: a1b2c3d4... (PBIX: Sales Report.pbix)
     [2] Port 51598 -- Database: e8f9a0b1... (Sales Report.pbix)
   Which one should I modify? Please confirm by number or filename.
   ```
5. **If the window title is ambiguous** (e.g., "CN\user") -- tell the user and ask for clarification

**Rationale:** Modifying the wrong PBIX file can cause data loss. Power BI Desktop may have multiple instances open, and the SSAS port is not directly linked to a filename. Always confirm the target before modifying.

### 3. Understand Before Create
**Before creating any new Measure, follow this mandatory workflow:**

1. **Search for existing related measures** -- use `get_measures` with `name_filter` to find measures with similar names (e.g., "NEW CLIENT", "MTD", "Customer")
2. **Read their full DAX** -- use `get_measures` to retrieve the complete DAX expression of each candidate
3. **Identify the business logic** -- understand what columns and filters define the concept (e.g., `ISFIRSTTRANSACTION = 1` defines "new client")
4. **Trace the dependency chain** -- check which base measures are referenced and what they do
5. **Build on existing logic** -- your new measure should reference existing model measures, not recreate logic from scratch
6. **Confirm with the user** -- explain what you found and how you plan to extend it, get approval before creating

**Example -- How NOT to do it:**
```
User: "Create a MTD New Customers measure"
WRONG: TOTALMTD([Customers (N)], 'Calendar'[DATE])  -- missed ISFIRSTTRANSACTION filter
```

**Example -- Correct approach:**
```
1. get_measures(name_filter="NEW CLIENT")  -> finds [NEW CLIENTS]
2. Read DAX: CALCULATE([Customers (N)], KEEPFILTERS('Retail Sales'[ISFIRSTTRANSACTION] = 1))
3. Understand: "new client" = ISFIRSTTRANSACTION = 1
4. Ask user: "Model already has [NEW CLIENTS] with this logic. Create MTD NEW CLIENTS based on it?"
5. Create: TOTALMTD([NEW CLIENTS], 'Calendar'[DATE])
```

### 4. Diagnose Before Fixing
When a user reports broken measures:
1. Use `search_dax` to find all measures containing the problematic reference
2. Use `get_measures` with `name_filter` to list affected measures
3. Present the count and list to the user BEFORE making changes
4. Ask for confirmation, then fix one measure as a test
5. After confirmation, fix the rest

### 5. Always Verify
After any modification:
1. Use `search_dax` again to confirm the old text is gone
2. Use `get_measures` to verify the new text is present
3. Tell the user to verify in Power BI Desktop

### 6. Batch Operations
When fixing multiple measures:
- Use `search_dax` to get the full list
- Fix one measure first as a test via `replace_in_measure`
- Then batch-fix the rest using a Python script (see batch_fix.py pattern)

### 7. DAX Troubleshooting & Best Practices

**Before writing DAX, always run this pre-flight check:**
1. `get_relationships` -> check cross-filter direction between ALL tables involved
2. `get_columns(table="TableA")` + `get_columns(table="TableB")` -> verify which table each column belongs to
3. **Prefer fact table columns** over dimension table columns (e.g., `'Retail Sales'[STORE TYPE]` over `'Store'[STORE TYPE]`)
4. If relationship is single-direction, either use `CROSSFILTER(..., Both)` or switch to fact table column

**This pre-flight check is MANDATORY before writing any DAX involving multiple tables.**

**Common DAX pitfalls:**

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| DISTINCTCOUNT always returns total, not per-group | Single-direction relationship blocks filter propagation | Use fact table column, or `CROSSFILTER(..., Both)` |
| Measure returns same value for all rows in table visual | External filter context is interfering | Use `REMOVEFILTERS(Table[Column])` or `ALL(Table[Column])` |
| Per-customer count is wrong | Iteration context lost inside CALCULATE | Use `ADDCOLUMNS(SUMMARIZE(...))` to pre-compute, then FILTER |
| SELECTEDVALUE returns BLANK | Multiple values in context, or no value selected | Use `HASONEVALUE()` check first, or fall back to `MAX()`/`MIN()` |

**Context control checklist:**
- [ ] Does the measure need to ignore the current visual's row/column filter? -> `REMOVEFILTERS`
- [ ] Does it need to ignore all filters on a table? -> `ALL(Table)`
- [ ] Does it need to preserve some filters? -> `ALLEXCEPT(Table, Column)`
- [ ] Is the relationship single-direction? -> `CROSSFILTER(..., Both)` or use fact table column

**Example: Single-channel customer count**
```
WRONG: DISTINCTCOUNT('Store'[STORE TYPE])  -- blocked by single-direction relationship
WRONG: DISTINCTCOUNT('Retail Sales'[STORE TYPE])  -- returns 1 because external filter on STORE TYPE
RIGHT: CALCULATE(DISTINCTCOUNT('Retail Sales'[STORE TYPE]), REMOVEFILTERS('Retail Sales'[STORE TYPE]))
```

## Common Patterns

### Column Rename Impact Analysis
```
User: "Calendar[YEAR WEEK] was renamed to [MERCH YEAR], what's broken?"
-> search_dax(pattern="YEAR WEEK") -> list affected measures -> ask to fix
```

### Model Exploration
```
User: "Tell me about this Power BI model"
-> get_model_info -> get_tables -> get_measures (first 10)
```

### Finding Specific Measures
```
User: "Show me all WTD measures"
-> get_measures(name_filter="WTD")
```

### Fixing Broken References
```
User: "Fix all measures referencing YEAR WEEK"
-> search_dax -> confirm -> replace_in_measure (one at a time or batch)
```

### Creating New Measures (Understand Before Create)
```
User: "Create a MTD New Customers measure"
-> get_measures(name_filter="NEW CLIENT") -> read DAX -> understand ISFIRSTTRANSACTION
-> discover [NEW CLIENTS] already exists -> propose: TOTALMTD([NEW CLIENTS], ...)
-> confirm with user -> create measure in ClaudeTest folder
```

### Power Query Audit & Analysis
```
User: "Audit my Power Query for optimization"
-> audit_power_query -> identify: query folding, high complexity, duplicate patterns
-> Present findings with specific optimization suggestions

User: "Show me the Power Query for the Customer table"
-> get_power_query(table="Customer") -> return full M code with analysis
```

### Business Performance Analysis
```
User: "Give me a summary of June 2026 sales performance"
-> get_model_info -> understand the model structure
-> get_measures -> identify relevant KPIs (Sales, Customers, etc.)
-> run_dax -> execute targeted queries:
  1. Monthly snapshot (current vs last month vs last year)
  2. Channel breakdown (by Store Type)
  3. Product category analysis
  4. New customer analysis
  5. Year-to-date summary
-> Synthesize findings into a structured summary with MoM/YoY comparisons,
  percentage breakdowns, and actionable insights
```

**Business Analysis Workflow:**
1. Use `get_model_info` and `get_measures` to understand what KPIs are available
2. Identify the relevant dimensions: time (Calendar), channel (Store), product, customer
3. Run 5-6 targeted DAX queries covering: snapshot, channel, product, customer, YTD
4. Present results in a structured table format with MoM/YoY comparisons
5. Highlight anomalies, trends, and actionable insights
6. Always include: percentage breakdowns, growth rates, and key takeaways