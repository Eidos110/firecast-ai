"""
Models package for FireCast
Contains CNN, LightGBM, XGBoost, BiGRU, CausalGRU, and ensemble implementations

IMPORTANT: Model modules (cnn, lgbm, xgb, bigru, causal_gru) are NOT eagerly imported
here because they import torch at module level, which fails on Railway's sandbox
(libtorch_cpu.so: cannot enable executable stack).

Instead, use lazy_import() from each submodule where needed, or import them directly
with a try/except at the call site.
"""

# Registry and utilities — safe to import eagerly
from . import registry

__all__ = [
    "registry",
    # Rest are imported lazily where needed:
    # "TunedCNN1D", "load_cnn_model",
    # "load_lgbm_model", "load_xgb_model", "predict_xgb",
    # "BiGRUModel", "load_bigru_model", "predict_bigru",
    # "CausalGRUWithAttention", "load_causal_gru_model", "predict_causal_gru",
    # "evaluate_ensemble",
]
