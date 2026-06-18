"""
FireCast Lite Launcher
Patches PyTorch execstack issue on Railway, then launches the app.
"""
import subprocess
import os
import sys
import logging

logger = logging.getLogger(__name__)

def _patch_libtorch():
    """Patch libtorch_cpu.so with execstack to allow executable stack on Railway."""
    lib_paths = [
        "/usr/local/lib/python3.9/site-packages/torch/lib/libtorch_cpu.so",
    ]
    for lib in lib_paths:
        if os.path.exists(lib):
            # Try patchelf first (more reliable)
            try:
                result = subprocess.run(
                    ["patchelf", "--set-interpreter", "/lib64/ld-linux-x86-64.so.2", lib],
                    capture_output=True, text=True, timeout=5
                )
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
    return True


def main():
    """Launch FireCast API with torch compatibility patch."""
    _patch_libtorch()

    # Set LD_PRELOAD to inject comp
    torch_lib = "/usr/local/lib/python3.9/site-packages/torch/lib/libtorch_cpu.so"
    os.environ["LD_PRELOAD"] = torch_lib
    os.environ["LD_LIBRARY_PATH"] = (
        "/usr/local/lib/python3.9/site-packages/torch/lib:"
        + os.environ.get("LD_LIBRARY_PATH", "")
    )

    import uvicorn
    uvicorn.run(
        "src.geo_api:app",
        host=os.getenv("API_HOST", "0.0.0.0"),
        port=int(os.getenv("API_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
