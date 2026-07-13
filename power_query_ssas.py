"""
Power Query M Code Reader (via SSAS Partitions)
================================================
Reads Power Query M code from running Power BI Desktop instances
via the $SYSTEM.TMSCHEMA_PARTITIONS DMV query.

Each table's Power Query is stored in the QueryDefinition column
of its partition entry.
"""

import os, sys, clr, subprocess, re
from pathlib import Path
from typing import Optional

# Auto-detect Power BI Desktop bin directory
def _find_pbi_bin() -> Path:
    for base in [r"D:\Program Files", r"C:\Program Files", r"C:\Program Files (x86)"]:
        p = Path(base) / "Microsoft Power BI Desktop" / "bin"
        if (p / "Microsoft.PowerBI.AdomdClient.dll").exists():
            return p
    raise RuntimeError("Power BI Desktop not found. Please install it first.")

PBI_BIN = _find_pbi_bin()
ADOMD_DLL = PBI_BIN / "Microsoft.PowerBI.AdomdClient.dll"
os.environ["PATH"] = str(PBI_BIN) + os.pathsep + os.environ.get("PATH", "")

import clr
clr.AddReference(str(ADOMD_DLL))
from Microsoft.AnalysisServices.AdomdClient import AdomdConnection


def discover_port() -> Optional[int]:
    """Find a running Power BI Desktop SSAS port."""
    r = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, timeout=10)
    pr = subprocess.run(["tasklist", "/FI", "IMAGENAME eq msmdsrv.exe", "/FO", "CSV"],
                         capture_output=True, text=True, timeout=10)
    pids = set()
    for line in pr.stdout.splitlines():
        if "msmdsrv" in line.lower():
            parts = line.replace('"', '').split(",")
            if len(parts) >= 2:
                try: pids.add(int(parts[1].strip()))
                except: pass

    for line in r.stdout.splitlines():
        if "LISTENING" not in line: continue
        m = re.search(r'127\.0\.0\.1:(\d+)\s+.*\s+(\d+)$', line)
        if m and int(m.group(2)) in pids:
            return int(m.group(1))
    return None


def get_power_query_m_code(port: int = None, table_name: str = None) -> dict:
    """
    Extract Power Query M code from a running Power BI Desktop instance.

    Args:
        port: SSAS port (auto-discover if None)
        table_name: Optional table name filter

    Returns:
        dict mapping table_name -> M code string
    """
    if port is None:
        port = discover_port()
        if port is None:
            raise RuntimeError("No Power BI Desktop instance found.")

    conn = AdomdConnection(f"Data Source=localhost:{port};Catalog=")
    conn.Open()

    # Get table ID -> name mapping
    cmd = conn.CreateCommand()
    cmd.CommandText = "SELECT * FROM $SYSTEM.TMSCHEMA_TABLES"
    reader = cmd.ExecuteReader()
    tables = {}
    while reader.Read():
        tables[str(reader["ID"])] = str(reader["Name"])
    reader.Close()

    # Get partitions with QueryDefinition
    cmd2 = conn.CreateCommand()
    cmd2.CommandText = "SELECT * FROM $SYSTEM.TMSCHEMA_PARTITIONS"
    reader2 = cmd2.ExecuteReader()
    result = {}
    while reader2.Read():
        qd = str(reader2["QueryDefinition"]) if reader2["QueryDefinition"] else ""
        tid = str(reader2["TableID"])
        tname = tables.get(tid, f"TableID={tid}")

        if not qd:
            continue

        if table_name and tname != table_name:
            continue

        result[tname] = qd

    reader2.Close()
    conn.Close()
    return result


def analyze_power_query(m_code: str) -> dict:
    """
    Analyze Power Query M code for common patterns and metrics.
    """
    lines = m_code.strip().split("\n")
    steps = []
    source_type = "unknown"

    for line in lines:
        stripped = line.strip()
        # Detect step names
        if "=" in stripped and not stripped.startswith("//"):
            left = stripped.split("=")[0].strip()
            if left and not left.startswith("let") and not left.startswith("in"):
                steps.append(left)

        # Detect source type
        if "PostgreSQL.Database" in stripped:
            source_type = "PostgreSQL"
        elif "Sql.Database" in stripped or "Sql.Databases" in stripped:
            source_type = "SQL Server"
        elif "Web.Contents" in stripped:
            source_type = "Web"
        elif "Csv.Document" in stripped or "Excel.Workbook" in stripped:
            source_type = "File (CSV/Excel)"
        elif "Json.Document" in stripped:
            source_type = "JSON"

    complexity = 0
    complexity += m_code.count("Table.") * 2
    complexity += m_code.count("List.") * 1
    complexity += m_code.count("each ") * 1
    complexity += m_code.count("Merge") * 3
    complexity += m_code.count("Append") * 2

    return {
        "steps": steps,
        "step_count": len(steps),
        "source_type": source_type,
        "line_count": len(lines),
        "char_count": len(m_code),
        "complexity_score": complexity,
    }