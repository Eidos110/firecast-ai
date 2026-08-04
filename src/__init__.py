"""
FireCast — Fire risk prediction system.

Stacking ensemble (LightGBM + XGBoost + meta-learner) with a legacy
CNN + LightGBM fallback, served via FastAPI + a React SPA.
"""

__version__ = "4.0.0"
__author__ = "FireCast Team"

# Lazy safe imports at module level
from . import (
    config,  # safe – no torch at top-level any more
    data_loader,  # safe – data loading
    utils,  # safe – utilities
)

# Heavy/dependent imports are lazy to survive Railway's sandbox restrictions
# (PyTorch 1.10.2 triggers: libtorch_cpu.so: cannot enable executable stack there)
#   from . import predict
#   from . import database
#   from . import models
#   from . import geo_api

__all__ = [
    "config",
    "utils",
    "data_loader",
]
