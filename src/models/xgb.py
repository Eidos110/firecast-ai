"""
XGBoost model module for FireCast.
Provides functions to load and run XGBoost predictions.
"""

import logging
from pathlib import Path
from typing import Any

import joblib
import numpy as np

logger = logging.getLogger(__name__)


def load_xgb_model(model_path: str | Path) -> Any:
    """
    Load XGBoost model from pickle file.

    Args:
        model_path: Path to the .pkl model file

    Returns:
        Loaded XGBoost model

    Raises:
        FileNotFoundError: If model file doesn't exist
        ValueError: If model cannot be loaded
    """
    model_path = Path(model_path)

    if not model_path.exists():
        raise FileNotFoundError(f"XGBoost model not found at: {model_path}")

    try:
        model = joblib.load(model_path)
        logger.info(f"XGBoost model loaded from {model_path}")
        return model
    except Exception as e:
        raise ValueError(f"Failed to load XGBoost model: {e}")


def predict_xgb(
    model: Any,
    X: np.ndarray,
    use_proba: bool = True,
) -> np.ndarray:
    """
    Run prediction using XGBoost model.

    Args:
        model: Loaded XGBoost model
        X: Input features (n_samples, n_features)
        use_proba: If True, return probability; else return class predictions

    Returns:
        Array of predictions (probability of class 1 if use_proba=True)

    Raises:
        RuntimeError: If prediction fails. We intentionally DO NOT return a
            silent 0.5 fallback — a bogus "Medium" risk label could mask a
            real fire danger (AGENTS.md §3 "Penanganan model ML"). Callers
            (predict.py) wrap this as PredictionError → HTTP 500.
    """
    try:
        if use_proba:
            # predict_proba first — works for XGBClassifier/xgb.XGBModel (sklearn ≥ 2)
            if hasattr(model, "predict_proba"):
                proba = model.predict_proba(X)
                if isinstance(proba, np.ndarray) and proba.ndim > 1 and proba.shape[1] > 1:
                    return proba[:, 1]
                return np.asarray(proba).flatten()
            # Raw margin fallback → sigmoid → [0,1]
            if hasattr(model, "predict"):
                raw = model.predict(X)
                if raw is not None:
                    arr = np.asarray(raw, dtype=float)
                    if arr.min() < -0.1 or arr.max() > 1.1:
                        arr = 1.0 / (1.0 + np.exp(-arr))
                    return np.clip(arr, 0.0, 1.0)
                raise RuntimeError("XGBoost .predict() returned None")

        raise RuntimeError(
            f"Unsupported XGBoost model object {type(model).__name__}: "
            "expected predict_proba() or predict()."
        )

    except Exception as e:
        logger.error("XGBoost prediction failed: %s", e, exc_info=True)
        raise RuntimeError(f"XGBoost prediction failed: {e}") from e


if __name__ == "__main__":
    import logging
    import sys

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    if len(sys.argv) > 1:
        model_path = sys.argv[1]
        model = load_xgb_model(model_path)
        logger.info(f"Model loaded: {type(model)}")

        if len(sys.argv) > 2:
            import numpy as np

            X_test = np.array([[0.1] * 79])
            prob = predict_xgb(model, X_test)
            logger.info(f"Prediction: {prob}")
