"""Lightweight, sandbox-safe request-level caching helpers.

Audit priority 2 — avoids double-compute for /predict, /weather, and other
read-heavy endpoints that may be hit repeatedly with the same arguments
inside the same Python process (e.g. during a Streamlit rerun storm or a
load-balanced worker reuse). All caches here are bounded TTL caches so they
do not grow unbounded across long-running workers.

This module MUST be import-safe without optional dependencies:
- ``cachetools`` is in ``requirements.txt`` (alphabetical dependency, not
  in the slow-import set), but we still guard with ``try/except`` so that
  a fresh sandbox without the wheel keeps the API functional (degraded
  to "no cache" rather than 500).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

try:
    from cachetools import TTLCache  # type: ignore[import-not-found]

    _HAS_CACHETOOLS = True
except Exception:  # pragma: no cover — sandbox without cachetools
    _HAS_CACHETOOLS = False
    logger.warning(
        "cachetools unavailable — request caches disabled (degraded throughput). "
        "Install requirements.txt to enable."
    )


# ---------------------------------------------------------------------------
# A small bounded TTL cache for *scalar/hashable* prediction payloads.
# 256 slots × 5-minute TTL is enough to absorb a typical AOI rerun burst
# (most fire-risk requests share the same lat/lon/weather slice during a
# single Streamlit session) without masking genuine weather drift.
# ---------------------------------------------------------------------------
_PRED_CACHE_MAX_SLOTS = 256
_PRED_CACHE_TTL_SEC = 300  # 5 minutes


def _make_cache(maxsize: int, ttl: int) -> Any | None:
    """Return a fresh ``TTLCache`` or ``None`` if cachetools missing."""
    if not _HAS_CACHETOOLS:
        return None
    return TTLCache(maxsize=maxsize, ttl=ttl)


_prediction_cache: Any | None = _make_cache(_PRED_CACHE_MAX_SLOTS, _PRED_CACHE_TTL_SEC)


def _stable_hash(value: Any) -> int:
    """Render any JSON-ish (or numpy) value into a stable numeric hash.

    ``hash()`` on a ``dict`` is non-deterministic across Python processes
    (PYTHONHASHSEED), so we fall back to ``repr`` + ``hashlib``. The hash
    is only used as an in-process cache key; it does not need to be
    cryptographically strong — it just needs to be the same for equal
    inputs within a worker lifetime.
    """
    import hashlib

    payload = repr(value).encode("utf-8", errors="ignore")
    # Shake-128 truncated to 16 bytes keeps the key small and fast.
    return int.from_bytes(hashlib.shake_128(payload).digest(16), "big")


def cache_get(key_value: Any) -> tuple[bool, Any]:
    """Return ``(hit, value)``.

    ``hit=False`` means the caller should recompute and store via
    :func:`cache_set`. The cache is *advisory* — a miss never raises.
    """
    if _prediction_cache is None:
        return False, None
    try:
        key = _stable_hash(key_value)
    except Exception:  # pragma: no cover — defensive, repr is very tolerant
        return False, None
    if key in _prediction_cache:
        return True, _prediction_cache[key]
    return False, None


def cache_set(key_value: Any, result: Any) -> None:
    """Store ``result`` under the stable hash of ``key_value``.

    Failures are swallowed: caching is best-effort and must never break
    a prediction request.
    """
    if _prediction_cache is None:
        return
    try:
        key = _stable_hash(key_value)
        # Bound stored size — if a caller tries to cache something huge
        # (e.g. a shap array per-feature for a 10k-point AOI) we evict
        # instead of growing unbounded. cachetools already bounds by slot
        # count, but a single slot can still hold >100 MB; clamp to a
        # reasonable byte budget by skipping oversized payloads.
        size = _approx_size(result)
        if size > 8_000_000:  # 8 MB hard cap per cached value
            logger.debug("Skipping cache set: payload ~%.1f MB > 8 MB cap", size / 1e6)
            return
        _prediction_cache[key] = result
    except Exception as e:  # pragma: no cover — never raise on cache write
        logger.debug("cache_set failed (ignored): %s", e)


def _approx_size(obj: Any) -> int:
    """Rough byte-size estimate for a JSON-serialisable object."""
    try:
        import sys

        total = sys.getsizeof(obj, 0)
        if isinstance(obj, dict):
            for v in obj.values():
                total += _approx_size(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                total += _approx_size(v)
        return total
    except Exception:
        return 0


def cache_clear() -> int:
    """Drop all cached entries. Returns the number of slots freed."""
    if _prediction_cache is None:
        return 0
    n = len(_prediction_cache)
    _prediction_cache.clear()
    return n


def cache_stats() -> dict[str, Any]:
    """Return a small snapshot for the admin endpoint."""
    if _prediction_cache is None:
        return {"enabled": False, "size": 0, "maxsize": 0, "ttl_seconds": 0}
    return {
        "enabled": True,
        "size": len(_prediction_cache),
        "maxsize": _PRED_CACHE_MAX_SLOTS,
        "ttl_seconds": _PRED_CACHE_TTL_SEC,
    }


# ---------------------------------------------------------------------------
# Decorator form for clean opt-in at the call site.
# ---------------------------------------------------------------------------
def cached(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: memoise ``func`` by hashing ``args+kwargs``.

    Use only on side-effect-free functions whose return value is JSON-ish
    (dict/list/number/str — no numpy arrays). Good for ``run_prediction``
    wrappers in the frontend tier; do NOT apply to functions that mutate
    model state or that rely on Streamlit session_state.
    """

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        key = (func.__qualname__, args, sorted(kwargs.items()))
        hit, value = cache_get(key)
        if hit:
            return value
        value = func(*args, **kwargs)
        cache_set(key, value)
        return value

    wrapper.__wrapped__ = func  # type: ignore[attr-defined]
    wrapper.__name__ = getattr(func, "__name__", "cached_wrapper")
    wrapper.__doc__ = func.__doc__
    return wrapper


__all__ = [
    "cache_clear",
    "cache_get",
    "cache_set",
    "cache_stats",
    "cached",
]
