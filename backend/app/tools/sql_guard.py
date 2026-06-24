"""SQL safety guard for the read-only SQL tool.

Parses with sqlglot and enforces: single statement, SELECT-only (CTEs allowed), schema/table
allowlist, no unsafe functions, length limit, and a hard row cap. See docs/SECURITY.md.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp

import app.models  # noqa: F401 - ensures all tables are registered on Base.metadata
from app.core.errors import ToolSafetyError
from app.db.base import Base

# Allowlist of tables the agent may read (all curated tables).
ALLOWED_TABLES: set[str] = set(Base.metadata.tables.keys())

_FORBIDDEN_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter, exp.Create,
    exp.Command, exp.Into, exp.Set, exp.Transaction, exp.Commit, exp.Rollback,
)
_ALLOWED_TOP = (exp.Select, exp.Union, exp.Subquery, exp.With, exp.Paren)
_FORBIDDEN_FUNCTIONS = {
    "pg_read_file", "pg_ls_dir", "pg_sleep", "lo_import", "lo_export", "dblink", "copy",
    "load_extension", "readfile", "writefile",
}


def validate_and_wrap_sql(
    query: str, *, row_limit: int, max_length: int, dialect: str = "postgres"
) -> str:
    """Validate ``query`` and return a row-capped wrapped statement. Raise ToolSafetyError."""
    if not query or not query.strip():
        raise ToolSafetyError("Empty SQL query")
    if len(query) > max_length:
        raise ToolSafetyError(f"Query exceeds max length {max_length}")

    try:
        statements = [s for s in sqlglot.parse(query, read=dialect) if s is not None]
    except Exception as exc:  # parse error
        raise ToolSafetyError(f"Unparseable SQL: {exc}") from exc

    if len(statements) != 1:
        raise ToolSafetyError("Only a single statement is allowed")
    stmt = statements[0]

    if not isinstance(stmt, _ALLOWED_TOP):
        raise ToolSafetyError(f"Only SELECT statements are allowed (got {type(stmt).__name__})")

    for node in stmt.walk():
        expr = node[0] if isinstance(node, tuple) else node
        if isinstance(expr, _FORBIDDEN_NODES):
            raise ToolSafetyError(f"Forbidden SQL construct: {type(expr).__name__}")
        if (isinstance(expr, exp.Anonymous) and expr.name
                and expr.name.lower() in _FORBIDDEN_FUNCTIONS):
            raise ToolSafetyError(f"Forbidden function: {expr.name}")
        if isinstance(expr, exp.Func):
            fname = (expr.sql_name() or "").lower()
            if fname in _FORBIDDEN_FUNCTIONS:
                raise ToolSafetyError(f"Forbidden function: {fname}")

    # Table allowlist (CTE names are not real tables and are exempt).
    cte_names = {c.alias_or_name for c in stmt.find_all(exp.CTE)}
    tables = {t.name for t in stmt.find_all(exp.Table)}
    illegal = {t for t in tables if t and t not in ALLOWED_TABLES and t not in cte_names}
    if illegal:
        raise ToolSafetyError(f"Query references tables outside the allowlist: {sorted(illegal)}")

    normalized = stmt.sql(dialect=dialect)
    # Hard row cap; fetch one extra to detect truncation.
    return f"SELECT * FROM ({normalized}) AS _lq LIMIT {row_limit + 1}"
