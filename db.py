"""Oracle access layer.

Uses python-oracledb in *thin* mode by default, so no Oracle Instant
Client installation is required on the server host.
"""

from __future__ import annotations

import datetime as _dt
import decimal
import logging
import time
from typing import Any

import oracledb

from config import Config

# my project logger name
log = logging.getLogger("db")

_pool: oracledb.ConnectionPool | None = None
_cfg: Config | None = None


def init(cfg: Config) -> None:
    global _pool, _cfg
    _cfg = cfg

    if cfg.wallet_dir:
        #thick mode- Oracle Wallet
        oracledb.init_oracle_client(config_dir=cfg.wallet_dir)
        log.info("Oracle client initialised in thick mode (%s)", cfg.wallet_dir)

    _pool = oracledb.create_pool(
        user=cfg.user,
        password=cfg.password,
        dsn=cfg.dsn,
        min=0,
        #min=cfg.pool_min,
        max=cfg.pool_max,
        increment=1,
        timeout=cfg.pool_timeout,
        getmode=oracledb.POOL_GETMODE_WAIT,
    )
    log.info("Connection pool up: %s@%s", cfg.user, cfg.dsn)


def close() -> None:
    if _pool is not None:
        _pool.close(force=True)


def _acquire() -> oracledb.Connection:
    if _pool is None:
        raise RuntimeError("Database pool not initialised. Call db.init(cfg) first.")
    conn = _pool.acquire()
    conn.call_timeout = (_cfg.statement_timeout_s if _cfg else 60) * 1000
    return conn


def _jsonable(value: Any) -> Any:
    """Convert Oracle types into something JSON can carry without surprises."""
    if value is None:
        return None
    if isinstance(value, decimal.Decimal):
        f = float(value)
        return int(f) if f.is_integer() else f
    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()
    if isinstance(value, oracledb.LOB):
        return value.read()
    if isinstance(value, bytes):
        return value.hex()
    return value


def fetch(sql: str, binds: dict[str, Any] | None = None) -> tuple[list[str], list[list[Any]], float]:
    """Run a SELECT and return (columns, rows, elapsed_ms)."""
    started = time.perf_counter()
    with _acquire() as conn:
        with conn.cursor() as cur:
            # Belt and braces: session itself enforces read-only
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(sql, binds or {})
            cols = [d[0] for d in cur.description]
            rows = [[_jsonable(v) for v in row] for row in cur]
        conn.rollback()  # ends the read-only transaction cleanly
    return cols, rows, (time.perf_counter() - started) * 1000


def describe(view_name: str) -> list[dict[str, Any]]:
    """Column metadata for one view, from the data dictionary."""
    sql = """
        SELECT column_name, data_type, data_length, data_precision,
               data_scale, nullable, column_id
        FROM   all_tab_columns
        WHERE  UPPER(table_name) = :vname
        ORDER  BY column_id
    """
    cols, rows, _ = fetch(sql, {"vname": view_name.split(".")[-1].upper()})
    return [dict(zip(cols, r)) for r in rows]


def audit(
    tool_name: str,
    statement: str,
    row_count: int | None,
    truncated: bool,
    elapsed_ms: float,
    outcome: str,
    error: str | None = None,
) -> None:
    """Write one line to the query log. Never raises into the caller."""
    if not _cfg or not _cfg.audit_enabled:
        return
    sql = f"""
        INSERT INTO {_cfg.audit_table}
            (client_id, tool_name, statement_txt, row_count,
             truncated_flag, elapsed_ms, outcome, error_txt)
        VALUES (:client_id, :tool_name, :stmt, :b_row_cnt,
                :trunc, :ms, :outcome, :err)
    """
    try:
        with _acquire() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    {
                        "client_id": _cfg.client_id,
                        "tool_name": tool_name[:60],
                        "stmt": statement,
                        "rows": row_count,
                        "trunc": "Y" if truncated else "N",
                        "ms": round(elapsed_ms),
                        "outcome": outcome[:20],
                        "err": (error or "")[:2000] or None,
                    },
                )
            conn.commit()
    except Exception as exc:  # audit must never break the query path
        log.warning("Audit write failed (%s): %s", outcome, exc)


def ping() -> str:
    """Connectivity check used by the preflight script."""
    _, rows, _ = fetch("SELECT 'ok' AS status FROM dual")
    return str(rows[0][0]) if rows else "no-response"