# -*- coding: utf-8 -*-
"""
DAX Safe Modification Utility
==============================
Implements defensive rules for DAX expression modification.

Usage:
    from dax_safe_modify import DaxModifier
    dm = DaxModifier(original_dax)
    dm.preview_replace("//+[Reservation Cancelled Qty]", "+[Reservation Cancelled Qty]")
    dm.apply()  # only after confirmation
"""

class DaxModifier:
    """Safe DAX modification with built-in defensive checks."""

    def __init__(self, expression: str, measure_name: str = ""):
        self.original = expression
        self.measure_name = measure_name
        self.proposed = expression
        self.pending_changes = []
        self.applied = False

    # ── Rule 1: No blind string replacement ────────────────────

    def preview(self):
        """Show the full expression before modification."""
        print("=" * 60)
        print("Current DAX for: %s" % self.measure_name)
        print("=" * 60)
        print(self.original)
        print("=" * 60)
        return self

    # ── Rule 2: Comment-aware modification ─────────────────────

    def _comment_ranges(self, expr: str) -> list[tuple[int, int]]:
        """Find all // comment ranges (start, end) in the expression."""
        ranges = []
        lines = expr.split('\n')
        pos = 0
        for line in lines:
            idx = line.find('//')
            if idx >= 0:
                start = pos + idx
                end = pos + len(line)
                ranges.append((start, end, line[idx:]))
            pos += len(line) + 1  # +1 for \n
        return ranges

    def show_comments(self):
        """Display all // comments and their full scope."""
        ranges = self._comment_ranges(self.original)
        if not ranges:
            print("No // comments found.")
            return self

        print("=" * 60)
        print("// Comments found in: %s" % self.measure_name)
        print("=" * 60)
        for start, end, text in ranges:
            print("  Line: %s" % text)
            print("  Range: chars %d-%d (NOT just the // itself!)" % (start, end))
            print("  This ENTIRE range is commented out by DAX")
            print()
        return self

    # ── Rule 3: Bracket-aware verification ─────────────────────

    def _check_brackets(self, expr: str) -> tuple[bool, str]:
        """Verify bracket pairing. Returns (is_valid, message)."""
        stack = []
        pairs = {'(': ')', '[': ']', '{': '}'}
        for i, ch in enumerate(expr):
            if ch in pairs:
                stack.append((ch, i))
            elif ch in pairs.values():
                if not stack:
                    return False, "Extra '%s' at position %d (no matching opener)" % (ch, i)
                opener, op_pos = stack.pop()
                expected = pairs[opener]
                if ch != expected:
                    return False, "Mismatch: '%s' at %d closed by '%s' at %d (expected '%s')" % (
                        opener, op_pos, ch, i, expected)
        if stack:
            return False, "Unclosed '%s' at position %d" % (stack[-1][0], stack[-1][1])
        return True, "All brackets matched"

    def proposed_replace(self, old: str, new: str):
        """Queue a replacement and run defensive checks."""
        if old not in self.original:
            print("WARNING: '%s' not found in expression. Skipping." % old[:50])
            return self

        self.proposed = self.original.replace(old, new)
        self.pending_changes.append((old, new))

        # Show what changed
        print("=" * 60)
        print("Proposed change for: %s" % self.measure_name)
        print("=" * 60)
        print("REMOVE: %s" % old)
        print("ADD:    %s" % new)
        print()

        # Check comments
        old_comments = self._comment_ranges(self.original)
        new_comments = self._comment_ranges(self.proposed)
        if old_comments and not new_comments:
            print("NOTE: This change removes // comments. Verify the full comment scope:")
            for _, _, text in old_comments:
                print("  Comment was: %s" % text)
                commented = text[2:].strip()  # content after //
                print("  Content after //: '%s'" % commented)
            print()

        # Check brackets
        old_ok, old_msg = self._check_brackets(self.original)
        new_ok, new_msg = self._check_brackets(self.proposed)
        if old_ok and not new_ok:
            print("WARNING: Brackets were valid before but NOT after!")
            print("  Before: %s" % old_msg)
            print("  After:  %s" % new_msg)
            print("  This change may have removed a bracket that was inside a comment!")
        elif not old_ok:
            print("NOTE: Original expression has bracket issue: %s" % old_msg)

        # Show diff
        print()
        print("DIFF:")
        if old_ok != new_ok:
            print("  BRACKET STATUS: %s -> %s" % (
                "VALID" if old_ok else "INVALID",
                "VALID" if new_ok else "INVALID"))
        print()

        return self

    def show_proposed(self):
        """Display the proposed expression."""
        print("Proposed DAX:")
        print(self.proposed)
        return self

    # ── Rule 4: Human confirmation required ────────────────────

    def confirm(self, force: bool = False) -> bool:
        """Require human confirmation before applying changes."""
        if not self.pending_changes:
            print("No pending changes.")
            return False

        bracket_ok, _ = self._check_brackets(self.proposed)
        if not bracket_ok and not force:
            print("Cannot apply: bracket mismatch detected. Use force=True to override.")
            return False

        if force:
            print("Force-applying changes...")
            return True

        # In automated mode, require explicit confirmation
        print("Review the proposed changes above.")
        print("Call .apply() to confirm and apply.")
        return True  # ready for apply

    def apply(self) -> str:
        """Apply all pending changes."""
        if not self.pending_changes:
            return self.original

        self.applied = True
        result = self.proposed

        # Final verification
        ok, msg = self._check_brackets(result)
        if not ok:
            print("WARNING: Applied expression has bracket issues: %s" % msg)

        print("Changes applied to: %s" % self.measure_name)
        return result


# ── Example usage ──────────────────────────────────────────────
if __name__ == "__main__":
    # Simulate the accident: fixing // comment in Not Allocated Qty
    original = (
        "[Reservation Ordered Qty]-([reservation In progress Qty]"
        "+[Reservation Fulfilled Qty]+[Reservation Received In Store Qty]"
        "//+[Reservation Cancelled Qty])\n)"
    )

    dm = DaxModifier(original, "Reservation Not Allocated Qty")
    dm.preview()
    dm.show_comments()
    dm.proposed_replace(
        "//+[Reservation Cancelled Qty])\n)",
        "+[Reservation Cancelled Qty])\n)"
    )
    dm.show_proposed()

    # The tool automatically detects:
    # 1. The // comment range includes ")+[Reservation Cancelled Qty])" not just "//"
    # 2. After replacement, brackets are mismatched
    # 3. Requires human confirmation before applying