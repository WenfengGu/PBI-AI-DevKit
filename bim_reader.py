"""
BIM File Reader/Writer
======================
Reads and modifies Tabular Model Schema (BIM) JSON files.
BIM files are the standard format for Tabular Editor, SSDT, and Power BI Project.
"""
import json, os, shutil
from pathlib import Path
from typing import Optional
from collections import Counter


def _expr_str(expr) -> str:
    return '\n'.join(expr) if isinstance(expr, list) else str(expr or '')


class BimModel:
    def __init__(self, bim_path: str):
        self.path = Path(bim_path)
        with open(bim_path, 'r', encoding='utf-8-sig') as f:
            self.data = json.load(f)
        self.model = self.data.get('model', {})

    @property
    def name(self) -> str:
        return self.data.get('name', 'Unknown')

    @property
    def compatibility_level(self) -> int:
        return self.data.get('compatibilityLevel', 0)

    def get_tables(self) -> list[dict]:
        return self.model.get('tables', [])

    def get_measures(self, table_filter: str = None, name_filter: str = None) -> list[dict]:
        results = []
        for t in self.get_tables():
            if table_filter and table_filter.lower() not in t['name'].lower():
                continue
            for m in t.get('measures', []):
                if name_filter and name_filter.lower() not in m['name'].lower():
                    continue
                results.append({
                    'name': m['name'],
                    'table': t['name'],
                    'expression': _expr_str(m.get('expression', '')),
                    'displayFolder': m.get('displayFolder', ''),
                    'formatString': m.get('formatString', ''),
                    'description': m.get('description', ''),
                })
        return results

    def get_columns(self, table_name: str) -> list[dict]:
        for t in self.get_tables():
            if t['name'] == table_name:
                return t.get('columns', [])
        return []

    def get_relationships(self) -> list[dict]:
        return self.model.get('relationships', [])

    def get_roles(self) -> list[dict]:
        roles = self.model.get('roles', {})
        if isinstance(roles, list):
            return roles
        return roles.get('roles', [])

    def get_partitions(self) -> list[dict]:
        results = []
        for t in self.get_tables():
            for p in t.get('partitions', []):
                src = p.get('source', {})
                expr = _expr_str(src.get('expression', ''))
                if expr:
                    results.append({
                        'table': t['name'],
                        'name': p['name'],
                        'expression': expr,
                        'type': src.get('type', 'm'),
                    })
        return results

    def search_dax(self, pattern: str, case_sensitive: bool = False) -> list[dict]:
        results = []
        for m in self.get_measures():
            expr = _expr_str(m.get('expression', ''))
            if case_sensitive:
                found = pattern in expr
            else:
                found = pattern.lower() in expr.lower()
            if found:
                results.append(m)
        return results

    def replace_in_measure(self, table_name: str, measure_name: str,
                           old_text: str, new_text: str) -> bool:
        for t in self.model.get('tables', []):
            if t['name'] == table_name:
                for m in t.get('measures', []):
                    if m['name'] == measure_name:
                        expr = _expr_str(m.get('expression', ''))
                        if old_text in expr:
                            m['expression'] = expr.replace(old_text, new_text)
                            return True
                        return False
        return False

    def save(self, backup: bool = True):
        if backup:
            backup_path = self.path.with_suffix('.bim.bak')
            shutil.copy2(self.path, backup_path)
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get_summary(self) -> dict:
        tables = self.get_tables()
        measures = self.get_measures()
        partitions = self.get_partitions()
        return {
            'name': self.name,
            'compatibility_level': self.compatibility_level,
            'tables': len(tables),
            'visible_tables': len([t for t in tables if not t.get('isHidden')]),
            'measures': len(measures),
            'relationships': len(self.get_relationships()),
            'roles': len(self.get_roles()),
            'partitions_with_m': len(partitions),
        }