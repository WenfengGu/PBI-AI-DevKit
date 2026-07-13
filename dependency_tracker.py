"""
Dependency Tracker for Power BI Models
======================================
Tracks measure and column dependencies across the model.
Builds a dependency graph from DAX expressions.

Supports:
  - Forward deps: which measures/columns does THIS measure depend on?
  - Backward deps: which measures depend on THIS measure/column? (impact analysis)
  - Full dependency graph with topological ordering
  - Circular dependency detection

Usage:
    from dependency_tracker import DependencyTracker
    tracker = DependencyTracker()
    tracker.build_graph(measures, relationships)
    deps = tracker.get_dependencies("Total Sales")
    impact = tracker.get_impact("[KPI]")
"""

import re
from collections import defaultdict, deque
from typing import Optional


# ──────────────────────────────────────────────────────────────
#  DAX Reference Parser
# ──────────────────────────────────────────────────────────────

def parse_dax_references(expr: str, current_table: str = "") -> dict:
    """Extract all references from a DAX expression.

    Returns dict with:
      - measures: set of measure names referenced (bare [Name])
      - columns: set of (table, column) tuples
      - tables: set of table names referenced
      - functions: set of DAX function names used
    """
    if not expr:
        return {"measures": set(), "columns": set(), "tables": set(), "functions": set()}

    result = {
        "measures": set(),
        "columns": set(),
        "tables": set(),
        "functions": set(),
    }

    # 1. Extract fully qualified column references: 'Table'[Column]
    qualified = re.findall(r"'([^']+)'\[([^\]]+)\]", expr)
    for table, column in result["columns"]:
        pass  # placeholder
    for table, column in qualified:
        result["columns"].add((table, column))

    # 2. Extract table references: 'Table' (in function calls like ALL('Table'), VALUES('Table'))
    # But NOT 'Table'[Column] -- we need table refs that are standalone
    table_refs = re.findall(r"'([^']+)'(?!\s*\[)", expr)
    for t in table_refs:
        result["tables"].add(t)

    # 3. Extract bare column/measure references: [Name]
    # These are ambiguous -- could be measure or column in current table
    bare_refs = re.findall(r'(?<!\w)\[([^\]]+)\](?!\s*\w)', expr)
    for ref in bare_refs:
        result["measures"].add(ref)

    # 4. Extract DAX function names: FUNC(
    functions = re.findall(r'\b([A-Z_][A-Z0-9_]*)\s*\(', expr, re.IGNORECASE)
    # Filter to common DAX functions
    dax_funcs = {
        'SUM', 'SUMX', 'AVERAGE', 'AVERAGEX', 'MIN', 'MINX', 'MAX', 'MAXX',
        'COUNT', 'COUNTA', 'COUNTX', 'COUNTROWS', 'DISTINCTCOUNT', 'DISTINCTCOUNTNOBLANK',
        'CALCULATE', 'CALCULATETABLE', 'FILTER', 'ALL', 'ALLEXCEPT', 'ALLSELECTED',
        'ALLNOBLANKROW', 'ALLSELECTED', 'REMOVEFILTERS', 'KEEPFILTERS',
        'VALUES', 'DISTINCT', 'RELATED', 'RELATEDTABLE', 'USERELATIONSHIP',
        'CROSSFILTER', 'TREATAS', 'SELECTEDVALUE', 'HASONEVALUE', 'HASONEFILTER',
        'ISFILTERED', 'ISCROSSFILTERED', 'ISINSCOPE', 'IF', 'SWITCH', 'AND', 'OR',
        'NOT', 'TRUE', 'FALSE', 'BLANK', 'IFERROR', 'ISERROR', 'ISBLANK',
        'DIVIDE', 'FORMAT', 'DATEADD', 'DATESYTD', 'DATESMTD', 'DATESQTD',
        'DATESINPERIOD', 'DATESBETWEEN', 'SAMEPERIODLASTYEAR', 'PARALLELPERIOD',
        'PREVIOUSDAY', 'PREVIOUSMONTH', 'PREVIOUSQUARTER', 'PREVIOUSYEAR',
        'NEXTDAY', 'NEXTMONTH', 'NEXTQUARTER', 'NEXTYEAR',
        'TOTALYTD', 'TOTALMTD', 'TOTALQTD', 'CLOSINGBALANCEYEAR', 'CLOSINGBALANCEMONTH',
        'OPENINGBALANCEYEAR', 'OPENINGBALANCEMONTH',
        'STARTOFMONTH', 'STARTOFQUARTER', 'STARTOFYEAR',
        'ENDOFMONTH', 'ENDOFQUARTER', 'ENDOFYEAR',
        'RANKX', 'TOPN', 'CONCATENATEX', 'ADDCOLUMNS', 'SUMMARIZE', 'SUMMARIZECOLUMNS',
        'SELECTCOLUMNS', 'GROUPBY', 'CROSSJOIN', 'UNION', 'INTERSECT', 'EXCEPT',
        'NATURALINNERJOIN', 'NATURALLEFTOUTERJOIN', 'GENERATE', 'GENERATEALL',
        'ROW', 'ROLLUP', 'ROLLUPADDISSUBTOTAL', 'ROLLUPISSUBTOTAL',
        'LOOKUPVALUE', 'VAR', 'RETURN', 'EVALUATE', 'DEFINE', 'ORDER', 'RANK',
        'EARLIER', 'EARLIEST', 'PATH', 'PATHCONTAINS', 'PATHITEM', 'PATHLENGTH',
        'CONTAINS', 'CONTAINSROW', 'CONTAINSSTRING', 'FIND', 'SEARCH',
        'LEFT', 'RIGHT', 'MID', 'LEN', 'LOWER', 'UPPER', 'TRIM', 'SUBSTITUTE',
        'COMBINEVALUES', 'REPT', 'CONCATENATE', 'VALUE', 'INT', 'ROUND',
        'ROUNDUP', 'ROUNDDOWN', 'MROUND', 'FLOOR', 'CEILING', 'ABS', 'SIGN',
        'SQRT', 'POWER', 'EXP', 'LN', 'LOG', 'LOG10', 'MOD', 'QUOTIENT',
        'RAND', 'RANDBETWEEN', 'SIN', 'COS', 'TAN', 'ASIN', 'ACOS', 'ATAN',
        'PI', 'DEGREES', 'RADIANS', 'WEEKNUM', 'WEEKDAY', 'YEAR', 'MONTH',
        'DAY', 'HOUR', 'MINUTE', 'SECOND', 'DATE', 'TIME', 'NOW', 'TODAY',
        'UTCNOW', 'UTCTODAY', 'EOMONTH', 'EDATE', 'DATEDIFF', 'YEARFRAC',
        'ISNUMBER', 'ISTEXT', 'ISNONTEXT', 'ISLOGICAL', 'ISODD', 'ISEVEN',
        'ISDATE', 'ISCURRENCY', 'TYPE', 'ERROR',
    }
    for f in functions:
        if f.upper() in dax_funcs:
            result["functions"].add(f.upper())

    return result


# ──────────────────────────────────────────────────────────────
#  Dependency Graph
# ──────────────────────────────────────────────────────────────

class DependencyTracker:
    """Tracks dependencies between measures, columns, and tables."""

    def __init__(self):
        # forward_deps[measure_key] = {measure_keys that this depends on}
        self.forward_deps: dict[str, set[str]] = defaultdict(set)
        # reverse_deps[measure_key] = {measure_keys that depend on this}
        self.reverse_deps: dict[str, set[str]] = defaultdict(set)
        # measure info: key -> {name, table, expression, ...}
        self.measures: dict[str, dict] = {}
        # table -> set of columns
        self.table_columns: dict[str, set[str]] = defaultdict(set)
        # tables set
        self.tables: set[str] = set()

    def _key(self, table: str, name: str) -> str:
        """Create a unique key for a measure."""
        return f"[{table}] {name}"

    def build_graph(self, measures: list[dict], tables: list[str] = None):
        """Build the full dependency graph from a list of measures.

        measures: list of dicts with 'name', 'table', 'expression' keys
        tables: optional list of table names
        """
        self.measures.clear()
        self.forward_deps.clear()
        self.reverse_deps.clear()
        self.table_columns.clear()

        if tables:
            self.tables = set(tables)

        # Index all measures by key
        for m in measures:
            mname = m.get("name") or m.get("Name", "?")
            mtable = m.get("table") or m.get("_TableName") or m.get("Table", "?")
            key = self._key(mtable, mname)
            self.measures[key] = {
                "name": mname,
                "table": mtable,
                "expression": m.get("expression") or m.get("Expression", ""),
            }

        # Build measure name -> table mapping for disambiguation
        measure_to_table = defaultdict(list)
        for key, info in self.measures.items():
            measure_to_table[info["name"]].append(info["table"])

        # Parse each measure's expression and build edges
        for key, info in self.measures.items():
            expr = info["expression"]
            current_table = info["table"]
            refs = parse_dax_references(expr, current_table)

            # Track table columns
            for table, col in refs["columns"]:
                self.table_columns[table].add(col)

            # Track measure dependencies
            for ref_name in refs["measures"]:
                # Try to resolve which measure this refers to
                candidates = measure_to_table.get(ref_name, [])
                if len(candidates) == 1:
                    dep_key = self._key(candidates[0], ref_name)
                elif current_table in candidates:
                    dep_key = self._key(current_table, ref_name)
                elif len(candidates) > 1:
                    # Ambiguous -- add all possible
                    for c in candidates:
                        dep_key = self._key(c, ref_name)
                        if dep_key in self.measures and dep_key != key:
                            self.forward_deps[key].add(dep_key)
                            self.reverse_deps[dep_key].add(key)
                    continue
                else:
                    # Not a measure (might be a column) -- skip
                    continue

                if dep_key in self.measures and dep_key != key:
                    self.forward_deps[key].add(dep_key)
                    self.reverse_deps[dep_key].add(key)

    def get_dependencies(self, measure_name: str, table: str = None) -> dict:
        """Get all measures that THIS measure depends on (forward dependencies).

        If table is not specified, finds the first match.
        Returns dict with direct and transitive dependencies.
        """
        key = self._resolve_key(measure_name, table)
        if not key:
            return {"error": f"Measure '{measure_name}' not found", "direct": [], "all": []}

        direct = sorted(self.forward_deps.get(key, set()))
        # BFS for transitive
        all_deps = set()
        queue = deque(direct)
        while queue:
            dep = queue.popleft()
            if dep not in all_deps:
                all_deps.add(dep)
                for sub in self.forward_deps.get(dep, set()):
                    if sub not in all_deps:
                        queue.append(sub)

        return {
            "measure": key,
            "direct": direct,
            "all": sorted(all_deps),
            "depth": len(all_deps),
        }

    def get_impact(self, measure_name: str, table: str = None) -> dict:
        """Get all measures that depend on THIS measure (impact analysis).

        If this measure changes, what else is affected?
        """
        key = self._resolve_key(measure_name, table)
        if not key:
            return {"error": f"Measure '{measure_name}' not found", "direct": [], "all": []}

        direct = sorted(self.reverse_deps.get(key, set()))
        # BFS for transitive
        all_impacted = set()
        queue = deque(direct)
        while queue:
            dep = queue.popleft()
            if dep not in all_impacted:
                all_impacted.add(dep)
                for sub in self.reverse_deps.get(dep, set()):
                    if sub not in all_impacted:
                        queue.append(sub)

        return {
            "measure": key,
            "directly_affected": direct,
            "all_affected": sorted(all_impacted),
            "depth": len(all_impacted),
        }

    def get_unused_measures(self) -> list[str]:
        """Find measures that are not referenced by any other measure."""
        unused = []
        for key in self.measures:
            if key not in self.reverse_deps or not self.reverse_deps[key]:
                # Check if it's also not a dependency of anything
                has_impact = any(key in deps for deps in self.forward_deps.values())
                if not has_impact:
                    # Only truly unused if it also doesn't depend on anything
                    # (standalone leaf measures might be used in visuals, not in other measures)
                    pass
                unused.append(key)
        return sorted(unused)

    def get_orphan_measures(self) -> list[str]:
        """Find measures that reference non-existent measures."""
        orphans = []
        for key, deps in self.forward_deps.items():
            for dep in deps:
                if dep not in self.measures:
                    orphans.append(f"{key} -> {dep} (missing)")
        return sorted(orphans)

    def detect_circular_dependencies(self) -> list[list[str]]:
        """Detect circular dependency chains using DFS."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {key: WHITE for key in self.measures}
        cycles = []

        def dfs(node, path):
            color[node] = GRAY
            path.append(node)
            for neighbor in self.forward_deps.get(node, set()):
                if neighbor not in color:
                    continue
                if color[neighbor] == GRAY:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)
                elif color[neighbor] == WHITE:
                    dfs(neighbor, path)
            path.pop()
            color[node] = BLACK

        for key in self.measures:
            if color[key] == WHITE:
                dfs(key, [])

        return cycles

    def get_topological_order(self) -> list[str]:
        """Return measures in topological order (dependencies first).
        Useful for understanding evaluation order.
        """
        in_degree = {key: 0 for key in self.measures}
        for key, deps in self.forward_deps.items():
            for dep in deps:
                if dep in in_degree:
                    in_degree[key] += 1

        queue = deque([k for k, d in in_degree.items() if d == 0])
        result = []
        while queue:
            node = queue.popleft()
            result.append(node)
            for dependent in self.reverse_deps.get(node, set()):
                if dependent in in_degree:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        if len(result) < len(self.measures):
            result.append("... (cycle detected -- some measures could not be ordered)")

        return result

    def get_most_used(self, top_n: int = 20) -> list[tuple[str, int]]:
        """Return the most referenced measures (highest impact if changed)."""
        counts = [(key, len(deps)) for key, deps in self.reverse_deps.items() if deps]
        counts.sort(key=lambda x: -x[1])
        return counts[:top_n]

    def _resolve_key(self, measure_name: str, table: str = None) -> Optional[str]:
        """Resolve a measure name to its full key."""
        if table:
            key = self._key(table, measure_name)
            if key in self.measures:
                return key

        # Search all tables
        matches = []
        for key, info in self.measures.items():
            if info["name"] == measure_name:
                matches.append(key)

        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            return matches[0]  # Return first match
        return None

    def format_dependencies(self, measure_name: str, table: str = None) -> str:
        """Format dependency info for a measure as readable text."""
        deps = self.get_dependencies(measure_name, table)
        if "error" in deps:
            return deps["error"]

        impact = self.get_impact(measure_name, table)

        lines = [
            f"Dependency Analysis for {deps['measure']}",
            "=" * 50,
            "",
            f"Depends on (direct, {len(deps['direct'])}):",
        ]
        for d in deps["direct"]:
            lines.append(f"  <- {d}")
        if deps["all"]:
            lines.append(f"  ... plus {len(deps['all']) - len(deps['direct'])} transitive")

        lines.extend([
            "",
            f"Depended on by (direct, {len(impact['directly_affected'])}):",
        ])
        for d in impact["directly_affected"]:
            lines.append(f"  -> {d}")
        if impact["all_affected"]:
            lines.append(f"  ... plus {len(impact['all_affected']) - len(impact['directly_affected'])} transitive")

        return "\n".join(lines)

    def format_summary(self) -> str:
        """Format a summary of the dependency graph."""
        total = len(self.measures)
        with_deps = sum(1 for deps in self.forward_deps.values() if deps)
        with_impact = sum(1 for deps in self.reverse_deps.values() if deps)
        isolated = total - with_deps - with_impact
        cycles = self.detect_circular_dependencies()
        most_used = self.get_most_used(10)

        lines = [
            f"Dependency Graph Summary",
            "=" * 50,
            f"",
            f"Total measures: {total}",
            f"Measures with dependencies: {with_deps}",
            f"Measures with dependents: {with_impact}",
            f"Isolated measures (no connections): {max(0, isolated)}",
            f"Circular dependencies: {len(cycles)}",
            f"",
            f"Most Referenced (Top {len(most_used)}):",
        ]
        for key, count in most_used:
            lines.append(f"  {count:3d} -> {key}")

        if cycles:
            lines.append(f"")
            lines.append(f"[WARN] Circular Dependencies:")
            for i, cycle in enumerate(cycles):
                lines.append(f"  Cycle {i+1}: {' -> '.join(cycle)}")

        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
#  Convenience functions
# ──────────────────────────────────────────────────────────────

def build_and_analyze(measures: list[dict], tables: list[str] = None) -> DependencyTracker:
    """Build a dependency graph from measures and return the tracker."""
    tracker = DependencyTracker()
    tracker.build_graph(measures, tables)
    return tracker