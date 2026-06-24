"""OpenTelemetry setup. No-op unless OTEL_ENABLED is true.

Provides a ``span`` context manager used across agent/tool/eval code so instrumentation works
whether or not a collector is configured.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)
_initialized = False


def setup_tracing(app: Any | None = None) -> None:
    """Initialize OTEL exporters if enabled; safe to call multiple times."""
    global _initialized
    settings = get_settings()
    if _initialized or not settings.otel_enabled:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider(
            resource=Resource.create({"service.name": settings.otel_service_name})
        )
        provider.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=settings.otel_exporter_otlp_endpoint, insecure=True)
            )
        )
        trace.set_tracer_provider(provider)
        if app is not None:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
        _initialized = True
        log.info("OpenTelemetry tracing enabled")
    except Exception:  # noqa: BLE001 - tracing must never break the app
        log.warning("OTEL setup failed; continuing without tracing", exc_info=True)


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[None]:
    """Context manager that opens an OTEL span if tracing is active, else a no-op."""
    settings = get_settings()
    if not settings.otel_enabled:
        yield
        return
    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("lineageiq")
        with tracer.start_as_current_span(name) as sp:
            for key, value in attributes.items():
                sp.set_attribute(key, value)
            yield
    except Exception:  # noqa: BLE001
        yield
