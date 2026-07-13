# Why We Built Our Own MCP (Plain English)

---

## An Analogy

Think of a Power BI file (PBIX) as a **safe**:

```
Your Report.pbix (safe)
+-- Report/         <- Labels on the outside (visual layout, JSON)
+-- TMDLScripts/    <- Sticky notes (recent changes)
+-- DataModel       <- What's inside (binary, proprietary format)
```

- **ChatGPT has the official key** -- Microsoft gave it one (now also available as Power BI MCP server Preview)
- **Claude doesn't have this key** -- it can only read the labels, not what's inside

We're here to **give Claude a key**.

---

## How Three AIs Interact with Power BI

### ChatGPT: Has the Official Key

```
Me: "Show me all measures in this report"

ChatGPT -> Official Power BI connector -> Opens safe -> Reads measures -> Responds
         (Microsoft-provided, built-in)
```

### Claude (Before): No Key

```
Me: "Show me all measures in this report"

Claude -> Unzips PBIX -> Sees DataModel -> Gibberish -> "I can't read this"
         (only outside)       (binary, proprietary)
```

### Claude (Now): We Made a Key

```
Me: "Show me all measures in this report"

Claude -> Our MCP Server -> Borrows PBI Desktop's key -> Opens safe -> Reads measures -> Responds
         (we built)       (uses PBI Desktop's own DLLs)       (same as ChatGPT)
```

The trick: **we didn't forge a key -- we borrowed the key that Power BI Desktop already has.**

Every computer with Power BI Desktop installed has these files:
```
C:\Program Files\Microsoft Power BI Desktop\bin\
    +-- Microsoft.PowerBI.AdomdClient.dll    <- Can "read"
    +-- Microsoft.AnalysisServices.*.dll      <- Can "write"
```

These are Microsoft's official DLLs. DAX Studio and Tabular Editor use them too. Our MCP simply bridges them to Python so Claude can use them.

---

## Comparison

| Core Question | Official MCP | Claude Before | Claude Now |
|---------------|:---:|:---:|:---:|
| Can open PBIX? | Yes | Unzips the ZIP, but can't read data | Yes, same as official |
| Can list all measures? | Yes | No | Yes |
| Can search DAX formulas? | Partial | No | **Full-text search** |
| Can modify measures? | Yes (TMDL) | No | **Yes (TOM)** |
| Can audit Power Query? | No | No | **Yes** |
| Needs internet? | Varies | No | No |
| Needs Azure account? | Varies | No | No |
| How? | Microsoft official | Impossible | Uses PBI Desktop's built-in DLLs |

---

## Why Not Just Use ChatGPT's Approach?

In one sentence: **ChatGPT's key is custom-made by Microsoft, only fits the ChatGPT/Entra ID lock. Claude's keyhole has a different shape.**

Specifically:
1. Official MCP can auto-discover local instances in Desktop scenarios, no Entra ID required
2. But it requires Node.js runtime (npx), not Python-friendly
3. Our solution: Python, zero-config, one-prompt deployment

---

## What We Built

```
Step 1: Discovered Power BI Desktop's built-in DLL keys
Step 2: Used pythonnet to "translate" Python calls to .NET calls
Step 3: Connected to local Power BI engine via ADOMD.NET
Step 4: Read model metadata via DMV queries (tables, measures, DAX)
Step 5: Enabled measure modification via TOM (Tabular Object Model)
Step 6: Found Power Query M code in TMSCHEMA_PARTITIONS, enabled auditing
Step 7: Packaged as MCP Server + Skill for Claude Code
```

**Result:** Claude now has the same Power BI read/write capabilities as the official MCP, plus full-text DAX search and Power Query audit -- all local, zero-auth, zero-config, no internet needed.