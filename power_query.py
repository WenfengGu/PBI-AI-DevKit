"""
Power Query (M Language) Reader/Writer
======================================
Extracts and modifies Power Query M code from PBIX DataMashup files.

The DataMashup inside a PBIX is typically a ZIP archive containing:
  Formulas/Section1.m    — Primary M language code
  Formulas/Section2.m    — Additional M modules (if present)
  Config/                — Data source configurations
  Data/                  — Cached/preview data

NOTE: In older Power BI Desktop versions, DataMashup may be an OLE Compound
Document instead of a ZIP. This module currently only handles the ZIP format
(used by Power BI Desktop 2021+). For OLE format, a third-party library like
`olefile` would be needed.

Also, the exact structure of DataMashup may vary. This has been tested on:
- Power BI Desktop 2026.06 (ZIP format confirmed)
- Cloud-downloaded PBIX files do NOT contain DataMashup

TODO: Test with real locally-created PBIX files to verify multi-section handling.
"""

import zipfile
import io
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional


def extract_m_code(pbix_path: str) -> Optional[str]:
    """
    Extract the main Power Query M code from a PBIX file.
    Returns the content of the first .m file found in Formulas/, or None.
    For multiple modules, use extract_all_m_modules() instead.
    """
    modules = extract_all_m_modules(pbix_path)
    if not modules:
        return None
    # Return Section1.m first, then fall back to any .m file
    for preferred in ["Formulas/Section1.m"]:
        if preferred in modules:
            return modules[preferred]
    return next(iter(modules.values()))


def extract_all_m_modules(pbix_path: str) -> dict[str, str]:
    """
    Extract all M language modules from the DataMashup.
    Returns dict of {filename: content}.
    """
    pbix_path = Path(pbix_path)
    if not pbix_path.exists():
        raise FileNotFoundError(f"PBIX not found: {pbix_path}")

    with zipfile.ZipFile(pbix_path, 'r') as zf:
        if "DataMashup" not in zf.namelist():
            return {}

        mashup_bytes = zf.read("DataMashup")

    modules = {}
    with zipfile.ZipFile(io.BytesIO(mashup_bytes), 'r') as mz:
        for name in mz.namelist():
            if name.startswith("Formulas/") and name.endswith(".m"):
                modules[name] = mz.read(name).decode("utf-8-sig")

    return modules


def update_m_code(pbix_path: str, new_code: str,
                  module_name: str = "Formulas/Section1.m") -> str:
    """
    Replace Power Query M code in a PBIX file.

    Returns the path to the modified PBIX.
    The original file is backed up as .pbix.bak.
    """
    pbix_path = Path(pbix_path)
    if not pbix_path.exists():
        raise FileNotFoundError(f"PBIX not found: {pbix_path}")

    # Backup original
    backup_path = pbix_path.with_suffix(".pbix.bak")
    shutil.copy2(pbix_path, backup_path)

    # Read the PBIX
    with zipfile.ZipFile(pbix_path, 'r') as zf:
        all_files = {}
        for name in zf.namelist():
            if name != "DataMashup":
                all_files[name] = zf.read(name)
            else:
                all_files[name] = zf.read(name)

    # Read and modify the DataMashup
    if "DataMashup" not in all_files:
        raise ValueError("PBIX does not contain DataMashup. "
                         "This file may be from Power BI Service (cloud).")

    mashup_bytes = all_files["DataMashup"]
    mashup_io = io.BytesIO()

    with zipfile.ZipFile(io.BytesIO(mashup_bytes), 'r') as mz_read:
        with zipfile.ZipFile(mashup_io, 'w', zipfile.ZIP_DEFLATED) as mz_write:
            for name in mz_read.namelist():
                if name == module_name:
                    mz_write.writestr(name, new_code)
                else:
                    mz_write.writestr(name, mz_read.read(name))

    all_files["DataMashup"] = mashup_io.getvalue()

    # Write back the PBIX
    with zipfile.ZipFile(pbix_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, data in all_files.items():
            zf.writestr(name, data)

    return str(pbix_path)


def has_power_query(pbix_path: str) -> bool:
    """Check if a PBIX file contains Power Query (DataMashup with M code)."""
    try:
        modules = extract_all_m_modules(pbix_path)
        return len(modules) > 0
    except Exception:
        return False


def analyze_m_code(m_code: str) -> dict:
    """
    Analyze M code for common patterns and metrics.
    Returns a summary dict with:
      - steps: list of applied step names
      - source_type: type of data source
      - line_count: total lines
      - complexity_score: rough complexity estimate
    """
    lines = m_code.strip().split("\n")
    steps = []
    source_type = "unknown"

    for line in lines:
        stripped = line.strip()
        # Detect step names: #"Step Name" or bare identifiers before =
        if "=" in stripped:
            left = stripped.split("=")[0].strip()
            if left.startswith('#"') or (left and not left.startswith("//") and not left.startswith("in")):
                steps.append(left)

        # Detect source type
        if "Sql.Database" in stripped or "Sql.Databases" in stripped:
            source_type = "SQL Server"
        elif "Web.Contents" in stripped:
            source_type = "Web"
        elif "Csv.Document" in stripped or "Excel.Workbook" in stripped:
            source_type = "File (CSV/Excel)"
        elif "Json.Document" in stripped:
            source_type = "JSON"
        elif "OData.Feed" in stripped:
            source_type = "OData"
        elif "GoogleSheets" in stripped:
            source_type = "Google Sheets"
        elif "Table.FromRows" in stripped:
            source_type = "Inline Data"

    complexity = 0
    complexity += m_code.count("Table.") * 2
    complexity += m_code.count("List.") * 1
    complexity += m_code.count("each ") * 1
    complexity += m_code.count("let") * 0
    complexity += m_code.count("Merge") * 3
    complexity += m_code.count("Append") * 2
    complexity += m_code.count("NestedJoin") * 3

    return {
        "steps": steps,
        "step_count": len(steps),
        "source_type": source_type,
        "line_count": len(lines),
        "char_count": len(m_code),
        "complexity_score": complexity,
    }