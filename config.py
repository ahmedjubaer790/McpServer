"""Configuration loading for the AI Reporting MCP server."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import yaml

# config.py config.yaml load
CURRENT_DIR = Path(__file__).resolve().parent
load_dotenv(CURRENT_DIR / ".env")

DEFAULT_CONFIG_PATH = CURRENT_DIR / "config.yaml"


@dataclass
class Config:
    user: str
    password: str
    dsn: str
    wallet_dir: str | None = None

    pool_min: int = 1
    pool_max: int = 4
    pool_timeout: int = 60

    allowed_views: list[str] = field(default_factory=list)
    max_rows: int = 10_000
    statement_timeout_s: int = 60
    client_id: str = "claude-desktop-local"

    audit_enabled: bool = True
    audit_table: str = "ai_rpt.claude_query_log"

    http_host: str = "127.0.0.1"
    http_port: int = 8765

    @property
    def allowed_upper(self) -> set[str]:
        names: set[str] = set()
        for raw in self.allowed_views:
            v = raw.strip().upper()
            names.add(v)
            if "." in v:
                names.add(v.split(".", 1)[1])
        return names


def _env(key: str, default: Any = None) -> Any:
    return os.environ.get(f"AI_MCP_{key.upper()}", default)


def load_config(path: Path | str | None = None) -> Config:
    config_file = Path(path or DEFAULT_CONFIG_PATH)
    data: dict[str, Any] = {}
    
    if config_file.exists():
        data = yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}

    oracle = data.get("oracle", {}) or {}
    guard = data.get("guard", {}) or {}
    audit = data.get("audit", {}) or {}
    http = data.get("http", {}) or {}

    user = _env("user", oracle.get("user", "claude_ro"))
    password = _env("password", oracle.get("password"))
    dsn = _env("dsn", oracle.get("dsn"))

    if not password:
        raise SystemExit(
            f"No database password found in {config_file}. Set AI_MCP_PASSWORD in .env or oracle.password in config.yaml."
        )
    if not dsn:
        raise SystemExit(
            "No DSN found. Set AI_MCP_DSN or oracle.dsn in config.yaml."
        )

    views = guard.get("allowed_views") or []
    if not views:
        raise SystemExit("guard.allowed_views is empty in config.yaml - refusing to start.")

    return Config(
        user=user,
        password=password,
        dsn=dsn,
        wallet_dir=_env("wallet_dir", oracle.get("wallet_dir")),
        pool_min=int(oracle.get("pool_min", 1)),
        pool_max=int(oracle.get("pool_max", 4)),
        pool_timeout=int(oracle.get("pool_timeout", 60)),
        allowed_views=list(views),
        max_rows=int(_env("max_rows", guard.get("max_rows", 10_000))),
        statement_timeout_s=int(guard.get("statement_timeout_s", 60)),
        client_id=str(_env("client_id", guard.get("client_id", "claude-desktop-local"))),
        audit_enabled=bool(audit.get("enabled", True)),
        audit_table=str(audit.get("table", "ai_rpt.claude_query_log")),
        http_host=str(_env("http_host", http.get("host", "127.0.0.1"))),
        http_port=int(_env("http_port", http.get("port", 8765))),
    )

# """Configuration loading for the AI Reporting MCP server.

# Precedence: environment variables override config.yaml.
# Secrets belong in the environment (.env), never in the YAML file.
# """

# from __future__ import annotations

# import os
# from dataclasses import dataclass, field
# from pathlib import Path
# from typing import Any

# import yaml

# # ডিফল্ট কনফিগ ফাইল পাথ
# DEFAULT_CONFIG_PATH = Path(
#     os.environ.get("AI_MCP_CONFIG", Path(__file__).resolve().parents[1] / "config.yaml")
# )


# @dataclass
# class Config:
#     # --- Oracle connection -------------------------------------------
#     user: str
#     password: str
#     dsn: str
#     wallet_dir: str | None = None

#     # --- Pool --------------------------------------------------------
#     pool_min: int = 1
#     pool_max: int = 4
#     pool_timeout: int = 60

#     # --- Guard rails -------------------------------------------------
#     allowed_views: list[str] = field(default_factory=list)
#     max_rows: int = 10_000
#     statement_timeout_s: int = 60
#     client_id: str = "claude-mcp"

#     # --- Audit (পরিবর্তন: AI_RPT স্কিমা) -----------------------------
#     audit_enabled: bool = True
#     audit_table: str = "ai_rpt.claude_query_log"

#     # --- Transport ---------------------------------------------------
#     http_host: str = "127.0.0.1"
#     http_port: int = 8765

#     @property
#     def allowed_upper(self) -> set[str]:
#         """Allowed view names, uppercased, with and without schema prefix."""
#         names: set[str] = set()
#         for raw in self.allowed_views:
#             v = raw.strip().upper()
#             names.add(v)
#             if "." in v:
#                 names.add(v.split(".", 1)[1])
#         return names


# def _env(key: str, default: Any = None) -> Any:
#     # পরিবর্তন: AI_MCP_ প্রিফিক্স ব্যবহার করা হয়েছে
#     return os.environ.get(f"AI_MCP_{key.upper()}", default)


# def load_config(path: Path | str | None = None) -> Config:
#     path = Path(path or DEFAULT_CONFIG_PATH)
#     data: dict[str, Any] = {}
#     if path.exists():
#         data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

#     oracle = data.get("oracle", {}) or {}
#     guard = data.get("guard", {}) or {}
#     audit = data.get("audit", {}) or {}
#     http = data.get("http", {}) or {}

#     # এনভায়রনমেন্ট ভেরিয়েবল থেকে ক্রেডেনশিয়াল রিড করা
#     user = _env("user", oracle.get("user", "claude_ro"))
#     password = _env("password", oracle.get("password"))
#     dsn = _env("dsn", oracle.get("dsn"))

#     if not password:
#         raise SystemExit(
#             "No database password. Set AI_MCP_PASSWORD in the environment "
#             "or oracle.password in config.yaml."
#         )
#     if not dsn:
#         raise SystemExit(
#             "No DSN. Set AI_MCP_DSN, e.g. 'localhost:1521/FREEPDB1'."
#         )

#     views = guard.get("allowed_views") or []
#     if not views:
#         raise SystemExit("guard.allowed_views is empty in config.yaml - refusing to start.")

#     return Config(
#         user=user,
#         password=password,
#         dsn=dsn,
#         wallet_dir=_env("wallet_dir", oracle.get("wallet_dir")),
#         pool_min=int(oracle.get("pool_min", 1)),
#         pool_max=int(oracle.get("pool_max", 4)),
#         pool_timeout=int(oracle.get("pool_timeout", 60)),
#         allowed_views=list(views),
#         max_rows=int(_env("max_rows", guard.get("max_rows", 10_000))),
#         statement_timeout_s=int(guard.get("statement_timeout_s", 60)),
#         client_id=str(_env("client_id", guard.get("client_id", "claude-desktop-local"))),
#         audit_enabled=bool(audit.get("enabled", True)),
#         audit_table=str(audit.get("table", "ai_rpt.claude_query_log")),
#         http_host=str(_env("http_host", http.get("host", "127.0.0.1"))),
#         http_port=int(_env("http_port", http.get("port", 8765))),
#     )