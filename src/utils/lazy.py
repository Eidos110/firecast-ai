"""
Lazy import helpers for heavy / sandbox-sensitive modules.

Centralises the torch lazy-load pattern so backend modules don't triplicate it
and so Railway/HF Spaces can start up even when PyTorch's native deps cannot be
loaded (e.g. ``libtorch_cpu.so: cannot enable executable stack``).
"""

from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)

_torch_module = None
_torch_nn_module = None
_torch_lock = threading.Lock()


def get_torch():
    """Return ``(torch, torch.nn)`` lazily; ``(None, None)`` if unavailable.

    The first successful import caches both ``torch`` and ``torch.nn`` for
    subsequent calls. Thread-safe via a module lock.
    """
    global _torch_module, _torch_nn_module
    if _torch_module is not None:
        return _torch_module, _torch_nn_module
    with _torch_lock:
        if _torch_module is None:
            try:
                import torch as _t  # type: ignore
                import torch.nn as _nn  # type: ignore

                _torch_module, _torch_nn_module = _t, _nn
            except (ImportError, OSError):
                # Railway: torch execstack blocked or not installed; demo-mode.
                pass
    return _torch_module, _torch_nn_module


def require_torch():
    """Return ``(torch, torch.nn)`` tuple; raise RuntimeError if unavailable.

    Use this in code paths that genuinely cannot continue without torch
    (model loading / inference). For optional paths prefer :func:`get_torch`
    and degrade gracefully.
    """
    torch_mod, nn_mod = get_torch()
    if torch_mod is None or nn_mod is None:
        raise RuntimeError(
            "PyTorch unavailable on this worker. " "ML inference is disabled; run in demo mode."
        )
    return torch_mod, nn_mod
