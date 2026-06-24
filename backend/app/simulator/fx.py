"""Deterministic FX rate generation and exact Decimal conversion.

Rates are stored as source -> target (units of target currency per 1 source unit). The same
``convert`` function is used by both the generator (to build reports) and the validator (to
reconcile them), so reports reconcile exactly.
"""

from __future__ import annotations

import random
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from app.simulator.config import BASE_FX_TO_USD, REPORTING_CURRENCY

MONEY_QUANT = Decimal("0.0001")
RATE_QUANT = Decimal("0.00000001")


def _daily_rate_to_usd(currency: str, day_index: int, rng: random.Random) -> Decimal:
    """Deterministic daily rate (currency -> USD) with mild drift."""
    base = Decimal(BASE_FX_TO_USD[currency])
    if currency == REPORTING_CURRENCY:
        return Decimal("1.00000000")
    # +/- up to ~2% pseudo-random drift, deterministic in rng draw order.
    drift = Decimal(str(rng.uniform(-0.02, 0.02)))
    return (base * (Decimal("1") + drift)).quantize(RATE_QUANT, rounding=ROUND_HALF_UP)


def build_fx_table(
    days: list[date], rng: random.Random
) -> dict[tuple[date, str, str], Decimal]:
    """Build a {(date, source, target=USD): rate} table for all currencies and days."""
    table: dict[tuple[date, str, str], Decimal] = {}
    for i, d in enumerate(days):
        for currency in BASE_FX_TO_USD:
            table[(d, currency, REPORTING_CURRENCY)] = _daily_rate_to_usd(currency, i, rng)
    return table


def convert(
    amount: Decimal,
    source_currency: str,
    target_currency: str,
    on_date: date,
    fx_table: dict[tuple[date, str, str], Decimal],
) -> Decimal:
    """Convert ``amount`` from source to target on ``on_date`` using the FX table.

    Only conversion to the reporting currency is supported in the MVP.
    """
    if source_currency == target_currency:
        return amount.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
    if target_currency != REPORTING_CURRENCY:
        raise ValueError(f"Only conversion to {REPORTING_CURRENCY} is supported")
    rate = fx_table[(on_date, source_currency, target_currency)]
    return (amount * rate).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
