"""SHAP-based prediction explaining utilities (audit Fase 3a).

Extracted from :mod:`src.predict` so SHAP logic is unit-testable and so that
callers have a stable, documented entry point. The original
``predict._compute_shap_explanation`` (kept as a thin re-export for backward
compat) remains the production path used internally by predict.py.

This module imports lazily (``shap``, ``pandas``, ``json``) inside the public
function so importing :mod:`src.features.shap_explain` does not pay for those
imports — important on Railway/HF Spaces workers where ``shap`` fails to load.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


def compute_shap_explanation(
    features: dict[str, Any],
    lgbm_model: Any,
    feature_vector: np.ndarray | None = None,
    feature_columns: list | None = None,
    feature_columns_path: str | None = None,
) -> dict[str, Any]:
    """Compute SHAP-based top-features explanation for a single FireCast prediction.

    Args:
        features: Input feature dictionary (fallback if feature_vector not
            provided).
        lgbm_model: Loaded LightGBM model compatible with ``shap.TreeExplainer``.
        feature_vector: Pre-built engineered feature vector (1, n_features).
            Preferred path, faster than re-deriving from features.
        feature_columns: Feature column names aligned to feature_vector.
        feature_columns_path: Optional JSON path containing feature columns.
            Defaults to :attr:`src.config.FEATURE_COLUMNS_PATH` when omitted.

    Returns:
        ``{"top_features": [...], "base_value": float}`` or ``{}`` if SHAP
        cannot be computed (e.g. ``shap`` library missing or samples too few).
    """
    try:
        import pandas as pd
        import shap  # lazy: heavy + may fail with numpy 2.x see requirements.txt

        from src import config

        if feature_vector is not None and feature_columns is not None:
            X = feature_vector
            feature_names = feature_columns
        else:
            df = pd.DataFrame([features])
            cols_path = feature_columns_path or getattr(config, "FEATURE_COLUMNS_PATH", None)
            try:
                if cols_path is None:
                    raise FileNotFoundError("FEATURE_COLUMNS_PATH not set")
                with open(cols_path) as f:
                    loaded_feature_columns = json.load(f)
            except Exception:
                loaded_feature_columns = list(features.keys())
            available_cols = [col for col in loaded_feature_columns if col in df.columns]
            if not available_cols:
                return {}
            X = df[available_cols].values
            feature_names = available_cols

        explainer = shap.TreeExplainer(lgbm_model)
        shap_values = explainer.shap_values(X)

        # Binary classification: TreeExplainer returns list [shap_class_0, shap_class_1];
        # positive class (fire risk = class 1).
        if isinstance(shap_values, list):
            if len(shap_values) == 2:
                shap_values_used = shap_values[1]
                if (
                    hasattr(explainer.expected_value, "__len__")
                    and len(explainer.expected_value) >= 2
                ):
                    base_value = float(explainer.expected_value[1])
                else:
                    base_value = float(explainer.expected_value)
            else:
                shap_values_used = shap_values[1]
                base_value = (
                    explainer.expected_value[1]
                    if hasattr(explainer.expected_value, "__len__")
                    else float(explainer.expected_value)
                )
        else:
            shap_values_used = shap_values
            base_value = float(explainer.expected_value)

        abs_shap = np.abs(shap_values_used[0])
        top_indices = np.argsort(abs_shap)[-5:][::-1]

        top_features = [
            {
                "feature": feature_names[idx],
                "shap_value": float(shap_values_used[0][idx]),
                "contribution": "positive" if shap_values_used[0][idx] > 0 else "negative",
                "importance": float(abs_shap[idx]),
            }
            for idx in top_indices
        ]

        return {"top_features": top_features, "base_value": base_value}
    except Exception as e:
        logger.debug(f"SHAP explanation failed: {e}")
        return {}
