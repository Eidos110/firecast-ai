"""Unit tests for ``src.observability`` — sandbox-safe no-op behaviour.

Covers the parts that MUST work even when:
- sentry_sdk is NOT installed,
- opentelemetry is NOT installed,
- no env vars are set.

The integration paths (real Sentry/OTLP server) are not covered here because
they require a live DSN. CI must verify that simply importing the module and
calling its public API never raises — that contract is what call-sites rely on.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


class TestObservabilityNoOp(unittest.TestCase):
    """Init with no DSN / OTEL endpoint → all helpers degrade to no-op."""

    def setUp(self):
        # Force-clean env so init doesn't accidentally pick up developer secrets.
        for key in (
            "SENTRY_DSN",
            "SENTRY_SAMPLE_RATE",
            "OTEL_EXPORTER_OTLP_ENDPOINT",
            "APP_ENV",
            "APP_RELEASE",
        ):
            os.environ.pop(key, None)
        # Reset module-level init flag for reproducibility.
        from src import observability

        observability._INITIALIZED = False
        observability._TRACER = None

    def tearDown(self):
        from src import observability

        observability._INITIALIZED = False
        observability._TRACER = None

    def test_init_returns_disabled_when_no_env(self):
        from src.observability import init_observability

        result = init_observability()
        self.assertIn("sentry", result)
        self.assertIn("opentelemetry", result)
        self.assertFalse(result["sentry"])
        self.assertFalse(result["opentelemetry"])

    def test_init_is_idempotent(self):
        from src.observability import init_observability

        first = init_observability()
        # First call returns capability snapshot, subsequent calls short-circuit
        # to {"status": "already_initialized"} — i.e. distinct contracts by
        # design. Both must be dicts and must not raise.
        second = init_observability()
        self.assertIsInstance(first, dict)
        self.assertIsInstance(second, dict)
        self.assertEqual(second, {"status": "already_initialized"})

    def test_capture_exception_no_op(self):
        from src.observability import capture_exception

        # Must not raise even without SDK installed/init.
        capture_exception(ValueError("dummy"), request_id="abc")

    def test_add_breadcrumb_no_op(self):
        from src.observability import add_breadcrumb

        add_breadcrumb(category="test", message="breadcrumb", level="info")
        add_breadcrumb(category="test", message="bad-level", level="boom")

    def test_span_context_manager_does_not_block(self):
        from src.observability import span

        with span("test.span", model_type="new") as _:
            pass
        # Span must not raise on __exit__ even without OTel.
        self.assertEqual(span.__name__, "span")

    def test_is_enabled_false_until_init(self):
        from src.observability import is_enabled

        self.assertFalse(is_enabled())


class TestObservabilityFakeInit(unittest.TestCase):
    """Init with a fake-looking DSN exercises code paths without SDK installed.

    In the local sandbox, sentry_sdk / opentelemetry are not installed, so
    init() returns disabled=True (libs missing) rather than enabled=True.
    This test ensures the guarded ``try/except`` block does not raise.
    """

    def setUp(self):
        os.environ["SENTRY_DSN"] = "https://dummy@example.com/1"
        os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = "http://localhost:4318/v1/traces"
        from src import observability

        observability._INITIALIZED = False
        observability._TRACER = None

    def tearDown(self):
        os.environ.pop("SENTRY_DSN", None)
        os.environ.pop("OTEL_EXPORTER_OTLP_ENDPOINT", None)
        from src import observability

        observability._INITIALIZED = False
        observability._TRACER = None

    def test_init_with_env_but_no_libs_does_not_raise(self):
        from src.observability import init_observability

        result = init_observability()
        # Both must be False in the sandbox (libs not installed).
        self.assertFalse(result["sentry"])
        self.assertFalse(result["opentelemetry"])

    def test_helpers_safe_after_failed_init(self):
        from src.observability import (
            add_breadcrumb,
            capture_exception,
            init_observability,
            is_enabled,
            span,
        )

        # Run init first — with env vars set in setUp() but no SDK installed,
        # init() returns disabled=True (libs missing) but still flips
        # _INITIALIZED=True so callers don't retry init on every request.
        init_result = init_observability()
        self.assertFalse(init_result["sentry"])
        self.assertFalse(init_result["opentelemetry"])

        # All helpers must be safe to invoke regardless of SDK availability.
        capture_exception(RuntimeError("x"))
        add_breadcrumb("cat", "msg")
        with span("test"):
            pass
        # is_enabled toggles based on _INITIALIZED, not actual SDK availability.
        # After init() ran and returned disabled, we still flip the flag so the
        # caller doesn't repeatedly retry init on every request.
        self.assertTrue(is_enabled())


if __name__ == "__main__":
    unittest.main()
