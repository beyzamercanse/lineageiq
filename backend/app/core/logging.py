"""Structured JSON logging with correlation-id support.

Never log secrets. The formatter redacts known sensitive keys defensively.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar

from pythonjsonlogger import jsonlogger

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

_SENSITIVE_KEYS = {"password", "api_key", "secret", "token", "authorization"}


class CorrelationIdFilter(logging.Filter):
    """Attach the current correlation id (if any) to every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = correlation_id_var.get()
        return True


class RedactingJsonFormatter(jsonlogger.JsonFormatter):
    """JSON formatter that redacts obvious secret fields."""

    def process_log_record(self, log_record: dict) -> dict:
        for key in list(log_record.keys()):
            if key.lower() in _SENSITIVE_KEYS and log_record[key]:
                log_record[key] = "***redacted***"
        return super().process_log_record(log_record)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once, emitting structured JSON to stdout."""
    handler = logging.StreamHandler()
    formatter = RedactingJsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s %(correlation_id)s"
    )
    handler.setFormatter(formatter)
    handler.addFilter(CorrelationIdFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
