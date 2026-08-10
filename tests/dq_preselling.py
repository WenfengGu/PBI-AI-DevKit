# -*- coding: utf-8 -*-
"""
Data Quality Check — Preselling Reporting CN
=============================================
Thin wrapper around dq_template.py — uses dq_config_preselling.json.

Usage:
    python dq_preselling.py                    # Full check
    python dq_preselling.py --quick             # Row counts + freshness only
    python dq_preselling.py --output report.md  # Save report to file
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dq_template import DataQualityChecker

if __name__ == "__main__":
    import argparse
    config = os.path.join(os.path.dirname(__file__), "dq_config_preselling.json")

    parser = argparse.ArgumentParser(description="Data Quality Check for Preselling Reporting CN")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--output", "-o", type=str)
    args = parser.parse_args()

    checker = DataQualityChecker(config)
    checker.run_all(quick=args.quick)

    if args.output:
        checker.generate_report(args.output)
    else:
        print("\n" + checker.generate_report())