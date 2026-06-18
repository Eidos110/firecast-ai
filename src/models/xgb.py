"""
XGBoost model module for FireCast.
Provides functions to load and run XGBoost predictions.
"""

import logging
from pathlib import Path
from typing import Optional, Union

import numpy as np
import joblib

logger = logging.getLogger(__name__)


def load_xgb_model(model_path: Union[str, Path]) -> any:
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
    model: any,
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
    """
    n = X.shape[0] if hasattr(X, "shape") else len(X)
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

        return model.predict(X)

    except Exception as e:
        logger.warning(f"XGBoost prediction error: {e}. Using neutral 0.5 fallback.")
        return np.full(n, 0.5, dtype=float)


if __name__ == "__main__":
    import sys
    import logging
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
