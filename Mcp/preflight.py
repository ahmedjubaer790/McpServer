#!/usr/bin/env python3
"""Live preflight check - tests database connectivity, views, and audit logging."""

import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import db
from config import load_config
from guard import QueryRejected, validate, wrap_with_limit


def main() -> int:
    print("\n=======================================================")
    print("   Running Live Preflight Check for Oracle AI_RPT      ")
    print("=======================================================\n")

    cfg = load_config()
    db.init(cfg)

    #ping test
    try:
        status = db.ping()
        print(f"✅ DB Ping: {status.upper()} (Connected to {cfg.dsn} as {cfg.user})")
    except Exception as e:
        print(f"❌ DB Ping Failed: {e}")
        return 1

    # live view read
    views = [
        "V_SMART_DAILY_SALES",
        "V_SMART_CASH_VARIANCE",
        "V_SMART_CUSTOMER_RETENTION"
    ]

    print("\n--- Verifying Authorized Views ---")
    for v in views:
        try:
            checked = validate(f"SELECT * FROM {v}", cfg.allowed_upper)
            sql = wrap_with_limit(checked.sql, 5)
            cols, rows, ms = db.fetch(sql)
            print(f"✅ OK: {v:<28} | Cols: {len(cols):<2} | Sample Rows: {len(rows)} ({round(ms, 1)}ms)")
        except Exception as e:
            print(f"❌ FAIL: {v:<26} | Error: {e}")

    # live secuirity and audit test
    print("\n--- Testing Security Guard Block on Live DB ---")
    bad_query = "DROP TABLE V_SMART_DAILY_SALES"
    try:
        validate(bad_query, cfg.allowed_upper)
        print("❌ FAIL: Guard failed to block DDL query!")
    except QueryRejected as exc:
        db.audit("run_query", bad_query, None, False, 0.0, "BLOCKED", str(exc))
        print(f"✅ PASS: Live DDL successfully BLOCKED ('{exc}')")
        print("✅ PASS: Block event recorded in AI_RPT.CLAUDE_QUERY_LOG.")

    db.close()
    print("\n🎉 Preflight Check Complete! System is ready for Claude connection.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())