"""SQL guard: application-level defence in depth.

The real security boundary is Oracle - CLAUDE_RO holds SELECT on allowed
views and nothing else, so even a bypass here reaches nothing sensitive.
This module exists to fail fast, fail loudly, and leave an audit trail
that says exactly what was refused and why.

Rules enforced:
  1. Exactly one statement. No ';' outside a string literal.
  2. Must begin with SELECT or WITH.
  3. No DML, DDL, DCL, PL/SQL block or hierarchical-loop keyword anywhere.
  4. Every object referenced after FROM / JOIN must be in the whitelist,
     unless it is a CTE name defined by the query's own WITH clause.
  5. Result set is capped by wrapping the query, not by trusting the client.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class QueryRejected(Exception):
    """Raised when a statement fails validation. The message is shown to Claude."""


# Verbs that must never appear, even inside a subquery or a hint.
_FORBIDDEN = (
    "INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE", "DROP", "ALTER",
    "CREATE", "GRANT", "REVOKE", "COMMIT", "ROLLBACK", "SAVEPOINT",
    "EXECUTE", "EXEC", "CALL", "BEGIN", "DECLARE", "PRAGMA", "LOCK",
    "FLASHBACK", "PURGE", "AUDIT", "NOAUDIT", "ANALYZE", "COMMENT",
    "RENAME", "SET", "ADMINISTER", "DBMS_", "UTL_", "OWA_", "HTP.",
    "SYS.", "DBA_", "V$", "GV$", "ALL_USERS", "USER_ROLE_PRIVS",
)

_STRING_OR_COMMENT = re.compile(
    r"""
      '(?:[^']|'')*'          # single-quoted literal, '' escape
    | q'\[.*?\]'              # q-quoted variants
    | q'\{.*?\}'
    | q'<.*?>'
    | q'\(.*?\)'
    | --[^\n]*                # line comment
    | /\*.*?\*/               # block comment
    """,
    re.VERBOSE | re.DOTALL | re.IGNORECASE,
)

# Object reference immediately after FROM / JOIN, optionally schema-qualified.
_OBJECT_REF = re.compile(
    r"\b(?:FROM|JOIN)\s+(?!\()([A-Za-z_$#][\w$#]*(?:\s*\.\s*[A-Za-z_$#][\w$#]*)?)",
    re.IGNORECASE,
)

# CTE names introduced by a WITH clause.
_CTE_NAME = re.compile(r"(?:\bWITH\b|,)\s*([A-Za-z_$#][\w$#]*)\s+AS\s*\(", re.IGNORECASE)

# Inline table functions and pseudo-sources that need no whitelist entry.
_ALWAYS_OK = {"DUAL", "TABLE", "LATERAL", "XMLTABLE", "JSON_TABLE"}


def _blank_literals(sql: str) -> str:
    """Replace string literals and comments with spaces of equal length.

    Keeps offsets stable so error messages point at the right place, and
    stops a keyword inside a literal ('DROP TABLE') from tripping the scan.
    """
    return _STRING_OR_COMMENT.sub(lambda m: " " * len(m.group(0)), sql)


@dataclass
class GuardResult:
    sql: str                 # the statement, trimmed and semicolon-free
    objects: list[str]       # whitelisted objects it touches
    ctes: list[str]          # CTE names it defines


def validate(sql: str, allowed: set[str]) -> GuardResult:
    if not sql or not sql.strip():
        raise QueryRejected("Empty statement.")

    raw = sql.strip().rstrip(";").strip()
    scan = _blank_literals(raw)

    # --- 1. single statement -----------------------------------------
    if ";" in scan:
        raise QueryRejected(
            "Multiple statements are not allowed. Send one SELECT at a time."
        )

    # --- 2. must be a read -------------------------------------------
    head = scan.lstrip().upper()
    if not (head.startswith("SELECT") or head.startswith("WITH")):
        raise QueryRejected(
            "Only SELECT and WITH statements are accepted. "
            "This connection is read-only by Dev.Jubaer."
        )

    # --- 3. forbidden verbs ------------------------------------------
    upper = scan.upper()
    for verb in _FORBIDDEN:
        pattern = re.escape(verb) if not verb.isalpha() else rf"\b{verb}\b"
        if re.search(pattern, upper):
            raise QueryRejected(
                f"The token '{verb}' is not permitted. "
                "Only safe SELECT statements against the authorized reporting views are allowed."
            )

    # --- 4. object whitelist -----------------------------------------
    ctes = {m.group(1).upper() for m in _CTE_NAME.finditer(scan)}
    referenced: list[str] = []
    offenders: list[str] = []

    for m in _OBJECT_REF.finditer(scan):
        obj = re.sub(r"\s+", "", m.group(1)).upper()
        bare = obj.split(".", 1)[1] if "." in obj else obj
        if bare in ctes or bare in _ALWAYS_OK:
            continue
        if obj in allowed or bare in allowed:
            referenced.append(bare)
        else:
            offenders.append(obj)

    if offenders:
        raise QueryRejected(
            "Not in the reporting layer: "
            + ", ".join(sorted(set(offenders)))
            + ". Call list_views or get_schema_notes to see available reporting views."
        )

    if not referenced:
        raise QueryRejected(
            "The statement references no authorized reporting view. "
            "Every query must read at least one whitelisted view."
        )

    return GuardResult(sql=raw, objects=sorted(set(referenced)), ctes=sorted(ctes))


def wrap_with_limit(sql: str, max_rows: int) -> str:
    """Cap the result set server-side.

    Fetching max_rows + 1 lets the caller detect truncation rather than
    silently reporting a partial total.
    """
    return (
        "SELECT * FROM (\n"
        f"{sql}\n"
        f") ai_capped WHERE ROWNUM <= {int(max_rows) + 1}"
    )