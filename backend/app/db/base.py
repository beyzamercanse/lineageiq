"""SQLAlchemy declarative base and shared column types.

Portable across PostgreSQL and SQLite (ADR-0005). Money uses NUMERIC(18,4) -> Decimal.
Timestamps are timezone-aware and stored in UTC.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, Numeric
from sqlalchemy.orm import DeclarativeBase, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""

    type_annotation_map = {
        Decimal: Numeric(18, 4),
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSON,
        list[Any]: JSON,
    }


def money_column(**kwargs: Any):
    """A NUMERIC(18,4) money column mapped to Decimal."""
    return mapped_column(Numeric(18, 4), **kwargs)


def utc_timestamp_column(**kwargs: Any):
    """A timezone-aware timestamp column (UTC)."""
    return mapped_column(DateTime(timezone=True), **kwargs)
