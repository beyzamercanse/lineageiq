"""SQLAlchemy declarative base and shared column types.

Portable across PostgreSQL and SQLite (ADR-0005). Money uses NUMERIC(18,4) -> Decimal.
On SQLite (which has no exact NUMERIC affinity) money is stored as a fixed-scale string so it
round-trips exactly — honoring the "no floats for money" rule.
Timestamps are timezone-aware and stored in UTC.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Numeric, String
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import JSON, TypeDecorator

_MONEY_SCALE = 4


class SqliteDecimal(TypeDecorator):
    """Store a Decimal as a fixed-scale string (exact round-trip on SQLite)."""

    impl = String(40)
    cache_ok = True

    def __init__(self, scale: int = _MONEY_SCALE) -> None:
        super().__init__()
        self.scale = scale
        self._quant = Decimal(1).scaleb(-scale)

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return str(Decimal(value).quantize(self._quant))

    def process_result_value(self, value: Any, dialect: Any) -> Decimal | None:
        if value is None:
            return None
        return Decimal(value)


# NUMERIC(18,4) on Postgres; exact decimal-as-string on SQLite.
Money = Numeric(18, _MONEY_SCALE).with_variant(SqliteDecimal(_MONEY_SCALE), "sqlite")
# Higher precision for FX exchange rates.
Rate = Numeric(18, 8).with_variant(SqliteDecimal(8), "sqlite")


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    type_annotation_map = {  # noqa: RUF012 - SQLAlchemy requires a plain dict here
        Decimal: Money,
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSON,
        list[Any]: JSON,
    }
