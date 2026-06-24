from __future__ import annotations

import pytest

from app.core.errors import ToolSafetyError
from app.tools.sql_guard import validate_and_wrap_sql

ROW_LIMIT = 200
MAX_LEN = 4000


def _validate(q: str, dialect: str = "sqlite") -> str:
    return validate_and_wrap_sql(q, row_limit=ROW_LIMIT, max_length=MAX_LEN, dialect=dialect)


@pytest.mark.security
@pytest.mark.parametrize("query", [
    "INSERT INTO orders (order_id) VALUES ('x')",
    "UPDATE orders SET gross_amount = 0",
    "DELETE FROM orders",
    "DROP TABLE orders",
    "ALTER TABLE orders ADD COLUMN c INT",
    "TRUNCATE TABLE orders",
    "SELECT order_id FROM orders; DROP TABLE orders",
    "SELECT order_id FROM orders; SELECT 1",
])
def test_rejects_non_select_and_multi_statement(query):
    with pytest.raises(ToolSafetyError):
        _validate(query)


@pytest.mark.security
def test_rejects_tables_outside_allowlist():
    with pytest.raises(ToolSafetyError):
        _validate("SELECT * FROM secret_credentials")


@pytest.mark.security
def test_rejects_oversized_query():
    big = "SELECT order_id FROM orders WHERE order_id IN (" + ",".join(["'x'"] * 2000) + ")"
    with pytest.raises(ToolSafetyError):
        _validate(big)


@pytest.mark.security
def test_rejects_unsafe_function():
    with pytest.raises(ToolSafetyError):
        _validate("SELECT pg_read_file('/etc/passwd')", dialect="postgres")


@pytest.mark.security
def test_allows_plain_select_and_caps_rows():
    wrapped = _validate("SELECT order_id FROM orders")
    assert "LIMIT" in wrapped.upper()
    assert str(ROW_LIMIT + 1) in wrapped


@pytest.mark.security
def test_allows_cte():
    wrapped = _validate(
        "WITH t AS (SELECT customer_id FROM customers) SELECT customer_id FROM t"
    )
    assert "LIMIT" in wrapped.upper()
