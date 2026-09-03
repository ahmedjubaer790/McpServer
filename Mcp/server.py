"""SmartStore AI Reporting Layer - MCP server."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any


#path load and direct import
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from mcp.server.fastmcp import FastMCP


import catalog
import db
from config import Config, load_config
from guard import QueryRejected, validate, wrap_with_limit

# Logging to stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("app.server")

# FastMCP Initialization
mcp = FastMCP(
    "smartstore-reporting",
    instructions=(
        "Read-only reporting access to the SmartStore Oracle database "
        "through authorized semantic reporting views (V_SMART_*).\n\n"
        "ALWAYS call get_schema_notes before writing your first query in a "
        "conversation - it carries the grain of each view and operational traps "
        "that prevent incorrect aggregates.\n\n"
        "Write standard Oracle SELECT statements against the authorized views. "
        "Aggregate in SQL rather than fetching detail rows and calculating totals yourself. "
        "All monetary values are in Bangladeshi Taka (BDT).\n\n"
        "If a result comes back with truncated=true, your query was too broad - "
        "add a GROUP BY or a date filter and run it again. Never report a "
        "truncated result as a total."
    ),
)

_cfg: Config | None = None


# ---------------------------------------------------------------- tools
@mcp.tool()
def get_schema_notes() -> str:
    """What each reporting view means, how departments cross-check each
    other, and which business assumptions apply. Read this first."""
    return catalog.overview()


@mcp.tool()
def list_views() -> str:
    """List the available reporting views, with column counts and a one-line
    description of what one row represents."""
    assert _cfg is not None
    out: list[dict[str, Any]] = []
    for name in sorted(_cfg.allowed_upper):
        if "." in name:
            continue
        meta = catalog.VIEWS.get(name, {})
        try:
            cols = db.describe(name)
            n_cols = len(cols)
        except Exception as exc:
            out.append({"view": name, "error": str(exc)[:200]})
            continue
        out.append(
            {
                "view": name,
                "columns": n_cols,
                "grain": meta.get("grain", "not documented"),
                "use": meta.get("use", ""),
            }
        )
    return json.dumps(out, indent=2)


@mcp.tool()
def describe_view(view_name: str) -> str:
    """Column names, datatypes and nullability for one reporting view.

    Args:
        view_name: e.g. "V_SMART_CASH_VARIANCE"
    """
    assert _cfg is not None
    name = view_name.strip().upper()
    if name not in _cfg.allowed_upper:
        return json.dumps(
            {
                "error": f"{name} is not in the reporting layer.",
                "available": sorted(n for n in _cfg.allowed_upper if "." not in n),
            },
            indent=2,
        )
    cols = db.describe(name)
    meta = catalog.VIEWS.get(name, {})
    db.audit("describe_view", name, len(cols), False, 0.0, "OK")
    return json.dumps(
        {
            "view": name,
            "grain": meta.get("grain", ""),
            "use": meta.get("use", ""),
            "trap": meta.get("trap", ""),
            "columns": cols,
        },
        indent=2,
        default=str,
    )


@mcp.tool()
def run_query(sql: str) -> str:
    """Run one read-only Oracle SELECT against the reporting views.

    Only SELECT and WITH statements are accepted, and only against the
    authorized reporting views (e.g. V_SMART_*). Aggregate in SQL - the result set is capped.

    Args:
        sql: a single Oracle SELECT statement, no trailing semicolon
    """
    assert _cfg is not None

    # 1. Validate before the database ever sees it.
    try:
        checked = validate(sql, _cfg.allowed_upper)
    except QueryRejected as exc:
        db.audit("run_query", sql[:4000], None, False, 0.0, "BLOCKED", str(exc))
        log.warning("BLOCKED: %s", exc)
        return json.dumps({"error": str(exc), "blocked": True}, indent=2)

    # 2. Execute with a hard row cap.
    capped = wrap_with_limit(checked.sql, _cfg.max_rows)
    try:
        cols, rows, elapsed = db.fetch(capped)
    except Exception as exc:
        db.audit("run_query", checked.sql[:4000], None, False, 0.0, "ERROR", str(exc))
        log.error("Query failed: %s", exc)
        return json.dumps(
            {
                "error": f"Oracle returned: {exc}",
                "hint": "Check column names with describe_view before retrying.",
            },
            indent=2,
        )

    truncated = len(rows) > _cfg.max_rows
    if truncated:
        rows = rows[: _cfg.max_rows]

    db.audit("run_query", checked.sql[:4000], len(rows), truncated, elapsed, "OK")

    payload: dict[str, Any] = {
        "columns": cols,
        "row_count": len(rows),
        "truncated": truncated,
        "elapsed_ms": round(elapsed),
        "views_read": checked.objects,
        "rows": rows,
    }
    if truncated:
        payload["warning"] = (
            f"Result capped at {_cfg.max_rows} rows. This is a PARTIAL result - "
            "do not report it as a total. Add a GROUP BY or narrow the date range."
        )
    return json.dumps(payload, indent=2, default=str)


# ---------------------------------------------------------------- entry
def main(argv: list[str] | None = None) -> int:
    global _cfg

    ap = argparse.ArgumentParser(description="SmartStore Reporting Layer MCP server")
    ap.add_argument("--config", help="path to config.yaml")
    ap.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="stdio for Claude Desktop / Cursor; http for a remote connector",
    )
    args = ap.parse_args(argv)

    _cfg = load_config(args.config)
    db.init(_cfg)

    try:
        db.ping()
        log.info("Database reachable. %d views whitelisted.", len(_cfg.allowed_views))
    except Exception as exc:
        log.error("Cannot reach the database: %s", exc)
        return 2

    try:
        if args.transport == "http":
            mcp.settings.host = _cfg.http_host
            mcp.settings.port = _cfg.http_port
            log.info("Serving on http://%s:%d/mcp", _cfg.http_host, _cfg.http_port)
            mcp.run(transport="streamable-http")
        else:
            mcp.run(transport="stdio")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# """SmartStore AI Reporting Layer - MCP server.

# Four tools, no more:
#     get_schema_notes  what the views mean, the traps, the open assumptions
#     list_views        the reporting views available, with column & grain info
#     describe_view     column metadata for one specific view
#     run_query         one read-only SELECT, capped and logged

# Run:
#     python -m app.server                  # stdio  (Claude Desktop / Cursor)
#     python -m app.server --transport http # streamable HTTP (remote connector)
# """

# from __future__ import annotations

# import argparse
# import json
# import logging
# import sys
# from typing import Any

# from mcp.server.fastmcp import FastMCP

# from . import catalog, db
# from .config import Config, load_config
# from .guard import QueryRejected, validate, wrap_with_limit

# # Logging to stderr (stdout is reserved for the MCP JSON-RPC protocol)
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
#     stream=sys.stderr,
# )
# log = logging.getLogger("app.server")

# # FastMCP Initialization with customized system instructions for Claude
# mcp = FastMCP(
#     "smartstore-reporting",
#     instructions=(
#         "Read-only reporting access to the SmartStore Oracle database "
#         "through authorized semantic reporting views (V_SMART_*).\n\n"
#         "ALWAYS call get_schema_notes before writing your first query in a "
#         "conversation - it carries the grain of each view and operational traps "
#         "that prevent incorrect aggregates.\n\n"
#         "Write standard Oracle SELECT statements against the authorized views. "
#         "Aggregate in SQL rather than fetching detail rows and calculating totals yourself. "
#         "All monetary values are in Bangladeshi Taka (BDT).\n\n"
#         "If a result comes back with truncated=true, your query was too broad - "
#         "add a GROUP BY or a date filter and run it again. Never report a "
#         "truncated result as a total."
#     ),
# )

# _cfg: Config | None = None


# # ---------------------------------------------------------------- tools
# @mcp.tool()
# def get_schema_notes() -> str:
#     """What each reporting view means, how departments cross-check each
#     other, and which business assumptions apply. Read this first."""
#     return catalog.overview()


# @mcp.tool()
# def list_views() -> str:
#     """List the available reporting views, with column counts and a one-line
#     description of what one row represents."""
#     assert _cfg is not None
#     out: list[dict[str, Any]] = []
#     for name in sorted(_cfg.allowed_upper):
#         if "." in name:
#             continue
#         meta = catalog.VIEWS.get(name, {})
#         try:
#             cols = db.describe(name)
#             n_cols = len(cols)
#         except Exception as exc:
#             out.append({"view": name, "error": str(exc)[:200]})
#             continue
#         out.append(
#             {
#                 "view": name,
#                 "columns": n_cols,
#                 "grain": meta.get("grain", "not documented"),
#                 "use": meta.get("use", ""),
#             }
#         )
#     return json.dumps(out, indent=2)


# @mcp.tool()
# def describe_view(view_name: str) -> str:
#     """Column names, datatypes and nullability for one reporting view.

#     Args:
#         view_name: e.g. "V_SMART_CASH_VARIANCE"
#     """
#     assert _cfg is not None
#     name = view_name.strip().upper()
#     if name not in _cfg.allowed_upper:
#         return json.dumps(
#             {
#                 "error": f"{name} is not in the reporting layer.",
#                 "available": sorted(n for n in _cfg.allowed_upper if "." not in n),
#             },
#             indent=2,
#         )
#     cols = db.describe(name)
#     meta = catalog.VIEWS.get(name, {})
#     db.audit("describe_view", name, len(cols), False, 0.0, "OK")
#     return json.dumps(
#         {
#             "view": name,
#             "grain": meta.get("grain", ""),
#             "use": meta.get("use", ""),
#             "trap": meta.get("trap", ""),
#             "columns": cols,
#         },
#         indent=2,
#         default=str,
#     )


# @mcp.tool()
# def run_query(sql: str) -> str:
#     """Run one read-only Oracle SELECT against the reporting views.

#     Only SELECT and WITH statements are accepted, and only against the
#     authorized reporting views (e.g. V_SMART_*). Aggregate in SQL - the result set is capped.

#     Args:
#         sql: a single Oracle SELECT statement, no trailing semicolon
#     """
#     assert _cfg is not None

#     # 1. Validate before the database ever sees it.
#     try:
#         checked = validate(sql, _cfg.allowed_upper)
#     except QueryRejected as exc:
#         db.audit("run_query", sql[:4000], None, False, 0.0, "BLOCKED", str(exc))
#         log.warning("BLOCKED: %s", exc)
#         return json.dumps({"error": str(exc), "blocked": True}, indent=2)

#     # 2. Execute with a hard row cap.
#     capped = wrap_with_limit(checked.sql, _cfg.max_rows)
#     try:
#         cols, rows, elapsed = db.fetch(capped)
#     except Exception as exc:
#         db.audit("run_query", checked.sql[:4000], None, False, 0.0, "ERROR", str(exc))
#         log.error("Query failed: %s", exc)
#         return json.dumps(
#             {
#                 "error": f"Oracle returned: {exc}",
#                 "hint": "Check column names with describe_view before retrying.",
#             },
#             indent=2,
#         )

#     truncated = len(rows) > _cfg.max_rows
#     if truncated:
#         rows = rows[: _cfg.max_rows]

#     db.audit("run_query", checked.sql[:4000], len(rows), truncated, elapsed, "OK")

#     payload: dict[str, Any] = {
#         "columns": cols,
#         "row_count": len(rows),
#         "truncated": truncated,
#         "elapsed_ms": round(elapsed),
#         "views_read": checked.objects,
#         "rows": rows,
#     }
#     if truncated:
#         payload["warning"] = (
#             f"Result capped at {_cfg.max_rows} rows. This is a PARTIAL result - "
#             "do not report it as a total. Add a GROUP BY or narrow the date range."
#         )
#     return json.dumps(payload, indent=2, default=str)


# # ---------------------------------------------------------------- entry
# def main(argv: list[str] | None = None) -> int:
#     global _cfg

#     ap = argparse.ArgumentParser(description="SmartStore Reporting Layer MCP server")
#     ap.add_argument("--config", help="path to config.yaml")
#     ap.add_argument(
#         "--transport",
#         choices=["stdio", "http"],
#         default="stdio",
#         help="stdio for Claude Desktop / Cursor; http for a remote connector",
#     )
#     args = ap.parse_args(argv)

#     _cfg = load_config(args.config)
#     db.init(_cfg)

#     try:
#         db.ping()
#         log.info("Database reachable. %d views whitelisted.", len(_cfg.allowed_views))
#     except Exception as exc:
#         log.error("Cannot reach the database: %s", exc)
#         return 2

#     try:
#         if args.transport == "http":
#             mcp.settings.host = _cfg.http_host
#             mcp.settings.port = _cfg.http_port
#             log.info("Serving on http://%s:%d/mcp", _cfg.http_host, _cfg.http_port)
#             mcp.run(transport="streamable-http")
#         else:
#             mcp.run(transport="stdio")
#     finally:
#         db.close()
#     return 0


# if __name__ == "__main__":
#     raise SystemExit(main())