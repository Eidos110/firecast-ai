"""Feature-engineering subpackage for single-inference helpers and
SHAP-based explanations (audit Fase 3a — split from ``src/predict.py``).

Modules:
- :mod:`src.features.single_inference` — lag/roll temporal estimation
  and feature vector builder.
- :mod:`src.features.shap_explain`     — SHAP top-features explanation.

Importing this package does NOT pull torch / shap / pandas — those remain
lazy inside the public functions themselves, preserving Railway/HF Spaces
sandbox-safety.
"""

from __future__ import annotations

from .shap_explain import compute_shap_explanation
from .single_inference import (
    create_feature_vector,
    estimate_temporal_feature,
)

__all__ = [
    "create_feature_vector",
    "estimate_temporal_feature",
    "compute_shap_explanation",
]
