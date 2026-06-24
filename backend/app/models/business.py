"""Business-domain ORM models for AtlasCommerce.

Money is Decimal (NUMERIC(18,4)); timestamps are UTC.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Date, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CrmCustomer(Base):
    __tablename__ = "crm_customers"

    crm_customer_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    external_customer_reference: Mapped[str] = mapped_column(String(60))
    legal_name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str] = mapped_column(String(2))
    segment: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[datetime] = mapped_column()


class Customer(Base):
    __tablename__ = "customers"

    customer_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    legal_name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str] = mapped_column(String(2))
    region: Mapped[str] = mapped_column(String(20))
    base_currency: Mapped[str] = mapped_column(String(3))
    # Nullable to allow the "missing customer mapping" incident.
    crm_customer_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("crm_customers.crm_customer_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column()
    status: Mapped[str] = mapped_column(String(20))

    orders: Mapped[list[Order]] = relationship(back_populates="customer")


class CustomerLimit(Base):
    __tablename__ = "customer_limits"

    limit_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"))
    currency: Mapped[str] = mapped_column(String(3))
    credit_limit: Mapped[Decimal] = mapped_column()
    effective_from: Mapped[datetime] = mapped_column()
    effective_to: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column()


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"))
    order_timestamp: Mapped[datetime] = mapped_column(index=True)
    order_currency: Mapped[str] = mapped_column(String(3))
    gross_amount: Mapped[Decimal] = mapped_column()
    net_amount: Mapped[Decimal] = mapped_column()
    tax_amount: Mapped[Decimal] = mapped_column()
    order_status: Mapped[str] = mapped_column(String(20))
    source_system: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[datetime] = mapped_column()

    customer: Mapped[Customer] = relationship(back_populates="orders")


class Payment(Base):
    __tablename__ = "payments"

    payment_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.order_id"))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"))
    payment_timestamp: Mapped[datetime] = mapped_column(index=True)
    payment_currency: Mapped[str] = mapped_column(String(3))
    payment_amount: Mapped[Decimal] = mapped_column()
    payment_status: Mapped[str] = mapped_column(String(20))
    payment_provider: Mapped[str] = mapped_column(String(40))
    idempotency_key: Mapped[str] = mapped_column(String(80))
    updated_at: Mapped[datetime] = mapped_column()

    __table_args__ = (Index("ix_payments_idempotency_key", "idempotency_key"),)


class Refund(Base):
    __tablename__ = "refunds"

    refund_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payments.payment_id"))
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.order_id"))
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.customer_id"))
    refund_timestamp: Mapped[datetime] = mapped_column(index=True)
    refund_currency: Mapped[str] = mapped_column(String(3))
    refund_amount: Mapped[Decimal] = mapped_column()
    refund_reason: Mapped[str] = mapped_column(String(80))
    refund_status: Mapped[str] = mapped_column(String(20))
    updated_at: Mapped[datetime] = mapped_column()


class FxRate(Base):
    __tablename__ = "fx_rates"

    rate_date: Mapped[date] = mapped_column(Date, primary_key=True)
    source_currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    target_currency: Mapped[str] = mapped_column(String(3), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    exchange_rate: Mapped[Decimal] = mapped_column()
    retrieved_at: Mapped[datetime] = mapped_column()


class Shipment(Base):
    __tablename__ = "shipments"

    shipment_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.order_id"))
    warehouse_region: Mapped[str] = mapped_column(String(20))
    carrier: Mapped[str] = mapped_column(String(40))
    shipment_status: Mapped[str] = mapped_column(String(20))
    shipped_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column()


class DailyRevenueReport(Base):
    __tablename__ = "daily_revenue_report"

    report_date: Mapped[date] = mapped_column(Date, primary_key=True)
    region: Mapped[str] = mapped_column(String(20), primary_key=True)
    reporting_currency: Mapped[str] = mapped_column(String(3))
    gross_revenue: Mapped[Decimal] = mapped_column()
    refund_total: Mapped[Decimal] = mapped_column()
    net_revenue: Mapped[Decimal] = mapped_column()
    order_count: Mapped[int] = mapped_column()
    payment_count: Mapped[int] = mapped_column()
    generated_at: Mapped[datetime] = mapped_column()
    source_pipeline_run_id: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
