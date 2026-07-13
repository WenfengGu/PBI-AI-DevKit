# -*- coding: utf-8 -*-
"""
Data Quality Check — Preselling Reporting CN
=============================================
Reusable data quality verification for target SalesAndCrm - target_China.
Auto-discovers column names from BIM file, executes live queries,
and generates a data quality report.

Usage:
    python dq_preselling.py                    # Full check
    python dq_preselling.py --quick             # Row counts + freshness only
    python dq_preselling.py --output report.md  # Save report to file

Prerequisites:
    - BIM file at d:\\LVMH_Max\\target\\SalesAndCrm_target_China_0709.bim
    - PBI_USERNAME / PBI_PASSWORD env vars (or set below)
"""
import os, sys, json, time
from datetime import datetime
from collections import OrderedDict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Credentials ────────────────────────────────────────────────
os.environ["PBI_USERNAME"] = "fendi.powerbi@lvmhfashion.partner.onsmchina.cn"
os.environ["PBI_PASSWORD"] = "***"

from ssas_client import RemotePowerBI
from bim_reader import BimModel

# ── Config ─────────────────────────────────────────────────────
SERVER = "powerbi://api.powerbi.cn/v1.0/myorg/FEN-D-ATOM%20%20CN"
DATABASE = "SalesAndCrm - target_China"
BIM_PATH = os.environ.get(
    "PBI_BIM_PATH",
    r"d:\LVMH_Max\target\SalesAndCrm_target_China_0709.bim",
)

# ── Key tables for Preselling report ──────────────────────────
KEY_TABLES = [
    "Sales Reservation Details",
    "Sales Reservation-Order Details",
    "Customer",
    "Item",
    "Store",
    "RMD",
    "Calendar",
    "Campaign Details",
    "Campaign",
    "Campaign Activity",
    "BookAppointment",
    "Clerk",
    "Database",
]

# ── Column mapping: (table, logical_key, description) ─────────
# Maps logical column roles to actual BIM column names
COLUMN_ALIASES = {
    "Customer": {"pk": "CUST_KEY", "name": "Cust ID DWH"},
    "Item": {"pk": "Barcode EAN13", "name": "Style"},
    "Store": {"pk": "STORE_KEY", "name": "Store"},
    "RMD": {"pk": "RPRO Store Code", "name": "Store Name"},
    "Clerk": {"pk": "CLERK_KEY", "name": "Clerk Full Name"},
    "Calendar": {"pk": "Date", "ym": "YearMonth", "year": "Year"},
    "Campaign": {"pk": "IDCAMPAIGN", "name": "Campaign Name"},
    "Campaign Details": {"pk": "Campaign ID", "name": "Campaign Name", "type": "Campaign Type", "start_date": "Event Start Date"},
    "Sales Reservation Details": {
        "pk": "CUST_KEY", "item": "ITEM_KEY", "store": "RMD_KEY",
        "date": "Sales Order Date", "status": "Sales Order Status",
        "type": "Sales Order Type", "event": "Sales Order Event ID",
    },
    "Sales Reservation-Order Details": {
        "pk": "CUST_KEY", "item": "ITEM_KEY", "store": "RMD_KEY",
        "date": "Sales Order Date", "status": "Sales Order Status",
    },
    "BookAppointment": {"date": "Activity Start Date (Date)"},
}


class DataQualityChecker:
    """Runs data quality checks against a remote Power BI model."""

    def __init__(self, server=SERVER, database=DATABASE, bim_path=BIM_PATH):
        self.client = RemotePowerBI(server=server, database=database)
        self.bim = BimModel(bim_path) if os.path.exists(bim_path) else None
        self.results = OrderedDict()
        self.issues = []
        self.start_time = None

    # ── Helpers ────────────────────────────────────────────────

    def _col(self, table, role):
        """Get actual column name from alias map or BIM."""
        alias = COLUMN_ALIASES.get(table, {}).get(role)
        if alias:
            return alias
        if self.bim:
            t = next((x for x in self.bim.get_tables() if x['name'] == table), None)
            if t:
                for c in t.get('columns', []):
                    if role.lower() in c['name'].lower():
                        return c['name']
        return role  # fallback

    def _dax(self, query):
        """Execute DAX and return first row."""
        try:
            rows = self.client.execute_dax(query)
            return rows[0] if rows else {}
        except Exception as e:
            self.issues.append("DAX error: %s" % str(e)[:120])
            return {}

    def _val(self, row, key, default=None):
        """Get value from row, handling [bracket] keys."""
        return self.client.row_val(row, key, default)

    def _count(self, table):
        """Get row count for a table."""
        row = self._dax("EVALUATE ROW(\"Cnt\", COUNTROWS('%s'))" % table)
        return self._val(row, "Cnt", 0)

    # ── Checks ─────────────────────────────────────────────────

    def check_row_counts(self):
        """DQ1: Row counts for key tables."""
        print("  [Row Counts]")
        self.results["row_counts"] = {}
        for t in KEY_TABLES:
            cnt = self._count(t)
            self.results["row_counts"][t] = cnt
            print("    %-40s %s" % (t, cnt))
        return self

    def check_date_ranges(self):
        """DQ2: Date range coverage."""
        print("  [Date Ranges]")
        self.results["date_ranges"] = {}

        # Calendar
        row = self._dax("EVALUATE ROW(\"Min\", MIN('Calendar'[Date]), "
                        "\"Max\", MAX('Calendar'[Date]), \"Days\", COUNTROWS('Calendar'))")
        self.results["date_ranges"]["Calendar"] = {
            "min": self._val(row, "Min"), "max": self._val(row, "Max"),
            "days": self._val(row, "Days"),
        }
        d = self.results["date_ranges"]["Calendar"]
        print("    Calendar: %s -> %s (%s days)" % (d["min"], d["max"], d["days"]))

        # Sales tables
        for t in ["Sales Reservation Details", "Sales Reservation-Order Details"]:
            dc = self._col(t, "date")
            row = self._dax("EVALUATE ROW(\"Min\", MIN('%s'[%s]), "
                            "\"Max\", MAX('%s'[%s]))" % (t, dc, t, dc))
            self.results["date_ranges"][t] = {
                "min": self._val(row, "Min"), "max": self._val(row, "Max"),
            }
            d = self.results["date_ranges"][t]
            print("    %s: %s -> %s" % (t, d["min"], d["max"]))
        return self

    def check_nulls(self):
        """DQ3: NULL/blank check on key columns."""
        print("  [NULL Checks]")
        self.results["nulls"] = {}

        checks = [
            ("Sales Reservation Details", "pk"),
            ("Sales Reservation Details", "item"),
            ("Sales Reservation Details", "store"),
            ("Sales Reservation Details", "date"),
            ("Sales Reservation-Order Details", "pk"),
            ("Sales Reservation-Order Details", "item"),
            ("Sales Reservation-Order Details", "date"),
            ("Customer", "pk"),
            ("Item", "pk"),
            ("Store", "pk"),
        ]

        for t, role in checks:
            c = self._col(t, role)
            row = self._dax(
                "EVALUATE ROW(\"Total\", COUNTROWS('%s'), "
                "\"Blanks\", COUNTROWS(FILTER('%s', ISBLANK('%s'[%s]))))"
                % (t, t, t, c))
            total = self._val(row, "Total", 0) or 0
            blanks = self._val(row, "Blanks", 0) or 0
            pct = (blanks / total * 100) if total > 0 else 0
            self.results["nulls"]["%s[%s]" % (t, c)] = {
                "total": total, "blanks": blanks, "pct": round(pct, 2),
            }
            flag = " !! HIGH" if pct > 5 else " !" if pct > 0 else ""
            if flag:
                self.issues.append("%s[%s]: %.1f%% blanks%s" % (t, c, pct, flag))
            print("    %s[%s]: %s/%s (%.1f%%)%s" % (t, c, blanks, total, pct, flag))
        return self

    def check_distincts(self):
        """DQ4: Distinct counts on key dimensions."""
        print("  [Distinct Counts]")
        self.results["distincts"] = {}

        checks = [
            ("Customer", "pk"),
            ("Item", "pk"),
            ("Store", "pk"),
            ("RMD", "pk"),
            ("Clerk", "pk"),
            ("Campaign", "pk"),
            ("Campaign Details", "pk"),
            ("Sales Reservation Details", "pk"),
            ("Sales Reservation Details", "event"),
        ]

        for t, role in checks:
            c = self._col(t, role)
            row = self._dax("EVALUATE ROW(\"D\", DISTINCTCOUNT('%s'[%s]))" % (t, c))
            d = self._val(row, "D", 0)
            self.results["distincts"]["%s[%s]" % (t, c)] = d
            print("    %s[%s]: %s" % (t, c, d))
        return self

    def check_freshness(self):
        """DQ5: Data freshness (days since last update)."""
        print("  [Data Freshness]")
        self.results["freshness"] = {}
        today = datetime.now()

        checks = [
            ("SalesResDate", "Sales Reservation Details", "date"),
            ("SalesOrdDate", "Sales Reservation-Order Details", "date"),
            ("CampaignDate", "Campaign Details", "start_date"),
        ]

        for label, t, role in checks:
            c = self._col(t, role)
            row = self._dax("EVALUATE ROW(\"D\", MAX('%s'[%s]))" % (t, c))
            d = self._val(row, "D")
            days_ago = None
            if d:
                try:
                    days_ago = (today - datetime.strptime(str(d)[:10], "%Y-%m-%d")).days
                except:
                    pass
            self.results["freshness"][label] = {"date": str(d), "days_ago": days_ago}
            ago_str = "(%d days ago)" % days_ago if days_ago is not None else ""
            print("    %s: %s %s" % (label, d, ago_str))
            if days_ago is not None and days_ago > 2:
                self.issues.append("%s is %d days stale" % (label, days_ago))
        return self

    def check_monthly_sales(self):
        """DQ6: Monthly Net Sales current year."""
        print("  [Monthly Net Sales]")
        self.results["monthly_sales"] = {}

        ym = self._col("Calendar", "ym")
        rows = self.client.execute_dax(
            "EVALUATE SUMMARIZECOLUMNS("
            "'Calendar'[%s], "
            "FILTER(VALUES('Calendar'[%s]), 'Calendar'[%s] >= 202601 && 'Calendar'[%s] <= 202607), "
            "\"Net Sales\", [Net Sale Euro]) "
            "ORDER BY 'Calendar'[%s]" % (ym, ym, ym, ym, ym))
        if rows:
            for row in rows:
                vals = list(row.values())
                ym_val = vals[0]
                ns = vals[1] if len(vals) > 1 and vals[1] else 0
                self.results["monthly_sales"][str(ym_val)] = ns
                print("    %s: %s" % (ym_val, ns))
        return self

    def check_preselling_metrics(self):
        """DQ7: Preselling-specific metrics."""
        print("  [Preselling Metrics]")

        # Reservation status distribution
        status_c = self._col("Sales Reservation Details", "status")
        rows = self.client.execute_dax(
            "EVALUATE SUMMARIZECOLUMNS("
            "'Sales Reservation Details'[%s], "
            "\"Count\", COUNTROWS('Sales Reservation Details')) "
            "ORDER BY [Count] DESC" % status_c)
        self.results["reservation_status"] = {}
        if rows:
            for row in rows:
                vals = list(row.values())
                self.results["reservation_status"][str(vals[0])] = vals[1]

        # Order status distribution
        ord_status_c = self._col("Sales Reservation-Order Details", "status")
        rows = self.client.execute_dax(
            "EVALUATE SUMMARIZECOLUMNS("
            "'Sales Reservation-Order Details'[%s], "
            "\"Count\", COUNTROWS('Sales Reservation-Order Details')) "
            "ORDER BY [Count] DESC" % ord_status_c)
        self.results["order_status"] = {}
        if rows:
            for row in rows:
                vals = list(row.values())
                self.results["order_status"][str(vals[0])] = vals[1]

        # Cross-table ratio
        row = self._dax(
            "EVALUATE ROW("
            "\"Res\", COUNTROWS('Sales Reservation Details'), "
            "\"Ord\", COUNTROWS('Sales Reservation-Order Details'))")
        res = self._val(row, "Res", 0)
        ord_cnt = self._val(row, "Ord", 0)
        ratio = (ord_cnt / res) if res else 0
        self.results["cross_table"] = {"reservation": res, "order": ord_cnt, "ratio": round(ratio, 3)}
        print("    Reservation: %s | Order: %s | Ratio: %.3f" % (res, ord_cnt, ratio))

        # Top stores
        store_name = self._col("Store", "name")
        rows = self.client.execute_dax(
            "EVALUATE TOPN(5, SUMMARIZECOLUMNS("
            "'Store'[%s], \"Net Sales\", [Net Sale Euro]), [Net Sale Euro], DESC)" % store_name)
        self.results["top_stores"] = []
        if rows:
            for row in rows:
                vals = list(row.values())
                self.results["top_stores"].append((str(vals[0]), vals[1]))
                print("    Top Store: %s = %s" % (vals[0], vals[1]))
        return self

    # ── Report ─────────────────────────────────────────────────

    def run_all(self, quick=False):
        """Run all data quality checks."""
        self.start_time = time.time()
        print("=" * 60)
        print("DATA QUALITY CHECK — Preselling Reporting CN")
        print("Model: %s" % DATABASE)
        print("=" * 60)

        self.check_row_counts()
        self.check_date_ranges()
        self.check_freshness()

        if not quick:
            self.check_nulls()
            self.check_distincts()
            self.check_monthly_sales()
            self.check_preselling_metrics()

        elapsed = time.time() - self.start_time
        print("\n" + "=" * 60)
        print("Checks complete in %.1fs. Issues found: %d" % (elapsed, len(self.issues)))
        for i in self.issues:
            print("  ! %s" % i)
        print("=" * 60)
        return self

    def generate_report(self, output_path=None):
        """Generate a markdown report."""
        lines = []
        lines.append("# Data Quality Report — Preselling Reporting CN")
        lines.append("")
        lines.append("> **Date**: %s" % datetime.now().strftime("%Y-%m-%d %H:%M"))
        lines.append("> **Model**: %s" % DATABASE)
        lines.append("> **Duration**: %.1fs" % (time.time() - self.start_time))
        lines.append("")

        # Row counts
        if "row_counts" in self.results:
            lines.append("## Row Counts")
            lines.append("")
            lines.append("| Table | Rows |")
            lines.append("|-------|------|")
            for t, cnt in self.results["row_counts"].items():
                lines.append("| %s | %s |" % (t, cnt))
            lines.append("")

        # Date ranges
        if "date_ranges" in self.results:
            lines.append("## Date Ranges")
            lines.append("")
            lines.append("| Table | Min | Max | Days |")
            lines.append("|-------|-----|-----|------|")
            for t, d in self.results["date_ranges"].items():
                if isinstance(d, dict):
                    lines.append("| %s | %s | %s | %s |" % (
                        t, d.get("min", "?"), d.get("max", "?"), d.get("days", "?")))
            lines.append("")

        # Freshness
        if "freshness" in self.results:
            lines.append("## Data Freshness")
            lines.append("")
            lines.append("| Metric | Latest Date | Lag |")
            lines.append("|--------|-------------|-----|")
            for label, d in self.results["freshness"].items():
                ago = "%d days" % d["days_ago"] if d["days_ago"] is not None else "?"
                lines.append("| %s | %s | %s |" % (label, d["date"], ago))
            lines.append("")

        # NULLs
        if "nulls" in self.results:
            lines.append("## NULL/Blank Checks")
            lines.append("")
            lines.append("| Column | Blanks | Total | % |")
            lines.append("|--------|--------|-------|---|")
            for col, d in self.results["nulls"].items():
                flag = " 🔴" if d["pct"] > 5 else " ⚠" if d["pct"] > 0 else ""
                lines.append("| %s | %s | %s | %.1f%%%s |" % (
                    col, d["blanks"], d["total"], d["pct"], flag))
            lines.append("")

        # Monthly sales
        if "monthly_sales" in self.results:
            lines.append("## Monthly Net Sales (2026, EUR)")
            lines.append("")
            lines.append("| Month | Net Sales |")
            lines.append("|-------|-----------|")
            for ym, ns in self.results["monthly_sales"].items():
                lines.append("| %s | %s |" % (ym, ns))
            lines.append("")

        # Issues
        if self.issues:
            lines.append("## Issues Found")
            lines.append("")
            for i in self.issues:
                lines.append("- %s" % i)
            lines.append("")

        report = "\n".join(lines)
        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(report)
            print("Report saved to %s" % output_path)
        return report


# ── CLI ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Data Quality Check for Preselling Reporting CN")
    parser.add_argument("--quick", action="store_true", help="Quick mode: row counts + freshness only")
    parser.add_argument("--output", "-o", type=str, help="Save report to file")
    args = parser.parse_args()

    checker = DataQualityChecker()
    checker.run_all(quick=args.quick)

    if args.output:
        checker.generate_report(args.output)
    else:
        print("\n" + checker.generate_report())