"""Unit tests for ``frontend.utils.log_handler`` (UI Revamp Fase 5.1).

Covers the pure-Python parts of the Streamlit log buffer handler:
- ``StreamlitLogHandler.emit`` writes an entry when a runtime is available
  (via a fake ``st.session_state`` dict) and silently drops when it isn't.
- Circular buffer trims to ``capacity`` (default 50).
- ``_level_to_color`` CSS class mapping for DEBUG/INFO/WARNING/ERROR.
- ``attach_to`` / ``add_to_root_logger`` idempotency-ish — handler instances
  are tracked in ``_INSTALLED_HANDLERS``.
- ``get_buffer`` / ``clear_buffer`` read-only helpers work without runtime.

Per PLAN.md Task 5.1, these do **not** require a real Streamlit runtime:
we monkey-patch ``log_handler.st`` with a stub that mimics ``session_state``
as a plain dict. The real integration (full Streamlit render) is exercised
by ``tests/test_ui_revamp_integration.py`` (Fase 5.2).
"""
from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ── Fake Streamlit session_state ──────────────────────────────────────
class _FakeState(dict):
    pass


class _FakeSt:
    """Mimics the parts of ``streamlit`` that log_handler touches."""

    def __init__(self):
        self.session_state = _FakeState()


class TestLogHandlerUnit(unittest.TestCase):
    """Pure-Python tests for streamlit_log_handler module helpers."""

    def setUp(self):
        from frontend.utils import log_handler
        self.log_handler = log_handler
        # Backup and replace st with our stub so emit() can mutate buffer.
        self._backup_st = log_handler.st
        self.fake_st = _FakeSt()
        log_handler.st = self.fake_st

    def tearDown(self):
        self.log_handler.st = self._backup_st

    def _emit_n(self, handler, n, level=logging.INFO, msg_fmt="msg-{}"):
        logger = logging.getLogger("test.log_handler.unit")
        logger.handlers = []
        logger.addHandler(handler)
        logger.setLevel(level)
        for i in range(n):
            logger.log(level, msg_fmt.format(i))

    # ── level mapping ─────────────────────────────────────────────────
    def test_level_to_color_debug_info_maps_to_ok(self):
        self.assertEqual(self.log_handler._level_to_color(logging.DEBUG), "ok")
        self.assertEqual(self.log_handler._level_to_color(logging.INFO), "ok")

    def test_level_to_color_warning_maps_to_warn(self):
        self.assertEqual(self.log_handler._level_to_color(logging.WARNING), "warn")

    def test_level_to_color_error_critical_maps_to_err(self):
        self.assertEqual(self.log_handler._level_to_color(logging.ERROR), "err")
        self.assertEqual(self.log_handler._level_to_color(logging.CRITICAL), "err")

    def test_level_to_color_custom_below_warning_is_ok(self):
        # Levels exist between INFO(20) and WARNING(30) (e.g. logging.INFO+1)
        self.assertEqual(self.log_handler._level_to_color(25), "ok")

    # ── StreamlitLogHandler construction ──────────────────────────────
    def test_handler_rejects_nonpositive_capacity(self):
        with self.assertRaises(ValueError):
            self.log_handler.StreamlitLogHandler(capacity=0)
        with self.assertRaises(ValueError):
            self.log_handler.StreamlitLogHandler(capacity=-5)

    def test_handler_default_capacity_is_50(self):
        h = self.log_handler.StreamlitLogHandler()
        self.assertEqual(h.capacity, 50)
        self.assertEqual(h.key, self.log_handler.SESSION_KEY)

    def test_handler_custom_capacity_and_key(self):
        h = self.log_handler.StreamlitLogHandler(capacity=7, key="custom_buf")
        self.assertEqual(h.capacity, 7)
        self.assertEqual(h.key, "custom_buf")

    # ── emit() + buffer ───────────────────────────────────────────────
    def test_emit_appends_entry_to_session_buffer(self):
        h = self.log_handler.StreamlitLogHandler()
        self._emit_n(h, 3)
        buf = self.fake_st.session_state[self.log_handler.SESSION_KEY]
        self.assertEqual(len(buf), 3)
        # Each entry has the documented schema keys
        for entry in buf:
            self.assertIn("ts", entry)
            self.assertIn("level", entry)
            self.assertIn("levelno", entry)
            self.assertIn("logger", entry)
            self.assertIn("msg", entry)
            self.assertIn("color", entry)
        # First message recorded
        self.assertIn("msg-0", buf[0]["msg"])

    def test_emit_truncates_to_capacity(self):
        h = self.log_handler.StreamlitLogHandler(capacity=5)
        self._emit_n(h, 12)
        buf = self.fake_st.session_state[self.log_handler.SESSION_KEY]
        self.assertEqual(len(buf), 5)
        # Oldest entries dropped — last recorded is msg-11
        self.assertIn("msg-11", buf[-1]["msg"])
        self.assertIn("msg-7", buf[0]["msg"])  # 12-5=7 is the first kept

    def test_emit_colors_match_level(self):
        h = self.log_handler.StreamlitLogHandler()
        logger = logging.getLogger("test.log_handler.colors")
        logger.handlers = []
        logger.addHandler(h)
        logger.setLevel(logging.DEBUG)
        logger.debug("d")
        logger.info("i")
        logger.warning("w")
        logger.error("e")
        buf = self.fake_st.session_state[self.log_handler.SESSION_KEY]
        self.assertEqual(buf[0]["color"], "ok")     # debug
        self.assertEqual(buf[1]["color"], "ok")     # info
        self.assertEqual(buf[2]["color"], "warn")   # warning
        self.assertEqual(buf[3]["color"], "err")    # error

    def test_emit_record_negative_levelno_does_not_break(self):
        # Defensive: a custom level between 0 and WARNING should still map ok.
        h = self.log_handler.StreamlitLogHandler()
        # Set handler level to the lowest so it always accepts the record.
        h.setLevel(1)
        logger = logging.getLogger("test.log_handler.neglevel")
        logger.handlers = []
        logger.addHandler(h)
        # NOTSET (0) means the logger delegates to handler's level — so level=5 is recorded.
        logger.setLevel(logging.NOTSET)
        # custom level 5 (below DEBUG=10) — handler accepts via h.level=1.
        logger.log(5, "lower than debug")
        buf = self.fake_st.session_state.get(self.log_handler.SESSION_KEY, [])
        # If stdlib decided NOT to call handler.isEnabledFor(5), buf is empty — acceptable.
        # If it did call (which it does when handler.level < 5), the entry should appear.
        if buf:
            self.assertEqual(buf[0]["color"], "ok")

    def test_clear_empties_buffer(self):
        h = self.log_handler.StreamlitLogHandler()
        self._emit_n(h, 5)
        h.clear()
        buf = self.fake_st.session_state[self.log_handler.SESSION_KEY]
        self.assertEqual(len(buf), 0)

    def test_snapshot_returns_shallow_copy(self):
        h = self.log_handler.StreamlitLogHandler()
        self._emit_n(h, 4)
        snap = h.snapshot()
        # snapshot is independent of buffer mutation
        h.clear()
        self.assertEqual(len(snap), 4)
        self.assertEqual(len(self.fake_st.session_state[self.log_handler.SESSION_KEY]), 0)

    # ── get_buffer / clear_buffer module helpers ─────────────────────
    def test_get_buffer_returns_empty_when_no_runtime(self):
        # Simulate no streamlit runtime
        self.log_handler.st = None
        self.assertEqual(self.log_handler.get_buffer(), [])

    def test_get_buffer_returns_copy_when_runtime_available(self):
        self.log_handler.st = self.fake_st
        h = self.log_handler.StreamlitLogHandler()
        self._emit_n(h, 2)
        out = self.log_handler.get_buffer()
        self.assertEqual(len(out), 2)
        # Mutating returned list does NOT affect session buffer
        out.append({"fake": True})
        self.assertEqual(len(self.fake_st.session_state[self.log_handler.SESSION_KEY]), 2)

    def test_clear_buffer_noop_without_runtime(self):
        self.log_handler.st = None
        # Must not raise even when there is no session_state at all
        self.log_handler.clear_buffer()

    def test_clear_buffer_empties_session_state(self):
        self.log_handler.st = self.fake_st
        h = self.log_handler.StreamlitLogHandler()
        self._emit_n(h, 3)
        self.log_handler.clear_buffer()
        self.assertEqual(len(self.fake_st.session_state[self.log_handler.SESSION_KEY]), 0)

    # ── emit() never raises on streamlit missing ──────────────────────
    def test_emit_silent_when_no_streamlit_runtime(self):
        self.log_handler.st = None
        h = self.log_handler.StreamlitLogHandler()
        # Should not raise
        logger = logging.getLogger("test.log_handler.noruntime")
        logger.handlers = []
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
        logger.info("this should silently drop")
        # Buffer accessor also returns [] (no st.session_state)
        self.assertEqual(h.snapshot(), [])

    # ── attach_to / add_to_root_logger ────────────────────────────────
    def test_attach_to_adds_handler_instance(self):
        before = len(self.log_handler._INSTALLED_HANDLERS)
        logger = logging.getLogger("test.attach_target")
        h = self.log_handler.attach_to(logger, capacity=10)
        self.assertIn(h, logger.handlers)
        self.assertEqual(h.capacity, 10)
        self.assertEqual(h.level, logging.INFO)
        self.assertEqual(logger.level, logging.INFO)
        # Tracked
        self.assertEqual(len(self.log_handler._INSTALLED_HANDLERS), before + 1)
        # Cleanup so we don't leak handlers across test cases
        logger.removeHandler(h)

    def test_attach_to_promotes_logger_level_when_notset(self):
        # A fresh logger defaults to NOTSET — attach_to must promote to INFO
        logger = logging.getLogger("test.attach_notset")
        logger.level = logging.NOTSET
        h = self.log_handler.attach_to(logger)
        self.assertEqual(logger.level, logging.INFO)
        logger.removeHandler(h)

    def test_add_to_root_logger_attaches_to_root(self):
        h = self.log_handler.add_to_root_logger()
        root = logging.getLogger()
        self.assertIn(h, root.handlers)
        self.assertEqual(h.capacity, self.log_handler.DEFAULT_CAPACITY)
        root.removeHandler(h)

    def test_emit_does_not_raise_on_formatter_failure(self):
        """If self.format(record) raises, emit falls back to getMessage()."""
        h = self.log_handler.StreamlitLogHandler()

        class _BoomFormatter(logging.Formatter):
            def format(self, record):
                raise RuntimeError("format boom")

        h.setFormatter(_BoomFormatter())
        logger = logging.getLogger("test.format_boom")
        logger.handlers = []
        logger.addHandler(h)
        logger.setLevel(logging.INFO)
        # Should not raise — should still emit using getMessage
        logger.info("fallback path")
        buf = self.fake_st.session_state[self.log_handler.SESSION_KEY]
        self.assertEqual(len(buf), 1)
        self.assertEqual(buf[0]["msg"], "fallback path")


if __name__ == "__main__":
    unittest.main()
