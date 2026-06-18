"""
FireCast – South Foreplay system
Ensemble: CNN + LightGBM for fire risk prediction
"""

__version__ = "1.0.0"
__author__ = "FireCast Team"

# Lazy safe imports at module level
from . import config          # safe – no torch at top-level any more
from . import utils           # safe – utilities
from . import data_loader     # safe – data loading

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
