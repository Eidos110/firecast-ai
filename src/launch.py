"""
FireCast Lite Launcher
======================
Patches the PyTorch ``libtorch_cpu.so`` executable-stack issue on Railway /
EL-based Linux distros, then launches the FastAPI app via uvicorn.

This file is **optional** — ``start_api.py`` is the primary entry point and
works on every platform (win/linux/mac, with-or-without torch). ``launch.py``
only adds the Railway ld-preload hack for the ELHosting torch wheel that ships
with an executable-stack flag Railway's hardened kernel rejects.

Portable torch path discovery
-----------------------------
The previous implementation hard-coded
``/usr/local/lib/python3.9/site-packages/torch/lib/libtorch_cpu.so``, which
breaks the moment the runtime Python (currently 3.12 in this repo's conda env
and the Dockerfile) does not match that path. We now resolve the library path
dynamically from ``torch.__file__`` so this stays correct across Python
versions. If torch is not importable (CPU-only sandbox without the wheel), the
patch step is silently skipped — the downstream uvicorn call will surface a
clear error instead.
"""

import contextlib
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def _resolve_libtorch_path() -> str | None:
    """Locate ``libtorch_cpu.so`` from the installed torch package.

    Returns ``None`` when torch is unavailable or the library file is missing
    (e.g. CPU-only wheels on Windows ships a ``.dll`` / ``.pyd``). The caller
    treats ``None`` as "skip the ld-preload hack".
    """
    try:
        import torch  # noqa: PLC0415 — lazy on purpose
    except ImportError:
        logger.info("torch not importable — skipping libtorch patch step")
        return None

    torch_lib_dir = Path(torch.__file__).parent / "lib"
    candidate = torch_lib_dir / "libtorch_cpu.so"
    if not candidate.exists():
        # Windows / macos wheels do not ship this .so — nothing to patch.
        logger.debug("libtorch_cpu.so not found at %s — nothing to patch", candidate)
        return None
    return str(candidate)


def _patch_libtorch(lib_path: str) -> bool:
    """Patch libtorch_cpu.so with execstack to allow an executable stack.

    Used only on hardened EL kernels (Railway) that reject the wheel's default
    PT_GNU_STACK marker. No-op on platforms without ``patchelf``.
    """
    with contextlib.suppress(FileNotFoundError, subprocess.TimeoutExpired):
        subprocess.run(
            ["patchelf", "--set-interpreter", "/lib64/ld-linux-x86-64.so.2", lib_path],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    return True


def main():
    """Launch FireCast API with optional torch compatibility patch."""
    lib_path = _resolve_libtorch_path()
    if lib_path is not None:
        _patch_libtorch(lib_path)
        os.environ["LD_PRELOAD"] = lib_path
        lib_dir = os.path.dirname(lib_path)
        os.environ["LD_LIBRARY_PATH"] = lib_dir + ":" + os.environ.get("LD_LIBRARY_PATH", "")

    import uvicorn  # noqa: PLC0415 — lazy import keeps cold-start light

    uvicorn.run(
        "src.geo_api:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
    )


if __name__ == "__main__":
    sys.exit(main())
