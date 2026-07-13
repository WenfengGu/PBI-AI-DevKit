"""
DAX Best Practice Analyzer (BPA)
================================
Static analysis of DAX expressions for common issues:
performance, maintainability, correctness, and naming conventions.

Usage:
    from bpa import DaxAnalyzer
    analyzer = DaxAnalyzer()
    issues = analyzer.analyze_measure("Total Sales", "KPI", "SUMX(...)")
    # Returns list of issue dicts with severity, category, and suggestion
"""

import re
from collections import Counter
from typing import Optional


# ──────────────────────────────────────────────────────────────
#  Rule Definitions
# ──────────────────────────────────────────────────────────────

class Severity:
    ERROR = "error"       # Likely broken / wrong result
    WARNING = "warning"   # Bad practice, performance issue
    INFO = "info"         # Style / convention suggestion


class Category:
    PERFORMANCE = "performance"
    MAINTAINABILITY = "maintainability"
    CORRECTNESS = "correctness"
    NAMING = "naming"


# ──────────────────────────────────────────────────────────────
#  Individual Rule Checkers
# ──────────────────────────────────────────────────────────────

def _check_divide_no_alternative(expr: str) -> Optional[dict]:
    """DIVIDE without third argument (safe divisor)."""
    # Match DIVIDE(..., ...) without third argument
    # Need to handle nested parens carefully
    pattern = r'DIVIDE\s*\([^,]+,[^,)]+\)'
    if re.search(pattern, expr, re.IGNORECASE):
        return {
            "rule": "DIVIDE_NO_ALTERNATIVE",
            "severity": Severity.WARNING,
            "category": Category.CORRECTNESS,
            "message": "DIVIDE() missing third argument -- consider providing an alternative result for division by zero",
            "suggestion": "Use DIVIDE(numerator, denominator, 0) or DIVIDE(numerator, denominator, BLANK())",
        }
    return None


def _check_earlier_instead_of_var(expr: str) -> Optional[dict]:
    """EARLIER() used instead of VAR/RETURN pattern."""
    if re.search(r'\bEARLIER\s*\(', expr, re.IGNORECASE):
        return {
            "rule": "EARLIER_INSTEAD_OF_VAR",
            "severity": Severity.WARNING,
            "category": Category.PERFORMANCE,
            "message": "EARLIER() detected -- consider using VAR/RETURN pattern for better readability and performance",
            "suggestion": "Replace EARLIER() with VAR variables defined before RETURN",
        }
    return None


def _check_nested_if_depth(expr: str, max_depth: int = 3) -> Optional[dict]:
    """IF statements nested too deeply."""
    # Count max nesting depth of IF(
    depth = 0
    max_seen = 0
    in_string = False
    for i, ch in enumerate(expr):
        if ch == '"' and (i == 0 or expr[i-1] != '\\'):
            in_string = not in_string
        if in_string:
            continue
        upper = expr[i:i+3].upper()
        if upper == 'IF(':
            depth += 1
            max_seen = max(max_seen, depth)
        elif ch == ')' and depth > 0:
            depth -= 1
    if max_seen > max_depth:
        return {
            "rule": "NESTED_IF_DEPTH",
            "severity": Severity.WARNING,
            "category": Category.MAINTAINABILITY,
            "message": f"IF() nested {max_seen} levels deep (threshold: {max_depth}) -- consider using SWITCH() for readability",
            "suggestion": f"Replace nested IF with SWITCH(TRUE(), ...) or refactor into separate measures",
        }
    return None


def _check_switch_no_else(expr: str) -> Optional[dict]:
    """SWITCH without final else/default case."""
    # SWITCH(..., ..., ..., ...) -- last arg should be the else
    # Hard to detect perfectly with regex; look for SWITCH without BLANK() at end
    if re.search(r'\bSWITCH\s*\(', expr, re.IGNORECASE):
        # Count commas in SWITCH call -- if even number of value-result pairs, may have else
        # Simple heuristic: check if SWITCH ends with a value that looks like functions
        switch_match = re.search(r'SWITCH\s*\((.+)\)\s*$', expr, re.IGNORECASE | re.DOTALL)
        if switch_match:
            body = switch_match.group(1)
            # Count top-level commas
            depth = 0
            commas_at_level_1 = []
            pos = 0
            for i, ch in enumerate(body):
                if ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                elif ch == ',' and depth == 0:
                    commas_at_level_1.append(i)
            # First arg is expression, then pairs of (value, result), then optional else
            # If len(commas) is even, we have pairs only (no else); if odd, we have an else
            if len(commas_at_level_1) >= 2 and len(commas_at_level_1) % 2 == 0:
                return {
                    "rule": "SWITCH_NO_ELSE",
                    "severity": Severity.WARNING,
                    "category": Category.CORRECTNESS,
                    "message": "SWITCH() may be missing an else/default case -- unmatched values will return BLANK()",
                    "suggestion": "Add a final else argument to SWITCH(), e.g. SWITCH(expr, val1, result1, val2, result2, BLANK())",
                }
    return None


def _check_calculate_no_filter(expr: str) -> Optional[dict]:
    """CALCULATE with no filter arguments (redundant)."""
    # CALCULATE( expr ) -- no comma = no filter
    matches = re.findall(r'CALCULATE\s*\(\s*([^,)]+)\s*\)', expr, re.IGNORECASE)
    if matches:
        return {
            "rule": "CALCULATE_NO_FILTER",
            "severity": Severity.INFO,
            "category": Category.PERFORMANCE,
            "message": f"CALCULATE() used without filter arguments -- redundant, remove CALCULATE wrapper",
            "suggestion": "Replace CALCULATE(expr) with just expr",
        }
    return None


def _check_filter_values(expr: str) -> Optional[dict]:
    """FILTER(ALL(table), ...) or FILTER(VALUES(table), ...) pattern."""
    if re.search(r'FILTER\s*\(\s*(ALL|VALUES)\s*\(', expr, re.IGNORECASE):
        return {
            "rule": "FILTER_VALUES_PATTERN",
            "severity": Severity.WARNING,
            "category": Category.PERFORMANCE,
            "message": "FILTER(ALL/VALUES(table), ...) detected -- consider using CALCULATE with direct filter arguments",
            "suggestion": "Replace FILTER(ALL(table), condition) with CALCULATE(expr, condition) or use TREATAS",
        }
    return None


def _check_multiple_filter(expr: str) -> Optional[dict]:
    """Multiple FILTER() calls in one expression."""
    count = len(re.findall(r'\bFILTER\s*\(', expr, re.IGNORECASE))
    if count > 2:
        return {
            "rule": "MULTIPLE_FILTER",
            "severity": Severity.WARNING,
            "category": Category.PERFORMANCE,
            "message": f"{count} FILTER() calls in one expression -- consider consolidating into a single filter context",
            "suggestion": "Combine multiple FILTER conditions with && in a single FILTER, or use CALCULATE filter arguments",
        }
    return None


def _check_sumx_no_filter(expr: str) -> Optional[dict]:
    """SUMX/MAXX/etc over large table without filtering."""
    if re.search(r'\b(SUMX|MAXX|MINX|AVERAGEX|COUNTX|RANKX)\s*\(\s*\'(?!_)[^\']+\'\s*,', expr, re.IGNORECASE):
        return {
            "rule": "ITERATOR_NO_FILTER",
            "severity": Severity.INFO,
            "category": Category.PERFORMANCE,
            "message": "Iterator function over a table without explicit filtering -- may cause performance issues on large tables",
            "suggestion": "Add filter arguments to the iterator, or wrap the table in FILTER/CALCULATETABLE",
        }
    return None


def _check_no_format_string(measure: dict) -> Optional[dict]:
    """Measure has no format string."""
    if not measure.get("formatString") and not measure.get("FormatString"):
        return {
            "rule": "NO_FORMAT_STRING",
            "severity": Severity.INFO,
            "category": Category.NAMING,
            "message": "No format string defined -- result may display inconsistently",
            "suggestion": "Set format string: '0.0%' for ratios, '#,0' for integers, '#,0.00' for decimals",
        }
    return None


def _check_no_display_folder(measure: dict) -> Optional[dict]:
    """Measure has no display folder."""
    if not measure.get("displayFolder") and not measure.get("DisplayFolder"):
        return {
            "rule": "NO_DISPLAY_FOLDER",
            "severity": Severity.INFO,
            "category": Category.NAMING,
            "message": "No display folder set -- measure appears at top level of table",
            "suggestion": "Assign a display folder to organize measures, e.g. 'Sales', 'Customer', 'Time'",
        }
    return None


def _check_long_expression(expr: str, max_len: int = 500) -> Optional[dict]:
    """Expression too long."""
    if len(expr) > max_len:
        return {
            "rule": "LONG_EXPRESSION",
            "severity": Severity.INFO,
            "category": Category.MAINTAINABILITY,
            "message": f"Expression is {len(expr)} characters (threshold: {max_len}) -- consider refactoring into smaller measures",
            "suggestion": "Break complex logic into intermediate measures, or use variables (VAR) for clarity",
        }
    return None


def _check_no_comments(expr: str) -> Optional[dict]:
    """No comments in DAX expression."""
    if '//' not in expr and '/*' not in expr and len(expr) > 200:
        return {
            "rule": "NO_COMMENTS",
            "severity": Severity.INFO,
            "category": Category.MAINTAINABILITY,
            "message": "Complex expression has no comments -- future maintainers may struggle to understand the logic",
            "suggestion": "Add // comments to explain business logic, especially for complex calculations",
        }
    return None


def _check_hardcoded_values(expr: str) -> Optional[dict]:
    """Hardcoded numeric values that might be magic numbers."""
    # Find standalone numbers (not in strings, not function args like 0, 1, 100)
    # Look for numbers > 1000 that might be thresholds
    numbers = re.findall(r'(?<!\w)(\d{4,})(?!\w)', expr)
    if numbers:
        unique = list(set(numbers))[:5]
        return {
            "rule": "HARDCODED_VALUES",
            "severity": Severity.INFO,
            "category": Category.MAINTAINABILITY,
            "message": f"Hardcoded numeric values detected: {', '.join(unique)} -- consider using parameters or measures",
            "suggestion": "Move hardcoded values to a parameter table or define as WHAT-IF parameters",
        }
    return None


def _check_select_columns_order(expr: str) -> Optional[dict]:
    """SELECTCOLUMNS with ADDCOLUMNS pattern (can be simplified)."""
    if re.search(r'SELECTCOLUMNS\s*\(\s*ADDCOLUMNS\s*\(', expr, re.IGNORECASE):
        return {
            "rule": "SELECTCOLUMNS_ADDCOLUMNS",
            "severity": Severity.INFO,
            "category": Category.PERFORMANCE,
            "message": "SELECTCOLUMNS(ADDCOLUMNS(...)) -- can be simplified to a single SELECTCOLUMNS",
            "suggestion": "Merge into a single SELECTCOLUMNS with all column definitions",
        }
    return None


def _check_isfiltered_in_measure(expr: str) -> Optional[dict]:
    """ISFILTERED/ISCROSSFILTERED used in measure definition."""
    if re.search(r'\b(ISFILTERED|ISCROSSFILTERED)\s*\(', expr, re.IGNORECASE):
        return {
            "rule": "ISFILTERED_IN_MEASURE",
            "severity": Severity.WARNING,
            "category": Category.CORRECTNESS,
            "message": "ISFILTERED()/ISCROSSFILTERED() in a measure definition -- results depend on visual context, may be unpredictable",
            "suggestion": "Consider using explicit filter context or documenting the expected behavior clearly",
        }
    return None


def _check_all_vs_allselected(expr: str) -> Optional[dict]:
    """ALL() used where ALLSELECTED() might be more appropriate."""
    # ALL('table') used -- could be ALLSELECTED for visual-level calculations
    all_matches = re.findall(r'\bALL\s*\(\s*\'([^\']+)\'\s*\)', expr, re.IGNORECASE)
    if all_matches and 'ALLSELECTED' not in expr.upper():
        return {
            "rule": "ALL_VS_ALLSELECTED",
            "severity": Severity.INFO,
            "category": Category.CORRECTNESS,
            "message": f"ALL({all_matches[0]}) used -- verify ALLSELECTED() is not more appropriate for visual-level calculations",
            "suggestion": "ALL() removes all filters; ALLSELECTED() preserves outer filters from visuals/slicers",
        }
    return None


def _check_blank_comparison(expr: str) -> Optional[dict]:
    """== BLANK() or <> BLANK() comparison."""
    if re.search(r'[=!<>]=?\s*BLANK\s*\(\)', expr, re.IGNORECASE):
        return {
            "rule": "BLANK_COMPARISON",
            "severity": Severity.INFO,
            "category": Category.CORRECTNESS,
            "message": "Direct comparison with BLANK() -- use ISBLANK() for clarity and correctness",
            "suggestion": "Replace 'x = BLANK()' with 'ISBLANK(x)' and 'x <> BLANK()' with 'NOT ISBLANK(x)'",
        }
    return None


def _check_userelationship_no_calculate(expr: str) -> Optional[dict]:
    """USERELATIONSHIP used without CALCULATE."""
    if 'USERELATIONSHIP' in expr.upper():
        if 'CALCULATE' not in expr.upper():
            return {
                "rule": "USERELATIONSHIP_NO_CALCULATE",
                "severity": Severity.ERROR,
                "category": Category.CORRECTNESS,
                "message": "USERELATIONSHIP() used without CALCULATE() -- USERELATIONSHIP only works inside CALCULATE",
                "suggestion": "Wrap in CALCULATE: CALCULATE(expr, USERELATIONSHIP('Table'[Col1], 'Table'[Col2]))",
            }
    return None


def _check_selectedvalue_no_alternative(expr: str) -> Optional[dict]:
    """SELECTEDVALUE without alternative."""
    if re.search(r'SELECTEDVALUE\s*\([^,]+\)', expr, re.IGNORECASE):
        return {
            "rule": "SELECTEDVALUE_NO_ALTERNATIVE",
            "severity": Severity.INFO,
            "category": Category.CORRECTNESS,
            "message": "SELECTEDVALUE() without alternative -- returns BLANK() when multiple values are selected",
            "suggestion": "Provide a fallback: SELECTEDVALUE(column, \"Multiple\") or use HASONEVALUE check",
        }
    return None


def _check_variables_not_used(expr: str) -> Optional[dict]:
    """VAR defined but RETURN not found (syntax error)."""
    has_var = bool(re.search(r'\bVAR\s+\w+\s*=', expr, re.IGNORECASE))
    has_return = 'RETURN' in expr.upper()
    if has_var and not has_return:
        return {
            "rule": "VAR_NO_RETURN",
            "severity": Severity.ERROR,
            "category": Category.CORRECTNESS,
            "message": "VAR defined but no RETURN statement -- DAX will fail to evaluate",
            "suggestion": "Add RETURN after the last variable definition",
        }
    return None


# ──────────────────────────────────────────────────────────────
#  All Rules Registry
# ──────────────────────────────────────────────────────────────

# Expression-only rules (don't need measure metadata)
EXPRESSION_RULES = [
    _check_divide_no_alternative,
    _check_earlier_instead_of_var,
    _check_nested_if_depth,
    _check_switch_no_else,
    _check_calculate_no_filter,
    _check_filter_values,
    _check_multiple_filter,
    _check_sumx_no_filter,
    _check_long_expression,
    _check_no_comments,
    _check_hardcoded_values,
    _check_select_columns_order,
    _check_isfiltered_in_measure,
    _check_all_vs_allselected,
    _check_blank_comparison,
    _check_userelationship_no_calculate,
    _check_selectedvalue_no_alternative,
    _check_variables_not_used,
]

# Measure-level rules (need measure metadata)
MEASURE_RULES = [
    _check_no_format_string,
    _check_no_display_folder,
]


# ──────────────────────────────────────────────────────────────
#  Analyzer
# ──────────────────────────────────────────────────────────────

class DaxAnalyzer:
    """Analyzes DAX measures for best practice violations."""

    def __init__(self):
        self.expression_rules = list(EXPRESSION_RULES)
        self.measure_rules = list(MEASURE_RULES)

    def analyze_expression(self, expr: str) -> list[dict]:
        """Run all expression-level rules against a DAX expression."""
        if not expr or not expr.strip():
            return [{
                "rule": "EMPTY_EXPRESSION",
                "severity": Severity.ERROR,
                "category": Category.CORRECTNESS,
                "message": "Empty DAX expression",
                "suggestion": "Define a valid DAX expression",
            }]
        issues = []
        for rule_fn in self.expression_rules:
            result = rule_fn(expr)
            if result:
                issues.append(result)
        return issues

    def analyze_measure(self, measure: dict) -> list[dict]:
        """Run all rules against a measure dict (name, table, expression, formatString, displayFolder)."""
        expr = measure.get("expression") or measure.get("Expression") or ""
        issues = self.analyze_expression(expr)
        for rule_fn in self.measure_rules:
            result = rule_fn(measure)
            if result:
                issues.append(result)
        return issues

    def analyze_all(self, measures: list[dict]) -> dict:
        """Analyze all measures and return summary with issues grouped by severity."""
        all_issues = []
        stats = {
            "total_measures": len(measures),
            "measures_with_issues": 0,
            "total_issues": 0,
            "by_severity": {Severity.ERROR: 0, Severity.WARNING: 0, Severity.INFO: 0},
            "by_category": {},
            "by_rule": {},
            "issues": [],
        }

        for m in measures:
            measure_issues = self.analyze_measure(m)
            if measure_issues:
                stats["measures_with_issues"] += 1
                stats["total_issues"] += len(measure_issues)
                for issue in measure_issues:
                    stats["by_severity"][issue["severity"]] += 1
                    cat = issue["category"]
                    stats["by_category"][cat] = stats["by_category"].get(cat, 0) + 1
                    rule = issue["rule"]
                    stats["by_rule"][rule] = stats["by_rule"].get(rule, 0) + 1
                    all_issues.append({
                        **issue,
                        "measure": m.get("name") or m.get("Name", "?"),
                        "table": m.get("table") or m.get("_TableName") or m.get("Table", "?"),
                    })

        # Sort: errors first, then warnings, then info
        severity_order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
        all_issues.sort(key=lambda x: (severity_order.get(x["severity"], 3), x["rule"]))
        stats["issues"] = all_issues

        return stats

    def format_report(self, stats: dict, max_issues: int = 100) -> str:
        """Format BPA results as a readable report."""
        if stats["total_issues"] == 0:
            return f"[OK] All {stats['total_measures']} measures passed the Best Practice Analyzer. No issues found!"

        lines = [
            f"DAX Best Practice Analysis",
            f"============================",
            f"",
            f"Measures analyzed: {stats['total_measures']}",
            f"Measures with issues: {stats['measures_with_issues']} ({stats['measures_with_issues']*100//max(1,stats['total_measures'])}%)",
            f"Total issues: {stats['total_issues']}",
            f"",
            f"By Severity:",
            f"  [ERR] Errors:   {stats['by_severity'][Severity.ERROR]}",
            f"  [WARN] Warnings: {stats['by_severity'][Severity.WARNING]}",
            f"  [INFO] Info:     {stats['by_severity'][Severity.INFO]}",
            f"",
            f"By Category:",
        ]
        for cat, count in sorted(stats["by_category"].items(), key=lambda x: -x[1]):
            lines.append(f"  {cat}: {count}")

        lines.append(f"")
        lines.append(f"By Rule (top 10):")
        for rule, count in sorted(stats["by_rule"].items(), key=lambda x: -x[1])[:10]:
            lines.append(f"  {rule}: {count}")

        lines.append(f"")
        lines.append(f"--- Issues ---")
        severity_icon = {Severity.ERROR: "[ERR]", Severity.WARNING: "[WARN]", Severity.INFO: "[INFO]"}
        for i, issue in enumerate(stats["issues"]):
            if i >= max_issues:
                lines.append(f"\n... ({len(stats['issues']) - max_issues} more issues)")
                break
            icon = severity_icon.get(issue["severity"], "[?]")
            lines.append(f"\n{icon} [{issue['table']}] {issue['measure']} -- {issue['rule']}")
            lines.append(f"   {issue['message']}")
            lines.append(f"   >> {issue['suggestion']}")

        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
#  Convenience function
# ──────────────────────────────────────────────────────────────

def analyze_measures(measures: list[dict]) -> str:
    """Analyze a list of measures and return a formatted report."""
    analyzer = DaxAnalyzer()
    stats = analyzer.analyze_all(measures)
    return analyzer.format_report(stats)