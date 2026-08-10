# -*- coding: utf-8 -*-
"""
PBIX Report Layout Parser
==========================
Parses Power BI PBIX files to extract report structure: pages, visuals,
field bindings (columns & measures), slicers, and filters.

Supports:
- PBIX file path (auto-extracts Report/Layout from zip)
- Already-extracted Layout JSON file
- CLI mode: python report_parser.py <path> [--measure <name>] [--column <name>]
- Library mode: from report_parser import ReportParser

Usage:
    python report_parser.py "report.pbix"
    python report_parser.py "report.pbix" --measure "Net Sale Euro"
    python report_parser.py "report.pbix" --column "CUST_KEY"
    python report_parser.py "report.pbix" --unused path/to/model.bim
"""
import json, os, sys, zipfile, io
from pathlib import Path
from collections import defaultdict
from typing import Optional


# ── Visual type labels ─────────────────────────────────────────
VISUAL_LABELS = {
    "slicer": "Slicer", "tableEx": "Table", "pivotTable": "Matrix",
    "barChart": "Bar Chart", "columnChart": "Column Chart",
    "clusteredBarChart": "Clustered Bar", "clusteredColumnChart": "Clustered Column",
    "stackedColumnChart": "Stacked Column", "lineChart": "Line Chart",
    "lineClusteredColumnComboChart": "Combo (Line+Column)",
    "areaChart": "Area Chart", "pieChart": "Pie", "donutChart": "Donut",
    "scatterChart": "Scatter", "waterfallChart": "Waterfall", "funnel": "Funnel",
    "treemap": "Treemap", "card": "Card", "cardVisual": "Multi-row Card",
    "gauge": "Gauge", "kpi": "KPI", "decompositionTree": "Decomposition Tree",
    "shape": "Shape", "image": "Image", "textbox": "Text Box",
    "actionButton": "Button", "chicletSlicer": "Chiclet Slicer",
}

SKIP_TYPES = {"shape", "image", "textbox", "actionButton"}


def _read_layout(path: str) -> dict:
    """Read Report/Layout from a PBIX file or raw Layout JSON file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")

    raw_bytes = p.read_bytes()

    # Check if it's a PBIX (zip) or raw Layout JSON
    if raw_bytes[:2] == b"PK":
        # PBIX file: extract Report/Layout from zip
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as zf:
            layout_path = None
            for name in zf.namelist():
                if name.lower().endswith("report/layout"):
                    layout_path = name
                    break
            if not layout_path:
                raise ValueError("No Report/Layout found in PBIX file")
            raw_bytes = zf.read(layout_path)
    else:
        # Raw Layout JSON file (UTF-16 LE encoded)
        pass

    # Decode UTF-16 LE
    text = raw_bytes.decode("utf-16-le")
    json_start = text.index("{")
    return json.loads(text[json_start:])


class ReportParser:
    """Parses a Power BI report layout and provides query methods."""

    def __init__(self, path: str, bim_path: str = None):
        self.path = path
        self.layout = _read_layout(path)
        self.pages = self.layout.get("sections", [])

        # Build lookup indexes
        self._measure_index = defaultdict(list)   # measure_name -> [(page, visual, role)]
        self._column_index = defaultdict(list)    # column_name -> [(page, visual, role)]
        self._slicer_index = []                   # [(page, field, sync_group)]
        self._visual_index = []                   # [(page, visual_type, fields, measures)]

        self._build_indexes()

        # Extract report-level measures from modelExtensions (Live Connection PBIX)
        self._report_measures = {}  # measure_name -> {expression, table, formatString, ...}
        self._extract_report_measures()

        # Load BIM for cross-reference (optional)
        self.bim_measures = set()
        if bim_path and os.path.exists(bim_path):
            try:
                sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                from bim_reader import BimModel
                bim = BimModel(bim_path)
                for m in bim.get_measures():
                    self.bim_measures.add(f"{m['table']}.{m['name']}")
            except Exception:
                pass

    def _build_indexes(self):
        """Build internal lookup indexes from layout."""
        for page in self.pages:
            page_name = page.get("displayName", "Unnamed")
            for vc in page.get("visualContainers", []):
                config = json.loads(vc.get("config", "{}"))
                vp = config.get("singleVisual") or config.get("multiVisual")
                if not vp:
                    continue

                vt = vp.get("visualType", "?")
                if vt in SKIP_TYPES:
                    continue

                projections = vp.get("projections", {})
                vis_fields = []
                vis_measures = []

                for role, items in projections.items():
                    for item in items:
                        qr = item.get("queryRef", "")
                        if not qr:
                            continue
                        vis_fields.append((role, qr))

                        # Classify: measure references have "Measure" in prototypeQuery.Select
                        is_measure = self._is_measure_reference(vp, qr)
                        if is_measure:
                            vis_measures.append(qr)
                            self._measure_index[qr].append({
                                "page": page_name, "visual": VISUAL_LABELS.get(vt, vt),
                                "role": role,
                            })
                        else:
                            self._column_index[qr].append({
                                "page": page_name, "visual": VISUAL_LABELS.get(vt, vt),
                                "role": role,
                            })

                # Slicers
                if vt in ("slicer", "chicletSlicer"):
                    sync = vp.get("syncGroup", {})
                    for role, items in projections.items():
                        for item in items:
                            qr = item.get("queryRef", "")
                            if qr:
                                self._slicer_index.append({
                                    "page": page_name,
                                    "field": qr,
                                    "sync_group": sync.get("groupName", ""),
                                    "active": item.get("active", False),
                                })

                self._visual_index.append({
                    "page": page_name,
                    "type": VISUAL_LABELS.get(vt, vt),
                    "fields": vis_fields,
                    "measures": vis_measures,
                })

    def _is_measure_reference(self, vp: dict, query_ref: str) -> bool:
        """Check if a queryRef refers to a measure (not a column)."""
        proto = vp.get("prototypeQuery", {})
        for sel in proto.get("Select", []):
            if sel.get("Name") == query_ref:
                return "Measure" in sel
        # Heuristic: if it looks like Table.[Measure] or has special chars
        if ".[" in query_ref:
            return True
        return False

    def _extract_report_measures(self):
        """Extract report-level measures from modelExtensions (Live Connection PBIX).

        Live Connection PBIX files can define measures locally in the Layout JSON's
        config.modelExtensions. These are NOT in the BIM file — they only exist in the PBIX.
        """
        try:
            config_str = self.layout.get("config", "{}")
            config = json.loads(config_str)
            extensions = config.get("modelExtensions", [])
            for ext in extensions:
                for entity in ext.get("entities", []):
                    entity_name = entity.get("name", "")
                    for m in entity.get("measures", []):
                        name = m.get("name", "")
                        expr = m.get("expression", "")
                        if isinstance(expr, list):
                            expr = "\n".join(expr)
                        folder = m.get("displayFolder", "")
                        # Store with full key: "Entity.MeasureName"
                        key = f"{entity_name}.{name}" if entity_name else name
                        self._report_measures[key] = {
                            "name": name,
                            "table": entity_name,
                            "expression": str(expr),
                            "displayFolder": folder,
                            "formatString": m.get("formatString", ""),
                            "dataType": m.get("dataType", ""),
                        }
        except Exception:
            pass  # Not all PBIX files have modelExtensions

    # ── Public API ──────────────────────────────────────────────

    def get_report_measures_dax(self) -> dict:
        """Return all report-level measures with their DAX expressions.

        These are measures defined locally in the PBIX (modelExtensions),
        not in the remote BIM model. Only present in Live Connection PBIX files
        that have report-level measures.

        Returns: {measure_name: {name, table, expression, displayFolder, formatString, dataType}}
        """
        return self._report_measures

    def get_pages(self) -> list[dict]:
        """Return list of all pages."""
        return [{"ordinal": i, "name": p.get("displayName", "?"),
                 "visuals": len(p.get("visualContainers", []))}
                for i, p in enumerate(self.pages)]

    def get_visuals(self, page_name: str = None) -> list[dict]:
        """Return all visuals, optionally filtered by page."""
        results = []
        for v in self._visual_index:
            if page_name and page_name.lower() not in v["page"].lower():
                continue
            results.append(v)
        return results

    def get_measures(self) -> set:
        """Return all measure names used in the report (visuals + report-level measures)."""
        measures = set(self._measure_index.keys())
        # Also include report-level measures from modelExtensions
        measures.update(self._report_measures.keys())
        return measures

    def get_columns(self) -> set:
        """Return all column names used in the report."""
        return set(self._column_index.keys())

    def get_measure_usage(self, measure_name: str) -> list[dict]:
        """Find all pages/visuals that use a specific measure."""
        results = []
        for key, usages in self._measure_index.items():
            if measure_name.lower() in key.lower():
                for u in usages:
                    results.append({**u, "measure": key})
        return results

    def get_column_usage(self, column_name: str) -> list[dict]:
        """Find all pages/visuals that use a specific column."""
        results = []
        for key, usages in self._column_index.items():
            if column_name.lower() in key.lower():
                for u in usages:
                    results.append({**u, "column": key})
        return results

    def get_slicers(self) -> list[dict]:
        """Return all slicer visuals with their fields and sync groups."""
        return self._slicer_index

    def get_unused_measures(self) -> list[str]:
        """Return measures in BIM that are NOT used in the report."""
        if not self.bim_measures:
            return []
        report_measures = {m.split(".")[-1] for m in self.get_measures()}
        unused = []
        for m in self.bim_measures:
            parts = m.split(".", 1)
            if len(parts) == 2:
                table, name = parts
                if name not in report_measures and table not in ("KPI_Curr", "Measure"):
                    unused.append(m)
        return sorted(unused)

    # ── Formatting ──────────────────────────────────────────────

    def format_structure(self) -> str:
        """Format complete report structure as Markdown."""
        lines = ["# Report Structure", ""]
        for page in self.pages:
            pname = page.get("displayName", "Unnamed")
            lines.append(f"## {pname}")
            lines.append("")

            for vc in page.get("visualContainers", []):
                config = json.loads(vc.get("config", "{}"))
                vp = config.get("singleVisual") or config.get("multiVisual")
                if not vp:
                    continue
                vt = vp.get("visualType", "?")
                if vt in SKIP_TYPES:
                    continue

                label = VISUAL_LABELS.get(vt, vt)
                lines.append(f"### {label}")
                lines.append("")

                projections = vp.get("projections", {})
                if projections:
                    for role, items in projections.items():
                        if items:
                            lines.append(f"- **{role}**:")
                            for item in items:
                                qr = item.get("queryRef", "?")
                                active = " *(active)*" if item.get("active") else ""
                                lines.append(f"  - `{qr}`{active}")
                lines.append("")
        return "\n".join(lines)

    def format_measures(self, cross_check: bool = False) -> str:
        """Format measure usage report."""
        lines = ["# Report Measures", ""]
        measures = sorted(self.get_measures())
        lines.append(f"**Total: {len(measures)} measures**")
        lines.append("")

        for m in measures:
            usages = self._measure_index.get(m, [])
            pages = sorted(set(u["page"] for u in usages))
            lines.append(f"### `{m}`")
            lines.append(f"Used in {len(usages)} visual(s) across {len(pages)} page(s):")
            for u in usages:
                lines.append(f"- {u['page']} -> [{u['visual']}] ({u['role']})")
            lines.append("")

        if cross_check and self.bim_measures:
            unused = self.get_unused_measures()
            lines.append(f"## Cross-Check with BIM")
            lines.append(f"BIM measures: {len(self.bim_measures)} | Report measures: {len(measures)} | Unused: {len(unused)}")
            lines.append("")
            if unused:
                lines.append("### Potentially Unused (in BIM but not in report)")
                for m in unused[:50]:
                    lines.append(f"- `{m}`")
                if len(unused) > 50:
                    lines.append(f"- ... and {len(unused)-50} more")

        return "\n".join(lines)

    def format_usage(self, field_name: str) -> str:
        """Format usage report for a specific field."""
        lines = [f"# Usage: `{field_name}`", ""]

        # Check measures
        m_usages = self.get_measure_usage(field_name)
        if m_usages:
            lines.append("## As Measure")
            for u in m_usages:
                lines.append(f"- **{u['page']}** -> [{u['visual']}] ({u['role']}): `{u['measure']}`")

        # Check columns
        c_usages = self.get_column_usage(field_name)
        if c_usages:
            lines.append("## As Column")
            for u in c_usages:
                lines.append(f"- **{u['page']}** -> [{u['visual']}] ({u['role']}): `{u['column']}`")

        if not m_usages and not c_usages:
            lines.append("Not found in any page or visual.")

        return "\n".join(lines)

    def format_slicers(self) -> str:
        """Format slicer report."""
        lines = ["# Slicers", ""]
        slicers = self.get_slicers()

        # Group by sync group
        by_group = defaultdict(list)
        for s in slicers:
            by_group[s["sync_group"] or "(no sync)"].append(s)

        for group, items in sorted(by_group.items()):
            lines.append(f"## Sync Group: {group}")
            lines.append("")
            for item in items:
                active = " [active]" if item["active"] else ""
                lines.append(f"- **{item['page']}**: `{item['field']}`{active}")
            lines.append("")

        return "\n".join(lines)


# ── CLI ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="PBIX Report Layout Parser")
    parser.add_argument("path", help="PBIX file path or Layout JSON file path")
    parser.add_argument("--measure", "-m", type=str, help="Find usage of a specific measure")
    parser.add_argument("--column", "-c", type=str, help="Find usage of a specific column")
    parser.add_argument("--slicers", action="store_true", help="Show slicer report")
    parser.add_argument("--measures", action="store_true", help="Show measure report")
    parser.add_argument("--report-measures", action="store_true", help="Show DAX for report-level measures (modelExtensions)")
    parser.add_argument("--unused", type=str, metavar="BIM_PATH", help="Cross-check with BIM for unused measures")
    parser.add_argument("--structure", action="store_true", help="Show full report structure")
    args = parser.parse_args()

    rp = ReportParser(args.path, bim_path=args.unused)

    if args.measure:
        print(rp.format_usage(args.measure))
    elif args.column:
        print(rp.format_usage(args.column))
    elif args.slicers:
        print(rp.format_slicers())
    elif args.measures:
        print(rp.format_measures(cross_check=bool(args.unused)))
    elif args.report_measures:
        dax_measures = rp.get_report_measures_dax()
        if dax_measures:
            print(f"# Report-Level Measures (from PBIX modelExtensions)\n")
            print(f"Total: {len(dax_measures)}\n")
            for key, m in sorted(dax_measures.items()):
                print(f"## {key}")
                print(f"```dax")
                print(m['expression'])
                print(f"```")
                if m.get('displayFolder'):
                    print(f"Folder: {m['displayFolder']}")
                print()
        else:
            print("No report-level measures found (not a Live Connection PBIX or no local measures).")
    elif args.structure:
        print(rp.format_structure())
    else:
        # Default: show summary
        pages = rp.get_pages()
        print(f"Report: {args.path}")
        print(f"Pages: {len(pages)}")
        for p in pages:
            print(f"  [{p['ordinal']}] {p['name']} ({p['visuals']} visuals)")
        print(f"\nMeasures: {len(rp.get_measures())}")
        print(f"Columns: {len(rp.get_columns())}")
        print(f"Slicers: {len(rp.get_slicers())}")
        print(f"\nUse --structure, --measures, --slicers, --measure <name>, or --column <name> for details.")