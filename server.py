#!/usr/bin/env python
"""
Power BI Model MCP Server (Self-Contained)
===========================================
Reads and modifies Power BI Desktop dataset models via local SSAS instance.
Implements MCP JSON-RPC 2.0 protocol over stdio.

Requirements:
  - pythonnet (pip install pythonnet)
  - Power BI Desktop running with a PBIX file open
"""

import os
import sys
import json
import traceback
import logging
from pathlib import Path

# Log to stderr to keep stdout clean for MCP protocol
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("pbi-mcp")

sys.path.insert(0, str(Path(__file__).parent))

from ssas_client import (
    discover_pbi_instances,
    connect_to_instance,
    connect_to_remote,
    RemotePowerBI,
    RemotePowerBIWithSchema,
    get_database_name,
    list_databases,
    get_all_tables,
    get_all_measures,
    get_all_columns,
    execute_dmv,
    execute_dax,
    replace_in_measure,
)
from power_query_ssas import (
    get_power_query_m_code,
    analyze_power_query as analyze_m_code,
)
from bpa import DaxAnalyzer, analyze_measures
from dependency_tracker import DependencyTracker, build_and_analyze

SERVER_NAME = "powerbi-model"
SERVER_VERSION = "1.2.0"


# ──────────────────────────────────────────────────────────────
#  MCP Protocol
# ──────────────────────────────────────────────────────────────

def read_message() -> dict | None:
    """Read a JSON-RPC message from stdin using MCP framing.
    Uses binary mode to avoid text-mode buffering issues.
    """
    try:
        # Read headers as bytes until \r\n\r\n
        header_bytes = b""
        while True:
            ch = sys.stdin.buffer.read(1)
            if not ch:
                return None  # EOF
            header_bytes += ch
            if header_bytes.endswith(b"\r\n\r\n"):
                break

        # Parse Content-Length from headers
        content_length = None
        header_text = header_bytes.decode("utf-8")
        for line in header_text.split("\r\n"):
            if line.lower().startswith("content-length:"):
                content_length = int(line.split(":", 1)[1].strip())

        if content_length is None:
            log.warning("No Content-Length header found")
            return None

        # Read body bytes
        body_bytes = sys.stdin.buffer.read(content_length)
        body = body_bytes.decode("utf-8")
        return json.loads(body)
    except Exception as e:
        log.error(f"Read error: {e}")
        return None


def send_message(msg: dict):
    """Send a JSON-RPC message to stdout using MCP framing."""
    body = json.dumps(msg, ensure_ascii=False)
    body_bytes = body.encode("utf-8")
    header = f"Content-Length: {len(body_bytes)}\r\n\r\n".encode("utf-8")
    sys.stdout.buffer.write(header + body_bytes)
    sys.stdout.buffer.flush()


def send_response(req_id, result):
    send_message({"jsonrpc": "2.0", "id": req_id, "result": result})


def send_error(req_id, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    send_message({"jsonrpc": "2.0", "id": req_id, "error": err})


# ──────────────────────────────────────────────────────────────
#  Tool Definitions
# ──────────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "discover",
        "description": "Discover running Power BI Desktop instances with their SSAS ports.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_model_info",
        "description": "Get overall model information: database name, tables, measures, columns count.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"}
            },
        },
    },
    {
        "name": "get_tables",
        "description": "Get all tables in the Power BI model.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"}
            },
        },
    },
    {
        "name": "get_measures",
        "description": "Get all measures from the model. Returns name, table, DAX expression, display folder, and error message.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_filter": {"type": "string", "description": "Filter by table name (substring match)"},
                "name_filter": {"type": "string", "description": "Filter by measure name (substring match, case-insensitive)"},
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
        },
    },
    {
        "name": "get_columns",
        "description": "Get all columns for a specific table.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name (exact match)"},
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
            "required": ["table"],
        },
    },
    {
        "name": "search_dax",
        "description": "Search within all measure DAX expressions for a pattern. Find measures that reference specific columns, tables, or functions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Text to search for in DAX expressions"},
                "case_sensitive": {"type": "boolean", "description": "Case sensitive search (default: false)"},
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "run_dax",
        "description": "Run a DAX query against the model. Use EVALUATE syntax.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "DAX query (EVALUATE ...)"},
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "replace_in_measure",
        "description": "Replace text in a measure's DAX expression. Useful for renaming column references across multiple measures.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "Table name containing the measure"},
                "measure_name": {"type": "string", "description": "Exact measure name"},
                "old_text": {"type": "string", "description": "Text to replace in the DAX expression"},
                "new_text": {"type": "string", "description": "Replacement text"},
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
            "required": ["table_name", "measure_name", "old_text", "new_text"],
        },
    },
    {
        "name": "get_power_query",
        "description": "Read the Power Query (M language) code for a specific table. Returns the full M code, step count, source type, and complexity score.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name (exact match). If omitted, returns all tables."},
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
        },
    },
    {
        "name": "audit_power_query",
        "description": "Audit all Power Query M code in the model for optimization opportunities: query folding, duplicate patterns, high complexity, and more.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
        },
    },
    {
        "name": "get_relationships",
        "description": "Get all relationships between tables in the model. Shows from/to table/column, active status, and cross-filter direction.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
        },
    },
    {
        "name": "validate_dax",
        "description": "Validate a DAX expression without creating a measure. Returns whether the expression is valid and any error details.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "DAX expression to validate"},
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
            "required": ["expression"],
        },
    },
    {
        "name": "export_model_snapshot",
        "description": "Export a lightweight JSON snapshot of the model: tables, measures (with DAX), relationships, and summary statistics. Useful for audit trails and change tracking.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
        },
    },
    {
        "name": "create_measure",
        "description": "Create a new measure in the model. Specify table name, measure name, DAX expression, and optional display folder and format string.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "Table to add the measure to"},
                "measure_name": {"type": "string", "description": "Name of the new measure"},
                "expression": {"type": "string", "description": "DAX expression for the measure"},
                "display_folder": {"type": "string", "description": "Optional display folder"},
                "format_string": {"type": "string", "description": "Optional format string (e.g. '#,0')"},
                "description": {"type": "string", "description": "Optional description"},
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
            "required": ["table_name", "measure_name", "expression"],
        },
    },
    {
        "name": "delete_measure",
        "description": "Delete a measure from the model. Requires confirmation of the exact measure name and table.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "Table containing the measure"},
                "measure_name": {"type": "string", "description": "Exact measure name to delete"},
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
            "required": ["table_name", "measure_name"],
        },
    },
    {
        "name": "get_roles",
        "description": "Get all security roles defined in the model, including their members and table-level filter permissions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
        },
    },
    {
        "name": "create_relationship",
        "description": "Create a new relationship between two columns in different tables. The model will validate and reject if it creates ambiguity.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "from_table": {"type": "string", "description": "Source table name"},
                "from_column": {"type": "string", "description": "Source column name"},
                "to_table": {"type": "string", "description": "Target table name"},
                "to_column": {"type": "string", "description": "Target column name"},
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
            "required": ["from_table", "from_column", "to_table", "to_column"],
        },
    },
    {
        "name": "create_table",
        "description": "Create a new calculated table with a simple ROW expression. The table will have an auto-generated RowNumber column. Use create_measure to add measures to the new table.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "Name of the new table"},
                "expression": {"type": "string", "description": "M expression for the table partition (e.g. ROW(\"Col1\", \"Value\"))"},
                "description": {"type": "string", "description": "Optional description"},
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
            "required": ["table_name", "expression"],
        },
    },
    {
        "name": "create_column",
        "description": "Add a new column to an existing table.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "Table to add the column to"},
                "column_name": {"type": "string", "description": "Name of the new column"},
                "data_type": {"type": "string", "description": "Data type: String, Int64, Double, Boolean, DateTime, Decimal"},
                "source_column": {"type": "string", "description": "Source column name (defaults to column_name)"},
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
            "required": ["table_name", "column_name", "data_type"],
        },
    },
    {
        "name": "batch_operations",
        "description": "Execute multiple operations in a single transaction. If any operation fails, all changes are rolled back. Supports: create_measure, delete_measure, replace_in_measure, create_table, create_column, delete_table.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "operations": {
                    "type": "array",
                    "description": "List of operations to execute. Each operation has: action (create_measure/delete_measure/replace_in_measure), table_name, measure_name, and other action-specific params.",
                    "items": {"type": "object"}
                },
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
            "required": ["operations"],
        },
    },
    {
        "name": "get_model_graph",
        "description": "Get the complete model topology in one call: all tables with their columns, plus all relationships with cross-filter directions. Use this BEFORE writing any DAX involving multiple tables.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
        },
    },
    {
        "name": "bpa_analyze",
        "description": "Run DAX Best Practice Analyzer on all measures. Checks for: DIVIDE without alternative, EARLIER patterns, nested IF > 3 levels, SWITCH without else, redundant CALCULATE, FILTER/VALUES patterns, iterator over large tables, long expressions, hardcoded values, missing format strings, ISFILTERED in measures, and more. Returns a report with errors, warnings, and suggestions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_filter": {"type": "string", "description": "Filter by table name (substring match)"},
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
        },
    },
    {
        "name": "dependency_analyze",
        "description": "Analyze measure dependencies: forward deps (what does this measure depend on?), backward deps/impact analysis (what depends on this measure?), circular dependency detection, orphan measures, most-used measures, and topological ordering. Use this BEFORE modifying or deleting any measure to understand the impact.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "measure_name": {"type": "string", "description": "Measure name to analyze (optional — if omitted, returns full graph summary)"},
                "table": {"type": "string", "description": "Table containing the measure (optional, helps disambiguate)"},
                "port": {"type": "integer", "description": "SSAS port (auto-discover if omitted)"},
            },
        },
    },
]

# ──────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────

def _get_connection(port: int = None, mode: str = "auto"):
    """Get connection with local-first, remote-fallback strategy.

    Returns (conn, port, db, title, is_remote).

    Modes:
      - "auto": local first, remote fallback if local unavailable
      - "local": force local (fail if no PBIX open)
      - "remote": force remote (fail if no remote config)
      - "write": local only, fail if remote (for write operations)
    """
    remote_server = os.environ.get("PBI_XMLA_SERVER", "")
    remote_db = os.environ.get("PBI_XMLA_DATABASE", "")
    bim_path = os.environ.get("PBI_BIM_PATH", "")

    # ── Force remote ──
    if mode == "remote":
        if not remote_server:
            raise RuntimeError("No remote connection configured. Set PBI_XMLA_SERVER env var.")
        return _connect_remote(remote_server, remote_db, bim_path)

    # ── Force local ──
    if mode == "local" or mode == "write":
        if port:
            conn = connect_to_instance(port)
            db = get_database_name(conn)
            return conn, port, db, "", False
        instances = discover_pbi_instances()
        if not instances:
            if mode == "write":
                raise RuntimeError(
                    "Write operations require a local PBIX file. "
                    "Please open the PBIX in Power BI Desktop."
                )
            raise RuntimeError("No Power BI Desktop instances found. Open a PBIX file first.")
        for inst in instances:
            try:
                conn = connect_to_instance(inst["port"])
                db = get_database_name(conn)
                return conn, inst["port"], db, inst.get("title", ""), False
            except Exception as e:
                pass
        raise RuntimeError("Could not connect to any local Power BI instance.")

    # ── Auto: local first ──
    if port:
        try:
            conn = connect_to_instance(port)
            db = get_database_name(conn)
            return conn, port, db, "", False
        except Exception:
            pass

    instances = discover_pbi_instances()
    if instances:
        errors = []
        for inst in instances:
            try:
                conn = connect_to_instance(inst["port"])
                db = get_database_name(conn)
                return conn, inst["port"], db, inst.get("title", ""), False
            except Exception as e:
                errors.append(f"Port {inst['port']}: {e}")

    # ── Auto: remote fallback ──
    if remote_server:
        log.info(f"No local PBIX found, falling back to remote: {remote_server}")
        return _connect_remote(remote_server, remote_db, bim_path)

    raise RuntimeError(
        "No Power BI Desktop instances found and no remote connection configured.\n"
        "Open a PBIX file or set PBI_XMLA_SERVER env var."
    )


def _connect_remote(remote_server: str, remote_db: str, bim_path: str = ""):
    """Connect to remote Power BI, with BIM schema if available."""
    # Try XMLA first, fall back to REST API + BIM
    try:
        log.info(f"Connecting to remote XMLA: {remote_server}, database: {remote_db}")
        conn = connect_to_remote(remote_server, remote_db)
        db = remote_db or get_database_name(conn)
        return conn, 0, db, f"Remote XMLA: {remote_server}", False
    except Exception as e:
        log.warning(f"XMLA failed: {e}, using REST API")
        if bim_path and os.path.exists(bim_path):
            log.info(f"Using BIM schema: {bim_path}")
            conn = RemotePowerBIWithSchema(remote_server, remote_db, bim_path)
            conn.load_schema()
            return conn, 0, remote_db, f"Remote+BIM: {remote_server}", True
        log.info(f"Connecting via REST API: {remote_server}")
        conn = RemotePowerBI(remote_server, remote_db)
        return conn, 0, remote_db, f"Remote: {remote_server}", True


def _format_results(rows: list[dict], title: str, max_rows: int = 200) -> str:
    if not rows:
        return f"{title}\nNo results."
    lines = [title, f"Count: {len(rows)}", "=" * 60]
    for i, row in enumerate(rows):
        if i >= max_rows:
            lines.append(f"\n... ({len(rows) - max_rows} more rows)")
            break
        lines.append(f"\n--- [{i+1}] ---")
        for key, val in row.items():
            if val and len(str(val)) > 500:
                val = str(val)[:500] + "..."
            lines.append(f"  {key}: {val}")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
#  Tool Handlers
# ──────────────────────────────────────────────────────────────

def handle_tool_call(tool_name: str, arguments: dict) -> str:
    try:
        if tool_name == "discover":
            lines = []
            remote_server = os.environ.get("PBI_XMLA_SERVER", "")
            remote_db = os.environ.get("PBI_XMLA_DATABASE", "")
            bim_path = os.environ.get("PBI_BIM_PATH", "")

            # Local
            instances = discover_pbi_instances()
            if instances:
                lines.append(f"=== Local PBIX ({len(instances)} instance(s)) ===")
                for inst in instances:
                    title = inst.get("title", "Unknown")
                    lines.append(f"  Port: {inst['port']}, Title: {title}, PID: {inst['pid']}")
                for inst in instances:
                    try:
                        conn = connect_to_instance(inst["port"])
                        db = get_database_name(conn)
                        conn.Close()
                        lines.append(f"\n  Port {inst['port']} -> Database: {db}")
                    except Exception as e:
                        lines.append(f"\n  Port {inst['port']} -> Error: {e}")
            else:
                lines.append("=== Local PBIX ===\n  No Power BI Desktop instances found.")

            # Remote
            lines.append(f"\n=== Remote Connection ===")
            if remote_server:
                lines.append(f"  Server:   {remote_server}")
                lines.append(f"  Database: {remote_db}")
                lines.append(f"  BIM:      {bim_path if bim_path else 'not configured'}")
                lines.append(f"  Status:   Configured (auto-fallback)")
            else:
                lines.append(f"  Not configured. Set PBI_XMLA_SERVER to enable.")

            lines.append(f"\n=== Mode ===")
            lines.append(f"  Strategy: Local-first, remote-fallback")
            lines.append(f"  Active:   {'Local' if instances else 'Remote (auto)' if remote_server else 'None'}")

            return "\n".join(lines)

        elif tool_name == "get_model_info":
            conn, port, db, title, is_remote = _get_connection(arguments.get("port"))
            if is_remote and hasattr(conn, 'get_model_info'):
                info = conn.get_model_info()
                return (
                    f"Model: {info['database']}\n"
                    f"Server: {info['server']}\n"
                    f"Mode: Remote REST API + BIM Schema\n"
                    f"BIM: {info['bim_path']}\n"
                    f"Tables: {info['visible_tables']} ({info['tables']} total)\n"
                    f"Measures: {info['measures']} | Columns: {info['columns']}\n"
                    f"Workspace ID: {info['workspace_id']}\n"
                    f"Dataset ID: {info['dataset_id']}"
                )
            if is_remote:
                info = conn.get_info()
                return (
                    f"Model: {db}\n"
                    f"Server: {info['server']}\n"
                    f"Mode: Remote REST API (no BIM)\n"
                    f"Workspace ID: {info['workspace_id']}\n"
                    f"Dataset ID: {info['dataset_id']}\n"
                    f"Note: Set PBI_BIM_PATH for full metadata"
                )
            try:
                tables = get_all_tables(conn)
                measures = get_all_measures(conn)
                columns = get_all_columns(conn)
            finally:
                conn.Close()

            visible_tables = [t for t in tables if t.get("IsHidden") != "True"]
            lines = [
                f"Model: {db}",
                f"Port: {port}",
                f"Tables: {len(visible_tables)} ({len(tables)} total) | Measures: {len(measures)} | Columns: {len(columns)}",
                "=" * 60,
                "Tables:",
            ]
            for t in tables:
                hidden = " [HIDDEN]" if t.get("IsHidden") == "True" else ""
                lines.append(f"  - {t['Name']}{hidden}")
            return "\n".join(lines)

        elif tool_name == "get_tables":
            conn, port, db, title, is_remote = _get_connection(arguments.get("port"))
            if is_remote and hasattr(conn, 'get_tables'):
                tables = conn.get_tables()
            else:
                try:
                    tables = get_all_tables(conn)
                finally:
                    conn.Close()

            lines = [f"Model: {db}", f"Tables: {len(tables)}", "=" * 60]
            for t in tables:
                hidden = " [HIDDEN]" if t.get("IsHidden") == "True" else ""
                desc = f" — {t['Description']}" if t.get("Description") else ""
                lines.append(f"  - {t['Name']}{hidden}{desc}")
            return "\n".join(lines)

        elif tool_name == "get_measures":
            conn, port, db, title, is_remote = _get_connection(arguments.get("port"))
            table_filter = (arguments.get("table_filter") or "").lower()
            name_filter = (arguments.get("name_filter") or "").lower()

            if is_remote and hasattr(conn, 'get_measures'):
                all_measures = conn.get_measures(table_filter=table_filter or None, name_filter=name_filter or None)
            else:
                try:
                    all_measures = get_all_measures(conn)
                    tables = get_all_tables(conn)
                    tid_to_name = {t["ID"]: t["Name"] for t in tables}
                finally:
                    conn.Close()

                filtered = []
                for m in all_measures:
                    table_name = tid_to_name.get(m.get("TableID"), "?")
                    if table_filter and table_filter not in table_name.lower():
                        continue
                    if name_filter and name_filter not in (m.get("Name", "") or "").lower():
                        continue
                    m["_TableName"] = table_name
                    filtered.append(m)
                all_measures = filtered

            if not all_measures:
                return f"No measures found (table_filter={table_filter}, name_filter={name_filter})."

            source = "BIM Schema" if (is_remote and hasattr(conn, 'get_measures')) else "Model"
            lines = [f"Model: {db} ({source})", f"Measures: {len(all_measures)}", "=" * 60]
            for m in all_measures:
                folder = f" [{m.get('DisplayFolder', '')}]" if m.get('DisplayFolder') else ""
                table = m.get('TableName') or m.get('_TableName', '?')
                lines.append(f"\n[{table}]{folder} {m['Name']}")
                if m.get('Expression'):
                    lines.append(f"  DAX: {m['Expression'].strip()[:500]}")
            return "\n".join(lines)

        elif tool_name == "get_columns":
            table = arguments.get("table", "")
            conn, port, db, title, is_remote = _get_connection(arguments.get("port"))

            if is_remote and hasattr(conn, 'get_columns'):
                cols = conn.get_columns(table)
                if not cols:
                    return f"Table '{table}' not found in BIM schema."
                lines = [f"Table: {table} (BIM Schema)", f"Columns: {len(cols)}", "=" * 60]
                for c in cols:
                    dtype = c.get("DataType", "?")
                    hidden = " [HIDDEN]" if c.get("IsHidden") == "True" else ""
                    lines.append(f"  - {c['Name']} ({dtype}){hidden}")
                return "\n".join(lines)

            try:
                all_cols = get_all_columns(conn)
                tables = get_all_tables(conn)
                tid_to_name = {t["ID"]: t["Name"] for t in tables}
            finally:
                conn.Close()

            # Find the table ID
            table_id = None
            for tid, tname in tid_to_name.items():
                if tname == table:
                    table_id = tid
                    break

            if table_id is None:
                return f"Table '{table}' not found."

            cols = [c for c in all_cols if c.get("TableID") == table_id]
            if not cols:
                return f"No columns found for '{table}'."

            lines = [f"Table: {table}", f"Columns: {len(cols)}", "=" * 60]
            for c in cols:
                dtype = c.get("DataType", "?")
                hidden = " [HIDDEN]" if c.get("IsHidden") == "True" else ""
                src = f" <- {c['SourceColumn']}" if c.get("SourceColumn") else ""
                lines.append(f"  - {c['Name']} ({dtype}){hidden}{src}")
            return "\n".join(lines)

        elif tool_name == "search_dax":
            pattern = arguments.get("pattern", "")
            case_sensitive = arguments.get("case_sensitive", False)

            conn, port, db, title, is_remote = _get_connection(arguments.get("port"))

            if is_remote and hasattr(conn, 'search_dax'):
                matches = conn.search_dax(pattern, case_sensitive)
            else:
                try:
                    all_measures = get_all_measures(conn)
                    tables = get_all_tables(conn)
                    tid_to_name = {t["ID"]: t["Name"] for t in tables}
                finally:
                    conn.Close()

                matches = []
                for m in all_measures:
                    expr = m.get("Expression") or ""
                    if case_sensitive:
                        found = pattern in expr
                    else:
                        found = pattern.lower() in expr.lower()
                    if found:
                        m["_TableName"] = tid_to_name.get(m.get("TableID"), "?")
                        matches.append(m)

            if not matches:
                return f"No measures with DAX containing '{pattern}'."

            lines = [f"Model: {db}", f"Measures with '{pattern}': {len(matches)}", "=" * 60]
            for m in matches:
                lines.append(f"\n[{m['_TableName']}] {m['Name']}")
                for eline in (m["Expression"] or "").strip().split("\n"):
                    if pattern.lower() in eline.lower():
                        lines.append(f"  >>> {eline.strip()}")
                    else:
                        lines.append(f"      {eline.strip()}")
            return "\n".join(lines)

        elif tool_name == "run_dax":
            query = arguments.get("query", "")
            conn, port, db, title, is_remote = _get_connection(arguments.get("port"))
            try:
                if is_remote:
                    rows = conn.execute_dax(query)
                else:
                    rows = execute_dax(conn, query)
            finally:
                if not is_remote:
                    conn.Close()
                else:
                    conn.close()

            if not rows:
                return "Query returned no results."

            lines = [f"Model: {db}", f"Rows: {len(rows)}", "=" * 60]
            headers = list(rows[0].keys())
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("|" + "|".join("-" * (len(h) + 2) for h in headers) + "|")
            for row in rows[:50]:
                vals = [str(row.get(h, "") or "") for h in headers]
                lines.append("| " + " | ".join(vals) + " |")
            if len(rows) > 50:
                lines.append(f"\n... ({len(rows) - 50} more rows)")
            return "\n".join(lines)

        elif tool_name == "replace_in_measure":
            table_name = arguments.get("table_name", "")
            measure_name = arguments.get("measure_name", "")
            old_text = arguments.get("old_text", "")
            new_text = arguments.get("new_text", "")

            conn, port, db, title, is_remote = _get_connection(arguments.get("port"), mode="write")
            conn.Close()  # Close ADOMD connection before TOM connection

            result = replace_in_measure(port, table_name, measure_name, old_text, new_text)
            if result:
                return (
                    f"**Success!** Replaced in [{table_name}] {measure_name}:\n"
                    f"  Old: {old_text}\n"
                    f"  New: {new_text}\n\n"
                    f"Remember to verify the change in Power BI Desktop."
                )
            else:
                return f"**Failed** to replace in [{table_name}] {measure_name}. Measure not found or old_text not present in DAX."

        elif tool_name == "get_power_query":
            table = arguments.get("table", "")
            conn, port, db, title, is_remote = _get_connection(arguments.get("port"))
            conn.Close()

            try:
                pq = get_power_query_m_code(port, table_name=table if table else None)
            except Exception as e:
                return f"Error reading Power Query: {e}"

            if not pq:
                return f"No Power Query M code found" + (f" for table '{table}'" if table else "")

            lines = [f"Model: {db}", f"Tables with Power Query: {len(pq)}", "=" * 60]
            for tname, m_code in sorted(pq.items()):
                a = analyze_m_code(m_code)
                lines.append(f"\n[{tname}] ({a['char_count']} chars, {a['step_count']} steps, {a['source_type']})")
                lines.append(m_code[:800])
                if len(m_code) > 800:
                    lines.append(f"... ({len(m_code) - 800} more chars)")
            return "\n".join(lines)

        elif tool_name == "audit_power_query":
            conn, port, db, title, is_remote = _get_connection(arguments.get("port"))
            conn.Close()

            try:
                pq = get_power_query_m_code(port)
            except Exception as e:
                return f"Error reading Power Query: {e}"

            if not pq:
                return "No Power Query M code found in this model."

            # Analyze each table
            lines = [f"Model: {db}", f"Tables with Power Query: {len(pq)}", "=" * 60]

            # Source summary
            from collections import Counter
            sources = Counter()
            for m_code in pq.values():
                if "PostgreSQL.Database" in m_code: sources["PostgreSQL"] += 1
                elif "Sql.Database" in m_code: sources["SQL Server"] += 1
                elif "Excel.Workbook" in m_code: sources["Excel"] += 1
                elif "Web.Contents" in m_code: sources["Web"] += 1
            lines.append(f"\nData Sources: {dict(sources)}")

            # Optimization findings
            issues = []
            for tname, m_code in pq.items():
                a = analyze_m_code(m_code)
                if "PostgreSQL.Database" in m_code and "List.Max" in m_code and "Table.SelectRows" in m_code:
                    issues.append(f"  [{tname}] No query folding — filters on [ds] in Power Query instead of database")
                if a["step_count"] > 10:
                    issues.append(f"  [{tname}] High step count ({a['step_count']} steps) — consider simplifying")
                if a["complexity_score"] > 30:
                    issues.append(f"  [{tname}] High complexity ({a['complexity_score']}) — review for redundant steps")
                if m_code.count("Table.AddColumn") > 5:
                    issues.append(f"  [{tname}] {m_code.count('Table.AddColumn')}x AddColumn — consider moving to DAX calculated columns")

            if issues:
                lines.append(f"\nOptimization Opportunities ({len(issues)}):")
                lines.extend(issues)
            else:
                lines.append("\nNo optimization opportunities found.")

            # Table statistics
            lines.append(f"\nTable Statistics:")
            for tname, m_code in sorted(pq.items(), key=lambda x: -len(x[1])):
                a = analyze_m_code(m_code)
                lines.append(f"  {tname:30s} | {a['char_count']:5d} chars | {a['step_count']:2d} steps | {a['source_type']}")

            return "\n".join(lines)

        elif tool_name == "get_relationships":
            conn, port, db, title, is_remote = _get_connection(arguments.get("port"))
            try:
                rels = execute_dmv(conn, "SELECT * FROM $SYSTEM.TMSCHEMA_RELATIONSHIPS")
                tables = get_all_tables(conn)
                columns = execute_dmv(conn, "SELECT * FROM $SYSTEM.TMSCHEMA_COLUMNS")
            finally:
                conn.Close()

            tid_to_name = {t["ID"]: t["Name"] for t in tables}
            cid_to_name = {}
            for c in columns:
                cname = c.get("ExplicitName", "") or c.get("InferredName", "")
                cid_to_name[c["ID"]] = cname

            lines = [f"Model: {db}", f"Relationships: {len(rels)}", "=" * 60]
            for r in rels:
                from_tbl = tid_to_name.get(r["FromTableID"], "?")
                to_tbl = tid_to_name.get(r["ToTableID"], "?")
                from_col = cid_to_name.get(r["FromColumnID"], r["FromColumnID"])
                to_col = cid_to_name.get(r["ToColumnID"], r["ToColumnID"])
                active = "ACTIVE" if r.get("IsActive") == "True" else "INACTIVE"
                cross = {"1": "Single", "2": "Both"}.get(r.get("CrossFilteringBehavior", ""), r.get("CrossFilteringBehavior", ""))
                lines.append(f"  [{from_tbl}] {from_col} -> [{to_tbl}] {to_col}  [{active}] [{cross}]")
            return "\n".join(lines)

        elif tool_name == "validate_dax":
            expression = arguments.get("expression", "")
            conn, port, db, title, is_remote = _get_connection(arguments.get("port"))
            try:
                cmd = conn.CreateCommand()
                cmd.CommandText = f"DEFINE MEASURE 'KPI'[_ClaudeValidate] = {expression} EVALUATE ROW(\"x\", [_ClaudeValidate])"
                reader = cmd.ExecuteReader()
                reader.Close()
                return f"VALID: {expression}"
            except Exception as e:
                return f"INVALID: {str(e)[:300]}"
            finally:
                conn.Close()

        elif tool_name == "export_model_snapshot":
            import json, datetime
            conn, port, db, title, is_remote = _get_connection(arguments.get("port"))
            try:
                tables = get_all_tables(conn)
                measures = get_all_measures(conn)
                columns = execute_dmv(conn, "SELECT * FROM $SYSTEM.TMSCHEMA_COLUMNS")
                rels = execute_dmv(conn, "SELECT * FROM $SYSTEM.TMSCHEMA_RELATIONSHIPS")
            finally:
                conn.Close()

            tid_to_name = {t["ID"]: t["Name"] for t in tables}
            cid_to_name = {}
            for c in columns:
                cname = c.get("ExplicitName", "") or c.get("InferredName", "")
                cid_to_name[c["ID"]] = cname

            snapshot = {
                "exported_at": datetime.datetime.now().isoformat(),
                "database": db,
                "summary": {
                    "tables": len(tables),
                    "visible_tables": len([t for t in tables if t.get("IsHidden") != "True"]),
                    "measures": len(measures),
                    "columns": len(columns),
                    "relationships": len(rels),
                },
                "tables": [{"name": t["Name"], "hidden": t.get("IsHidden") == "True"} for t in tables],
                "measures": [
                    {"name": m["Name"], "table": tid_to_name.get(m.get("TableID", ""), "?"),
                     "expression": m.get("Expression", ""), "errorMessage": m.get("ErrorMessage", "")}
                    for m in measures
                ],
                "relationships": [
                    {"from": f"{tid_to_name.get(r['FromTableID'], '?')}[{cid_to_name.get(r['FromColumnID'], '?')}]",
                     "to": f"{tid_to_name.get(r['ToTableID'], '?')}[{cid_to_name.get(r['ToColumnID'], '?')}]",
                     "active": r.get("IsActive") == "True"}
                    for r in rels
                ],
            }
            return json.dumps(snapshot, indent=2, ensure_ascii=False)

        elif tool_name == "create_measure":
            table_name = arguments.get("table_name", "")
            measure_name = arguments.get("measure_name", "")
            expression = arguments.get("expression", "")
            display_folder = arguments.get("display_folder", "ClaudeTest")
            format_string = arguments.get("format_string", "")
            description = arguments.get("description", "")

            conn, port, db, title, is_remote = _get_connection(arguments.get("port"), mode="write")
            conn.Close()

            import clr
            clr.AddReference(str(Path(r"D:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.AnalysisServices.Server.Tabular.dll")))
            clr.AddReference(str(Path(r"D:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.Tabular.dll")))
            from Microsoft.AnalysisServices.Tabular import Server, Measure

            server = Server()
            try:
                server.Connect(f"Data Source=localhost:{port};Catalog=")
                model = server.Databases[0].Model

                for t in model.Tables:
                    if t.Name == table_name:
                        existing = [m for m in t.Measures if m.Name == measure_name]
                        if existing:
                            return f"Measure [{table_name}] {measure_name} already exists."

                        m = Measure()
                        m.Name = measure_name
                        m.Expression = expression
                        m.DisplayFolder = display_folder
                        if format_string:
                            m.FormatString = format_string
                        if description:
                            m.Description = description
                        t.Measures.Add(m)
                        model.SaveChanges()
                        return f"Created: [{table_name}] {measure_name}\n  DAX: {expression}\n  Folder: {display_folder}"
                return f"Table '{table_name}' not found."
            finally:
                server.Disconnect()

        elif tool_name == "delete_measure":
            table_name = arguments.get("table_name", "")
            measure_name = arguments.get("measure_name", "")

            conn, port, db, title, is_remote = _get_connection(arguments.get("port"), mode="write")
            conn.Close()

            import clr
            clr.AddReference(str(Path(r"D:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.AnalysisServices.Server.Tabular.dll")))
            clr.AddReference(str(Path(r"D:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.Tabular.dll")))
            from Microsoft.AnalysisServices.Tabular import Server

            server = Server()
            try:
                server.Connect(f"Data Source=localhost:{port};Catalog=")
                model = server.Databases[0].Model

                for t in model.Tables:
                    if t.Name == table_name:
                        target = [m for m in t.Measures if m.Name == measure_name]
                        if not target:
                            return f"Measure [{table_name}] {measure_name} not found."
                        t.Measures.Remove(target[0])
                        model.SaveChanges()
                        return f"Deleted: [{table_name}] {measure_name}"
                return f"Table '{table_name}' not found."
            finally:
                server.Disconnect()

        elif tool_name == "get_roles":
            conn, port, db, title, is_remote = _get_connection(arguments.get("port"))
            conn.Close()

            import clr
            clr.AddReference(str(Path(r"D:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.AnalysisServices.Server.Tabular.dll")))
            clr.AddReference(str(Path(r"D:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.Tabular.dll")))
            from Microsoft.AnalysisServices.Tabular import Server

            server = Server()
            try:
                server.Connect(f"Data Source=localhost:{port};Catalog=")
                model = server.Databases[0].Model

                lines = [f"Model: {db}", f"Roles: {len(model.Roles)}", "=" * 60]
                for role in model.Roles:
                    members = [str(m.Name) for m in role.Members]
                    lines.append(f"\n[{role.Name}]")
                    if members:
                        lines.append(f"  Members: {', '.join(members)}")
                    for tp in role.TablePermissions:
                        filter_expr = ""
                        try:
                            filter_expr = tp.FilterExpression or ""
                        except:
                            pass
                        lines.append(f"  Table: {tp.Table.Name}" + (f" (Filter: {filter_expr})" if filter_expr else ""))
                return "\n".join(lines)
            finally:
                server.Disconnect()

        elif tool_name == "create_relationship":
            from_table = arguments.get("from_table", "")
            from_column = arguments.get("from_column", "")
            to_table = arguments.get("to_table", "")
            to_column = arguments.get("to_column", "")

            conn, port, db, title, is_remote = _get_connection(arguments.get("port"), mode="write")
            conn.Close()

            import clr
            clr.AddReference(str(Path(r"D:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.AnalysisServices.Server.Tabular.dll")))
            clr.AddReference(str(Path(r"D:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.Tabular.dll")))
            from Microsoft.AnalysisServices.Tabular import Server, SingleColumnRelationship

            server = Server()
            try:
                server.Connect(f"Data Source=localhost:{port};Catalog=")
                model = server.Databases[0].Model

                ft = next((t for t in model.Tables if t.Name == from_table), None)
                tt = next((t for t in model.Tables if t.Name == to_table), None)
                if not ft: return f"Table '{from_table}' not found."
                if not tt: return f"Table '{to_table}' not found."

                fc = next((c for c in ft.Columns if c.Name == from_column), None)
                tc = next((c for c in tt.Columns if c.Name == to_column), None)
                if not fc: return f"Column '{from_column}' not found in '{from_table}'."
                if not tc: return f"Column '{to_column}' not found in '{to_table}'."

                rel = SingleColumnRelationship()
                rel.Name = f"Rel_{from_table}_{from_column}_to_{to_table}_{to_column}"
                rel.FromColumn = fc
                rel.ToColumn = tc

                model.Relationships.Add(rel)
                model.SaveChanges()
                return f"Created relationship: [{from_table}] {from_column} -> [{to_table}] {to_column}"
            except Exception as e:
                return f"Failed: {str(e)[:300]}"
            finally:
                server.Disconnect()

        elif tool_name == "create_table":
            table_name = arguments.get("table_name", "")
            expression = arguments.get("expression", "")
            description = arguments.get("description", "")

            conn, port, db, title, is_remote = _get_connection(arguments.get("port"), mode="write")
            conn.Close()

            import clr
            clr.AddReference(str(Path(r"D:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.AnalysisServices.Server.Tabular.dll")))
            clr.AddReference(str(Path(r"D:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.Tabular.dll")))
            from Microsoft.AnalysisServices.Tabular import Server, Table, Partition, MPartitionSource

            server = Server()
            try:
                server.Connect(f"Data Source=localhost:{port};Catalog=")
                model = server.Databases[0].Model

                existing = [t for t in model.Tables if t.Name == table_name]
                if existing:
                    return f"Table '{table_name}' already exists."

                tbl = Table()
                tbl.Name = table_name
                if description: tbl.Description = description
                model.Tables.Add(tbl)

                part = Partition()
                part.Name = f"{table_name}_Partition"
                src = MPartitionSource()
                src.Expression = expression
                part.Source = src
                tbl.Partitions.Add(part)

                model.SaveChanges()
                return f"Created table: {table_name} ({len(tbl.Columns)} columns)"
            except Exception as e:
                return f"Failed: {str(e)[:300]}"
            finally:
                server.Disconnect()

        elif tool_name == "create_column":
            table_name = arguments.get("table_name", "")
            column_name = arguments.get("column_name", "")
            data_type_str = arguments.get("data_type", "String")
            source_column = arguments.get("source_column", column_name)

            conn, port, db, title, is_remote = _get_connection(arguments.get("port"), mode="write")
            conn.Close()

            import clr
            clr.AddReference(str(Path(r"D:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.AnalysisServices.Server.Tabular.dll")))
            clr.AddReference(str(Path(r"D:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.Tabular.dll")))
            from Microsoft.AnalysisServices.Tabular import Server, DataColumn, DataType

            type_map = {"String": DataType.String, "Int64": DataType.Int64,
                        "Double": DataType.Double, "Boolean": DataType.Boolean,
                        "DateTime": DataType.DateTime, "Decimal": DataType.Decimal}
            dt = type_map.get(data_type_str, DataType.String)

            server = Server()
            try:
                server.Connect(f"Data Source=localhost:{port};Catalog=")
                model = server.Databases[0].Model

                tbl = next((t for t in model.Tables if t.Name == table_name), None)
                if not tbl: return f"Table '{table_name}' not found."

                existing = [c for c in tbl.Columns if c.Name == column_name]
                if existing: return f"Column '{column_name}' already exists in '{table_name}'."

                col = DataColumn()
                col.Name = column_name
                col.DataType = dt
                col.SourceColumn = source_column
                tbl.Columns.Add(col)
                model.SaveChanges()
                return f"Created column: [{table_name}] {column_name} ({data_type_str})"
            except Exception as e:
                return f"Failed: {str(e)[:300]}"
            finally:
                server.Disconnect()

        elif tool_name == "get_model_graph":
            conn, port, db, title, is_remote = _get_connection(arguments.get("port"))
            try:
                tables = get_all_tables(conn)
                rels = execute_dmv(conn, "SELECT * FROM $SYSTEM.TMSCHEMA_RELATIONSHIPS")
                columns = execute_dmv(conn, "SELECT * FROM $SYSTEM.TMSCHEMA_COLUMNS")
            finally:
                conn.Close()

            tid_to_name = {t["ID"]: t["Name"] for t in tables}
            cid_to_name = {}
            for c in columns:
                cname = c.get("ExplicitName", "") or c.get("InferredName", "")
                cid_to_name[c["ID"]] = cname

            lines = [f"Model: {db}", f"Tables: {len(tables)} ({len([t for t in tables if t.get('IsHidden')!='True'])} visible)", "=" * 60]

            lines.append("\n-- TABLES --")
            for t in tables:
                h = " [HIDDEN]" if t.get("IsHidden") == "True" else ""
                lines.append(f"\n[{t['Name']}]{h}")
                tbl_cols = [c for c in columns if c.get("TableID") == t["ID"]]
                for c in tbl_cols[:5]:
                    cname = c.get("ExplicitName", "") or c.get("InferredName", "")
                    dtype = c.get("ExplicitDataType", c.get("InferredDataType", "?"))
                    src = f" <- {c['SourceColumn']}" if c.get("SourceColumn") else ""
                    lines.append(f"  - {cname} ({dtype}){src}")
                if len(tbl_cols) > 5:
                    lines.append(f"  ... ({len(tbl_cols)-5} more columns)")

            lines.append(f"\n-- RELATIONSHIPS ({len(rels)}) --")
            for r in rels:
                from_tbl = tid_to_name.get(r["FromTableID"], "?")
                to_tbl = tid_to_name.get(r["ToTableID"], "?")
                from_col = cid_to_name.get(r["FromColumnID"], r["FromColumnID"])
                to_col = cid_to_name.get(r["ToColumnID"], r["ToColumnID"])
                active = "ACTIVE" if r.get("IsActive") == "True" else "INACTIVE"
                cross = {"1": "Single", "2": "Both"}.get(r.get("CrossFilteringBehavior", ""), "?")
                lines.append(f"  [{from_tbl}] {from_col} -> [{to_tbl}] {to_col} [{active}] [CrossFilter={cross}]")

            return "\n".join(lines)

        elif tool_name == "bpa_analyze":
            table_filter = (arguments.get("table_filter") or "").lower()
            conn, port, db, title, is_remote = _get_connection(arguments.get("port"))
            try:
                all_measures = get_all_measures(conn)
                tables = get_all_tables(conn)
                tid_to_name = {t["ID"]: t["Name"] for t in tables}
            finally:
                conn.Close()

            # Filter by table if requested
            measures = []
            for m in all_measures:
                m["_TableName"] = tid_to_name.get(m.get("TableID"), "?")
                if table_filter and table_filter not in m["_TableName"].lower():
                    continue
                measures.append(m)

            if not measures:
                return f"No measures found to analyze (table_filter={table_filter})."

            return analyze_measures(measures)

        elif tool_name == "dependency_analyze":
            measure_name = arguments.get("measure_name", "")
            table = arguments.get("table", "")
            conn, port, db, title, is_remote = _get_connection(arguments.get("port"))
            try:
                all_measures = get_all_measures(conn)
                tables = get_all_tables(conn)
                tid_to_name = {t["ID"]: t["Name"] for t in tables}
            finally:
                conn.Close()

            # Prepare measures for the tracker
            measures = []
            table_names = []
            for m in all_measures:
                m["_TableName"] = tid_to_name.get(m.get("TableID"), "?")
                measures.append(m)
            for t in tables:
                table_names.append(t["Name"])

            tracker = build_and_analyze(measures, table_names)

            if measure_name:
                return tracker.format_dependencies(measure_name, table if table else None)
            else:
                return tracker.format_summary()

        elif tool_name == "batch_operations":
            ops = arguments.get("operations", [])
            conn, port, db, title, is_remote = _get_connection(arguments.get("port"), mode="write")
            conn.Close()

            import clr
            clr.AddReference(str(Path(r"D:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.AnalysisServices.Server.Tabular.dll")))
            clr.AddReference(str(Path(r"D:\Program Files\Microsoft Power BI Desktop\bin\Microsoft.PowerBI.Tabular.dll")))
            from Microsoft.AnalysisServices.Tabular import Server, Measure

            server = Server()
            results = []
            try:
                server.Connect(f"Data Source=localhost:{port};Catalog=")
                model = server.Databases[0].Model

                for i, op in enumerate(ops):
                    action = op.get("action", "")
                    tname = op.get("table_name", "")
                    mname = op.get("measure_name", "")

                    try:
                        if action == "create_measure":
                            tbl = next((t for t in model.Tables if t.Name == tname), None)
                            if not tbl:
                                raise ValueError(f"Table '{tname}' not found")
                            if any(m.Name == mname for m in tbl.Measures):
                                raise ValueError(f"Measure '{mname}' already exists")
                            m = Measure()
                            m.Name = mname
                            m.Expression = op.get("expression", "")
                            m.DisplayFolder = op.get("display_folder", "ClaudeTest")
                            if op.get("format_string"): m.FormatString = op["format_string"]
                            tbl.Measures.Add(m)
                            results.append(f"OK [{i+1}] Created: [{tname}] {mname}")

                        elif action == "delete_measure":
                            tbl = next((t for t in model.Tables if t.Name == tname), None)
                            if not tbl:
                                raise ValueError(f"Table '{tname}' not found")
                            target = [m for m in tbl.Measures if m.Name == mname]
                            if not target:
                                raise ValueError(f"Measure '{mname}' not found")
                            tbl.Measures.Remove(target[0])
                            results.append(f"OK [{i+1}] Deleted: [{tname}] {mname}")

                        elif action == "replace_in_measure":
                            tbl = next((t for t in model.Tables if t.Name == tname), None)
                            if not tbl:
                                raise ValueError(f"Table '{tname}' not found")
                            target = [m for m in tbl.Measures if m.Name == mname]
                            if not target:
                                raise ValueError(f"Measure '{mname}' not found")
                            old_text = op.get("old_text", "")
                            new_text = op.get("new_text", "")
                            if old_text not in target[0].Expression:
                                raise ValueError(f"'{old_text}' not found in {mname}")
                            target[0].Expression = target[0].Expression.replace(old_text, new_text)
                            results.append(f"OK [{i+1}] Replaced in: [{tname}] {mname}")

                        elif action == "create_table":
                            from Microsoft.AnalysisServices.Tabular import Table, Partition, MPartitionSource, ModeType
                            existing = [t for t in model.Tables if t.Name == tname]
                            if existing:
                                raise ValueError(f"Table '{tname}' already exists")
                            tbl = Table()
                            tbl.Name = tname
                            if op.get("description"): tbl.Description = op["description"]
                            model.Tables.Add(tbl)
                            part = Partition()
                            part.Name = f"{tname}_Partition"
                            src = MPartitionSource()
                            src.Expression = op.get("expression", 'ROW("X", 1)')
                            part.Source = src
                            part.Mode = ModeType.Import
                            tbl.Partitions.Add(part)
                            results.append(f"OK [{i+1}] Created table: {tname}")

                        elif action == "create_column":
                            from Microsoft.AnalysisServices.Tabular import DataColumn, DataType
                            tbl = next((t for t in model.Tables if t.Name == tname), None)
                            if not tbl: raise ValueError(f"Table '{tname}' not found")
                            cname = op.get("column_name", "")
                            if any(c.Name == cname for c in tbl.Columns):
                                raise ValueError(f"Column '{cname}' already exists")
                            type_map = {"String": DataType.String, "Int64": DataType.Int64,
                                        "Double": DataType.Double, "Boolean": DataType.Boolean,
                                        "DateTime": DataType.DateTime, "Decimal": DataType.Decimal}
                            col = DataColumn()
                            col.Name = cname
                            col.DataType = type_map.get(op.get("data_type", "String"), DataType.String)
                            col.SourceColumn = op.get("source_column", cname)
                            tbl.Columns.Add(col)
                            results.append(f"OK [{i+1}] Created column: [{tname}] {cname}")

                        elif action == "delete_table":
                            existing = [t for t in model.Tables if t.Name == tname]
                            if not existing:
                                raise ValueError(f"Table '{tname}' not found")
                            model.Tables.Remove(existing[0])
                            results.append(f"OK [{i+1}] Deleted table: {tname}")

                        else:
                            raise ValueError(f"Unknown action: {action}")
                    except Exception as e:
                        results.append(f"FAIL [{i+1}] {action}: {e}")
                        raise  # Re-raise to trigger rollback

                model.SaveChanges()
                results.append(f"\nBatch committed: {len(ops)} operations")
                return "\n".join(results)

            except Exception as e:
                results.append(f"\nBatch ROLLED BACK: {str(e)[:200]}")
                return "\n".join(results)
            finally:
                server.Disconnect()

        else:
            return f"Invalid tool: {tool_name}"

    except Exception as e:
        log.error(f"Tool error: {traceback.format_exc()}")
        return f"Error: {e}"


# ──────────────────────────────────────────────────────────────
#  Main Loop
# ──────────────────────────────────────────────────────────────

def main():
    log.info(f"Power BI Model MCP Server v{SERVER_VERSION} starting...")
    while True:
        request = read_message()
        if request is None:
            break

        req_id = request.get("id")
        method = request.get("method", "")

        try:
            if method == "initialize":
                send_response(req_id, {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                })
            elif method == "notifications/initialized":
                pass
            elif method == "tools/list":
                send_response(req_id, {"tools": TOOLS})
            elif method == "tools/call":
                params = request.get("params", {})
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})
                result_text = handle_tool_call(tool_name, arguments)
                send_response(req_id, {"content": [{"type": "text", "text": result_text}]})
            elif method == "ping":
                send_response(req_id, {})
            else:
                send_error(req_id, -32601, f"Method not found: {method}")
        except Exception as e:
            log.error(f"Error: {traceback.format_exc()}")
            send_error(req_id, -32603, f"Internal error: {e}")


if __name__ == "__main__":
    main()