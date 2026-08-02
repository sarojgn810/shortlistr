"""Optional OpenTelemetry hooks — no-op if OTel not installed."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator


@contextmanager
def trace_span(name: str, attributes: dict | None = None) -> Iterator[None]:
    try:
        from opentelemetry import trace
        tracer = trace.get_tracer("shortlistr")
        with tracer.start_as_current_span(name, attributes=attributes or {}):
            yield
    except ImportError:
        yield


def record_metric(name: str, value: float, labels: dict | None = None) -> None:
    try:
        from opentelemetry import metrics
        meter = metrics.get_meter("shortlistr")
        counter = meter.create_counter(name)
        counter.add(value, labels or {})
    except ImportError:
        # No OpenTelemetry installed — still emit a structured log line so there's
        # basic local visibility without needing a monitoring stack.
        import logging

        logging.getLogger("shortlistr.metrics").info("metric %s=%s %s", name, value, labels or {})
