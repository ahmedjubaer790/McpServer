#!/usr/bin/env python3
"""Offline self-test - exercises the whole server with a fake database.

    python selftest.py

Proves the guard, the row cap, the truncation flag, the audit path and
the four tools all behave, without needing Oracle. Run this on any laptop
before connecting to live database.
"""

from __future__ import annotations

import json
import os
import sys

# Import handling: supports running directly or from the tests/ folder
try:
    import catalog, db, server
    from config import Config
except ImportError:
    # If files are inside 'app' package
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from Mcp import catalog, db, server
    from config import Config

# Mock data matching V_SMART_CASH_VARIANCE
FAKE_ROWS = [
    ["SmartStore Gulshan",    "2026-08-24", 50000, 53500,  3500, "EXCESS_HIGH"],
    ["SmartStore Banani",     "2026-08-24", 40000, 40000,     0, "BALANCED"],
    ["SmartStore Agrabad",    "2026-08-24", 35000, 32000, -3000, "SHORT_HIGH"],
]
FAKE_COLS = ["OUTLET_NAME", "RECON_DATE", "SYSTEM_BALANCE", "DRAWER_BALANCE", "CASH_VARIANCE", "STATUS_FLAG"]

audit_lines: list[tuple] = []
ok = fail = 0


def tool(name: str):
    """Return the plain callable behind an @mcp.tool()."""
    obj = getattr(server, name)
    return getattr(obj, "fn", obj)


def expect(label: str, condition: bool, detail: str = "") -> None:
    global ok, fail
    if condition:
        ok += 1
        print(f"  PASS  {label}")
    else:
        fail += 1
        print(f"  FAIL  {label}   {detail}")


def install_fakes(max_rows: int = 10_000, row_multiplier: int = 1) -> Config:
    cfg = Config(
        user="claude_ro",
        password="x",
        dsn="fake:1521/FAKE",
        allowed_views=list(catalog.VIEWS.keys()),
        max_rows=max_rows,
        client_id="selftest",
    )
    server._cfg = cfg

    def fake_fetch(sql, binds=None):
        return FAKE_COLS, FAKE_ROWS * row_multiplier, 12.5

    def fake_describe(view_name):
        return [
            {"COLUMN_NAME": c, "DATA_TYPE": "VARCHAR2", "NULLABLE": "Y", "COLUMN_ID": i + 1}
            for i, c in enumerate(FAKE_COLS)
        ]

    def fake_audit(*args, **kwargs):
        audit_lines.append(args)

    db.fetch, db.describe, db.audit = fake_fetch, fake_describe, fake_audit
    return cfg


def main() -> int:
    print("\nSmartStore AI Reporting Layer - offline self-test\n")
    install_fakes()

    print(" Tool: get_schema_notes")
    notes = tool("get_schema_notes")()
    expect("returns the briefing", "V_SMART_CASH_VARIANCE" in notes)
    expect("carries the open assumptions", "A1:" in notes or "OUTLET_NAME" in notes)
    expect("names the currency", "BDT" in notes)

    print("\n Tool: list_views")
    listed = json.loads(tool("list_views")())
    expect("three views listed", len(listed) == 3, f"got {len(listed)}")
    expect("every entry states its grain", all(e.get("grain") for e in listed))

    print("\n Tool: describe_view")
    desc = json.loads(tool("describe_view")("V_SMART_CASH_VARIANCE"))
    expect("returns columns", len(desc["columns"]) == len(FAKE_COLS))
    expect("returns the trap note", "drawer_balance" in desc["trap"].lower() or "SHORT_HIGH" in desc["trap"])
    refused = json.loads(tool("describe_view")("HRM_EMPLOYEES"))
    expect("refuses a non-whitelisted view", "error" in refused)

    print("\n Tool: run_query - happy path")
    res = json.loads(tool("run_query")(
        "SELECT outlet_name, recon_date, system_balance, drawer_balance, cash_variance, status_flag "
        "FROM v_smart_cash_variance WHERE recon_date = DATE '2026-08-24'"
    ))
    expect("rows returned", res["row_count"] == 3, str(res.get("row_count")))
    expect("not truncated", res["truncated"] is False)
    expect("reports which views were read",
           res["views_read"] == ["V_SMART_CASH_VARIANCE"], str(res.get("views_read")))
    expect("audit row written", any(a[0] == "run_query" for a in audit_lines))

    print("\n Tool: run_query - refusals")
    for label, stmt in [
        ("DDL",                 "DROP TABLE smart_transactions"),
        ("DML",                 "DELETE FROM v_smart_daily_sales"),
        ("chained statements",  "SELECT 1 FROM v_smart_daily_sales; DROP TABLE x"),
        ("PII table",           "SELECT nid_number FROM customers"),
        ("student data",        "SELECT * FROM elc_student_info"),
        ("dictionary probe",    "SELECT * FROM all_tab_privs"),
        ("no view referenced",  "SELECT 1 FROM dual"),
    ]:
        out = json.loads(tool("run_query")(stmt))
        expect(f"blocks {label}", out.get("blocked") is True, str(out)[:90])

    print("\n Tool: run_query - truncation guard")
    install_fakes(max_rows=5, row_multiplier=4)      # 12 fake rows, cap 5
    res = json.loads(tool("run_query")("SELECT * FROM v_smart_daily_sales"))
    expect("capped to max_rows", res["row_count"] == 5, str(res["row_count"]))
    expect("truncated flag set", res["truncated"] is True)
    expect("carries a do-not-total warning", "PARTIAL" in res.get("warning", ""))

    print(f"\n {ok} passed, {fail} failed\n")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())