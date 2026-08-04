"""Lightweight, optional observability wiring (Sentry + OpenTelemetry).

Sentry/OpenTelemetry opsional (Audit rekomendasi "Sentry/OpenTelemetry").
Model yang dipakai:
- Inspeksi env saat startup. Bila ``SENTRY_DSN`` kosong -> no-op.
- Bila ``OTEL_EXPORTER_OTLP_ENDPOINT`` kosong -> no-op.
- ``sentinel`` pattern: modul ini tidak pernah Import error.
  Bila sentry_sdk/opentelemetry tidak terinstall, observability menurun ke
  no-op tetapi fungsi ``capture_exception``/``add_breadcrumb``/``span`` tetap
  callable, sehingga call-sites tersebar (geo_api.py, predict.py, app.py)
  tidak perlu try/except di sekitar pemanggilan.
- Kontrak ``capture_exception``/``add_breadcrumb``/``span`` adalah subset
  Sentry SDK publik agar engineer tahu nama yang familiar.
"""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Optional SDK imports — guarded so absence never blocks startup.
# ---------------------------------------------------------------------------
try:
    import sentry_sdk  # type: ignore[import-not-found]
    from sentry_sdk.integrations.fastapi import (  # type: ignore[import-not-found]
        FastApiIntegration,
    )
    from sentry_sdk.integrations.logging import (  # type: ignore[import-not-found]
        LoggingIntegration,
    )

    _HAS_SENTRY = True
except Exception:  # pragma: no cover
    sentry_sdk = None  # type: ignore[assignment]
    _HAS_SENTRY = False


try:
    from opentelemetry import trace  # type: ignore[import-not-found]
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # type: ignore[import-not-found]
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.resources import (  # type: ignore[import-not-found]
        Resource,
    )
    from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
    from opentelemetry.sdk.trace.export import (  # type: ignore[import-not-found]
        BatchSpanProcessor,
    )

    _HAS_OTEL = True
except Exception:  # pragma: no cover
    trace = None  # type: ignore[assignment]
    _HAS_OTEL = False


_INITIALIZED = False
_TRACER = None  # opentelemetry.trace.Tracer or None


def init_observability(
    *,
    sentry_dsn: str | None = None,
    otel_endpoint: str | None = None,
    service_name: str = "firecast-api",
    environment: str | None = None,
    release: str | None = None,
    sample_rate: float = 1.0,
) -> dict[str, Any]:
    """Initialise Sentry + OpenTelemetry from env (idempotent, sandbox-safe).

    Returns a small snapshot describing what initialised. Failures never raise
    — observability is best-effort and must not block the API.
    """
    global _INITIALIZED, _TRACER
    if _INITIALIZED:
        return {"status": "already_initialized"}

    sentry_dsn = sentry_dsn or os.environ.get("SENTRY_DSN")
    otel_endpoint = otel_endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    environment = environment or os.environ.get("APP_ENV", "development")
    release = release or os.environ.get("APP_RELEASE")
    sample_rate_env = os.environ.get("SENTRY_SAMPLE_RATE")
    if sample_rate_env:
        try:
            sample_rate = float(sample_rate_env)
        except ValueError:
            logger.warning("Invalid SENTRY_SAMPLE_RATE=%r, fallback to 1.0", sample_rate_env)

    result: dict[str, Any] = {"sentry": False, "opentelemetry": False}

    # --- Sentry ----------------------------------------------------------
    if sentry_dsn and _HAS_SENTRY:
        try:
            sentry_sdk.init(
                dsn=sentry_dsn,
                environment=environment,
                release=release,
                traces_sample_rate=sample_rate,
                integrations=[
                    LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
                    FastApiIntegration(),
                ],
            )
            result["sentry"] = True
            logger.info("Sentry initialised (env=%s, release=%s)", environment, release)
        except Exception as e:  # pragma: no cover
            logger.warning("Sentry init failed (degraded): %s", e)

    # --- OpenTelemetry ---------------------------------------------------
    if otel_endpoint and _HAS_OTEL:
        try:
            resource = Resource.create({"service.name": service_name})
            provider = TracerProvider(resource=resource)
            exporter = OTLPSpanExporter(endpoint=otel_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            trace.set_tracer_provider(provider)
            _TRACER = trace.get_tracer(service_name)
            result["opentelemetry"] = True
            logger.info("OpenTelemetry initialised (service=%s, endpoint=%s)", service_name, otel_endpoint)
        except Exception as e:  # pragma: no cover
            logger.warning("OpenTelemetry init failed (degraded): %s", e)

    _INITIALIZED = True
    return result


# ---------------------------------------------------------------------------
# Public, sandbox-safe convenience functions
# ---------------------------------------------------------------------------
def capture_exception(exception: BaseException, **tags: Any) -> None:
    """Forward to ``sentry_sdk.capture_exception``; no-op bila unavailable."""
    if not _HAS_SENTRY:
        return
    try:
        for k, v in tags.items():
            sentry_sdk.set_tag(k, v)  # type: ignore[union-attr]
        sentry_sdk.capture_exception(exception)  # type: ignore[union-attr]
    except Exception as e:  # pragma: no cover
        logger.debug("capture_exception failed: %s", e)


def add_breadcrumb(category: str, message: str, level: str = "info", **data: Any) -> None:
    """Forward to ``sentry_sdk.add_breadcrumb``; no-op bila unavailable."""
    if not _HAS_SENTRY:
        return
    try:
        sentry_sdk.add_breadcrumb(  # type: ignore[union-attr]
            category=category,
            message=message,
            level=level if level in {"info", "warning", "error", "debug", "fatal"} else "info",
            data=data,
        )
    except Exception as e:  # pragma: no cover
        logger.debug("add_breadcrumb failed: %s", e)


@contextmanager
def span(name: str, **attrs: Any) -> Iterator[None]:
    """Lightweight tracing span (OTel if available) else contextmanager.

    Usage::

        with span("predict_fire_risk", model_type=model_type):
            ...

    Bila OpenTelemetry tidak dikonfigurasi, this is a cheap no-op context
    that still propagates exceptions to Sentry via :func:`capture_exception`.
    """
    if _TRACER is not None:
        try:
            with _TRACER.start_as_current_span(name) as _ot_span:
                for k, v in attrs.items():
                    with contextlib.suppress(Exception):
                        _ot_span.set_attribute(k, v)
                yield
                return
        except Exception as e:  # pragma: no cover
            logger.debug("otel span '%s' failed: %s", name, e)
    # Fallback / no-op path.
    yield


def is_enabled() -> bool:
    """Return True bila either Sentry atau OTEL aktif."""
    return _INITIALIZED


__all__ = [
    "add_breadcrumb",
    "capture_exception",
    "init_observability",
    "is_enabled",
    "span",
]
