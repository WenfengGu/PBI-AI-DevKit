# -*- coding: utf-8 -*-
"""
Smoke Test — Remote Power BI Connection
========================================
Quick connectivity check for target SalesAndCrm model.
Run this FIRST before any data quality or analysis scripts.
Should complete in <30 seconds.

Usage:
    python smoke_test.py
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── Credentials ────────────────────────────────────────────────
# Same pattern as test_remote_rest.py: hardcode for reliability
os.environ["PBI_USERNAME"] = "fendi.powerbi@lvmhfashion.partner.onsmchina.cn"
os.environ["PBI_PASSWORD"] = "***"
os.environ["PBI_XMLA_SERVER"] = "powerbi://api.powerbi.cn/v1.0/myorg/FEN-D-ATOM%20%20CN"
os.environ.setdefault("PBI_XMLA_DATABASE", "SalesAndCrm - target_China")

from ssas_client import RemotePowerBI

SERVER = "powerbi://api.powerbi.cn/v1.0/myorg/FEN-D-ATOM%20%20CN"
DATABASE = "SalesAndCrm - target_China"

def main():
    total_start = time.time()
    passed = 0
    failed = 0

    print("=" * 60)
    print("SMOKE TEST — Remote Power BI Connection")
    print("=" * 60)

    # ── Test 1: Token Acquisition ──────────────────────────────
    print("\n[1] Token Acquisition...", end=" ", flush=True)
    try:
        client = RemotePowerBI(server=SERVER, database=DATABASE)
        token_preview = client.token[:20]
        print("OK (%s...)" % token_preview)
        passed += 1
    except Exception as e:
        print("FAILED: %s" % str(e)[:80])
        failed += 1
        print("\nABORT: Cannot proceed without token.")
        return 1

    # ── Test 2: Workspace Discovery ────────────────────────────
    print("[2] Workspace Discovery...", end=" ", flush=True)
    try:
        ws = client.list_workspaces()
        fendi_ws = [w for w in ws if "FEN" in w["name"]]
        print("OK (%d workspaces, %d target)" % (len(ws), len(fendi_ws)))
        passed += 1
    except Exception as e:
        print("FAILED: %s" % str(e)[:80])
        failed += 1

    # ── Test 3: Dataset Resolution ─────────────────────────────
    print("[3] Dataset Resolution...", end=" ", flush=True)
    try:
        client._ensure_resolved()
        ds = client.list_datasets()
        assert client._ds_id, "Dataset ID not resolved"
        print("OK (ws=%s, ds=%s, %d datasets)" % (
            client._ws_id[:8], client._ds_id[:8], len(ds)))
        passed += 1
    except Exception as e:
        print("FAILED: %s" % str(e)[:80])
        failed += 1

    # ── Test 4: Basic DAX ──────────────────────────────────────
    print("[4] Basic DAX Query...", end=" ", flush=True)
    try:
        rows = client.execute_dax("EVALUATE ROW(\"Test\", 1+1)")
        assert rows, "No rows returned"
        val = client.row_val(rows[0], "Test")
        assert val == 2, "Expected 2, got %s" % val
        print("OK (1+1=%s)" % val)
        passed += 1
    except Exception as e:
        print("FAILED: %s" % str(e)[:80])
        failed += 1

    # ── Test 5: Business DAX ───────────────────────────────────
    print("[5] Business DAX Query...", end=" ", flush=True)
    try:
        rows = client.execute_dax(
            "EVALUATE ROW(\"Rows\", COUNTROWS('Sales Reservation Details'), "
            "\"Customers\", DISTINCTCOUNT('Sales Reservation Details'[CUST_KEY]))")
        assert rows, "No rows returned"
        total = client.row_val(rows[0], "Rows", 0)
        custs = client.row_val(rows[0], "Customers", 0)
        print("OK (%s rows, %s customers)" % (total, custs))
        passed += 1
    except Exception as e:
        print("FAILED: %s" % str(e)[:80])
        failed += 1

    # ── Test 6: Date Freshness ─────────────────────────────────
    print("[6] Date Freshness...", end=" ", flush=True)
    try:
        rows = client.execute_dax(
            "EVALUATE ROW(\"MaxDate\", MAX('Sales Reservation Details'[Sales Order Date]))")
        max_date = client.row_val(rows[0], "MaxDate", "N/A")
        print("OK (latest: %s)" % max_date)
        passed += 1
    except Exception as e:
        print("FAILED: %s" % str(e)[:80])
        failed += 1

    # ── Summary ────────────────────────────────────────────────
    elapsed = time.time() - total_start
    print("\n" + "=" * 60)
    print("RESULT: %d/%d passed in %.1fs" % (passed, passed + failed, elapsed))
    if failed:
        print("STATUS: FAILURE — %d test(s) failed" % failed)
    else:
        print("STATUS: ALL PASS — connection healthy")
    print("=" * 60)

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())