"""Streamlit-compatible log handler (UI Revamp Fase 1 — Task 1.1).

Provides a :class:`StreamlitLogHandler` that buffers records into
``st.session_state["log_buffer"]`` so the UI can render engineer-grade
inference logs without drilling through the terminal / Streamlit logs pane.

Design notes
------------
- The handler is a stdlib ``logging.Handler`` so it plugs into any logger via
  ``logger.addHandler(StreamlitLogHandler())``. It never raises: the Streamlit
  runtime may not be available (e.g. unit tests, scripts) so every
  ``st.session_state`` interaction is wrapped in a defensive try/except.
- Buffer is a circular list capped at ``MAX_ENTRIES`` (default 50). Older
  entries are dropped silently — emperically 50 is enough for the bottom-bar
  8-10 line log box plus a few extras.
- Each emitted entry is a plain dict with::

    {
      "ts": <ISO8601 UTC>,
      "level": "INFO" | "WARNING" | "ERROR" | ...,
      "levelno": <int>,
      "logger": <name>,
      "msg": <formatted message>,
      "color": "ok" | "warn" | "err",
    }

  ``color`` is the CSS class used by ``bottom_bar.py`` and ``app.css``.
- ``add_to_root_logger()`` / ``attach_to()`` helpers make it easy to hook
  the handler from ``app.py`` and ``prediction_engine.py``.

Usage
-----
>>> import logging
>>> from frontend.utils.log_handler import StreamlitLogHandler, add_to_root_logger
>>> add_to_root_logger()                 # attach to root logger
>>> StreamlitLogHandler(capacity=100)    # or instantiate directly
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Streamlit must be importable but we keep the import lazy-equivalent: if it
# is missing (e.g. unit tests of the handler itself), emit() degrades to a
# no-op so the host application never crashes.
try:
    import streamlit as st  # type: ignore
except Exception:  # pragma: no cover - exercised only in headless envs
    st = None  # type: ignore

# ── Defaults ────────────────────────────────────────────────────────────
DEFAULT_CAPACITY: int = 50
SESSION_KEY: str = "log_buffer"

# Map record.levelno -> CSS class used by `.log-line.ok|.warn|.err`
# Log levels (stdlib): DEBUG=10, INFO=20, WARNING=30, ERROR=40, CRITICAL=50.
_LEVEL_COLOR = {
    "ok": "ok",       # DEBUG / INFO
    "warn": "warn",   # WARNING
    "err": "err",     # ERROR / CRITICAL
}


def _level_to_color(levelno: int) -> str:
    """Return the CSS color-class for a stdlib log level."""
    if levelno < logging.WARNING:
        return _LEVEL_COLOR["ok"]
    if levelno < logging.ERROR:
        return _LEVEL_COLOR["warn"]
    return _LEVEL_COLOR["err"]


class StreamlitLogHandler(logging.Handler):
    """Logging handler that streams records into ``st.session_state[SESSION_KEY]``.

    Behaviour:
    - Mutates ``st.session_state`` only when a Streamlit runtime is available
      (i.e. inside ``streamlit run``). Outside of a runtime (scripts, tests)
      ``emit`` is a no-op — the record is silently dropped.
    - The buffer is circular: when it exceeds ``capacity``, the oldest entries
      are trimmed via slicing so we never grow unbounded.
    - Thread-safe enough for the Streamlit single-threaded scripting run;
      for hot multi-thread paths use a dedicated queue instead.
    """

    def __init__(self, capacity: int = DEFAULT_CAPACITY, key: str = SESSION_KEY) -> None:
        super().__init__()
        if capacity <= 0:
            raise ValueError(f"capacity must be > 0, got {capacity}")
        self.capacity: int = int(capacity)
        self.key: str = key

    # ── Session-state interaction ───────────────────────────────────
    def _buffer(self) -> Optional[List[Dict[str, Any]]]:
        """Return the live buffer list from session state, or None if unavailable."""
        if st is None:
            return None
        try:
            buf = st.session_state.get(self.key)
            if buf is None:
                buf = []
                st.session_state[self.key] = buf
            return buf
        except Exception:
            # No ScriptRunContext / not in a Streamlit script — degrade gracefully.
            return None

    def _append(self, entry: Dict[str, Any]) -> None:
        buf = self._buffer()
        if buf is None:
            return
        buf.append(entry)
        # Circular truncate — slice assignment keeps the same list object so
        # other references reading st.session_state[key] see the trim.
        if len(buf) > self.capacity:
            del buf[: len(buf) - self.capacity]

    # ── logging.Handler API ────────────────────────────────────────
    def emit(self, record: logging.LogRecord) -> None:
        """Format *record* and append a JSON-safe dict to the buffer.

        Never raises — handler errors propagate as silent no-ops so the host
        app's logging pipeline is never broken by a UI helper.
        """
        try:
            try:
                msg = self.format(record)
            except Exception:
                msg = record.getMessage()
            entry: Dict[str, Any] = {
                "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "level": record.levelname,
                "levelno": int(record.levelno),
                "logger": record.name,
                "msg": msg,
                "color": _level_to_color(record.levelno),
            }
            self._append(entry)
        except Exception:
            # Last-resort: drop silently. logging.Handler's contract is that
            # emit() never raises (silently swallow via handleError instead).
            return

    # ── Public helpers (used by tests + integrations) ──────────────
    def clear(self) -> None:
        """Empty the buffer (helper for admin/cache-invalidate endpoints)."""
        buf = self._buffer()
        if buf is not None:
            buf.clear()

    def snapshot(self) -> List[Dict[str, Any]]:
        """Return a shallow copy of the current buffer (or [] if no runtime)."""
        buf = self._buffer()
        return list(buf) if buf is not None else []


# ── Module-level attachment helpers ────────────────────────────────────
_INSTALLED_HANDLERS: List["StreamlitLogHandler"] = []


def attach_to(logger: logging.Logger, capacity: int = DEFAULT_CAPACITY) -> StreamlitLogHandler:
    """Attach a fresh :class:`StreamlitLogHandler` to *logger* (idempotent-ish).

    Adding the same handler instance twice is a no-op (we track instances).
    Tuning ``capacity`` per-logger is allowed — the module-level helper
    ``add_to_root_logger`` uses the default 50.

    The handler's own level is ``INFO`` by default so it captures the prediction
    INFO logs that the engine already emits. We also raise the logger level to
    ``INFO`` if it is currently unset (``NOTSET``), so subsequent
    ``logger.info(...)`` calls are not silently filtered out before reaching
    the handler.
    """
    handler = StreamlitLogHandler(capacity=capacity)
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
    # Bump logger level if unset so INFO logs reach the handler.
    if logger.level == logging.NOTSET:
        logger.setLevel(logging.INFO)
    _INSTALLED_HANDLERS.append(handler)
    return handler


def add_to_root_logger(capacity: int = DEFAULT_CAPACITY) -> StreamlitLogHandler:
    """Convenience helper: attach a handler to ``logging.getLogger()``."""
    return attach_to(logging.getLogger(), capacity=capacity)


def get_buffer(key: str = SESSION_KEY) -> List[Dict[str, Any]]:
    """Read-only accessor: return the session buffer or an empty list.

    Handy for components that want to render logs without touching
    ``st.session_state`` directly (and to keep the import surface stable
    in tests).
    """
    if st is None:
        return []
    try:
        buf = st.session_state.get(key)
        return list(buf) if buf else []
    except Exception:
        return []


def clear_buffer(key: str = SESSION_KEY) -> None:
    """Clear the session buffer (or no-op when there is no Streamlit runtime)."""
    if st is None:
        return
    try:
        buf = st.session_state.get(key)
        if buf is not None:
            buf.clear()
    except Exception:
        return


__all__ = [
    "DEFAULT_CAPACITY",
    "SESSION_KEY",
    "StreamlitLogHandler",
    "attach_to",
    "add_to_root_logger",
    "get_buffer",
    "clear_buffer",
]
