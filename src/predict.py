"""
FireCast Prediction Module
==========================
Functions for running fire risk predictions using the ensemble model.
"""

import json
import logging
import math
import os
import pickle
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional, Union
from pathlib import Path

import numpy as np
import pandas as pd
import joblib
from sklearn.preprocessing import StandardScaler

from src import config
from src.data_loader import load_data_for_evaluation
from src.feature_engineering import engineer_features
import sys  # for module-global scope access in _init_models()

# ── Lazy torch / model imports ──
# Railway/CPU envs: PyTorch 1.10.2 fails with
# "libtorch_cpu.so: cannot enable executable stack".
# We use lazy imports so the app still starts (in demo mode).
# Call _init_models() before calling predict functions.

_torch = None
_cnn_module = None


def _get_torch():
    """Return torch module lazily. Returns None if unavailable (Railway)."""
    global _torch
    if _torch is None:
        try:
            import torch as _t
            _torch = _t
        except ImportError:
            pass  # Railway execstack restriction
    return _torch


def _init_models():
    """Load all ML model implementations (lazy, fail-safe).

    Returns True if all models loaded, False otherwise (falls back to demo).
    When successful, registers the loaders in module globals so that
    load_ensemble_models() and load_stacking_models() can use them directly.
    """
    _mod = sys.modules[__name__]
    try:
        from src.models.cnn import TunedCNN1D, load_cnn_model  # noqa: F401
        from src.models.lgbm import load_lgbm_model             # noqa: F401
        from src.models.xgb import load_xgb_model, predict_xgb  # noqa: F401
        from src.models.bigru import load_bigru_model, predict_bigru  # noqa: F401
        from src.models.causal_gru import load_causal_gru_model, predict_causal_gru  # noqa: F401
        from src.models.ensemble import evaluate_ensemble       # noqa: F401
        # Register in module globals so outer functions can find them
        _mod.load_cnn_model = load_cnn_model
        _mod.load_lgbm_model = load_lgbm_model
        _mod.load_xgb_model = load_xgb_model
        _mod.predict_xgb = predict_xgb
        _mod.load_bigru_model = load_bigru_model
        _mod.predict_bigru = predict_bigru
        _mod.load_causal_gru_model = load_causal_gru_model
        _mod.predict_causal_gru = predict_causal_gru
        _mod.evaluate_ensemble = evaluate_ensemble
    except Exception as e:
        logging.getLogger(__name__).warning(
            f"Model loading failed (likely PyTorch unavailability on Railway): {e}. "
            "Falling back to demo mode."
        )
        return False
    return True

logger = logging.getLogger(__name__)

# Weighted ensemble weights for LGBM+XGB (computed from validation AUCs)
# From notebook: LGBM AUC=0.8834, XGB AUC=0.8855
_WEIGHTS_LGBM_XGB = np.array([0.8834, 0.8855])
_WEIGHTS_LGBM_XGB = _WEIGHTS_LGBM_XGB / _WEIGHTS_LGBM_XGB.sum()

# Flag to enable/disable Causal GRU for AOI predictions (no historical data).
# Set environment variable USE_CAUSAL_GRU_AOI=false to force disable (fall back to LGBM+XGB).
USE_CAUSAL_GRU_AOI = os.getenv('USE_CAUSAL_GRU_AOI', 'true').lower() != 'false'

# Backward compatibility alias
USE_BIGRU_AOI = os.getenv('USE_BIGRU_AOI', os.getenv('USE_CAUSAL_GRU_AOI', 'true')).lower() != 'false'


def _safe_divide(numerator: Union[float, np.ndarray], denominator: Union[float, np.ndarray], epsilon: float = 1e-8) -> Union[float, np.ndarray]:
    """
    Safe division to prevent division by zero and numerical overflow.
    
    Args:
        numerator: Numerator value(s)
        denominator: Denominator value(s)
        epsilon: Small value to add to denominator for numerical stability
        
    Returns:
        Result of numerator / (denominator + epsilon), clipped to prevent infinities.
    """
    safe_denom = denominator + epsilon
    result = numerator / safe_denom
    # Clip extreme values to prevent inf/nan propagation
    if isinstance(result, np.ndarray):
        return np.clip(result, -1e10, 1e10)
    else:
        return max(min(result, 1e10), -1e10)


class PredictionError(Exception):
    """Custom exception for prediction errors."""

    pass


class ModelLoadError(Exception):
    """Custom exception for model loading errors."""

    pass


# Registry for model version management – safe (registry.py has no torch import)
from src.models import registry

# ── End of safe module-level imports ──


def load_ensemble_models(
    input_dim: int, version: Optional[str] = None
) -> Tuple[Any, Any]:
    """
    Load both CNN and LightGBM models.

    Args:
        input_dim: Number of input features for CNN
        version: Optional model version string. If None, loads active version.

    Returns:
        Tuple of (cnn_model, lgbm_model)

    Raises:
        ModelLoadError: If models cannot be loaded
    """
    # Lazy import: avoid top-level import of torch
    try:
        from src.models.cnn import load_cnn_model  # noqa
        from src.models.lgbm import load_lgbm_model  # noqa
    except ImportError as e:
        raise ModelLoadError(
            f"Cannot import model loaders (torch unavailable on Railway?): {e}"
        )

    # Try registry first, fallback to direct paths if not found
    try:
        cnn_path = registry.get_model_path("cnn", version)
        lgbm_path = registry.get_model_path("lgbm", version)
    except Exception:
        cnn_path = None
        lgbm_path = None

    # Fallback to direct paths if registry returns None
    if not cnn_path:
        cnn_path = config.CNN_MODEL_PATH
    if not lgbm_path:
        lgbm_path = config.LGBM_MODEL_PATH

    try:
        logger.info(f"Loading CNN model from {cnn_path}")
        cnn_model = load_cnn_model(input_dim, model_path=cnn_path)
        logger.info("CNN model loaded successfully")
    except Exception as e:
        raise ModelLoadError(f"Failed to load CNN model: {e}")

    try:
        logger.info(f"Loading LightGBM model from {lgbm_path}")
        lgbm_model = load_lgbm_model(model_path=lgbm_path)
        logger.info("LightGBM model loaded successfully")
    except Exception as e:
        raise ModelLoadError(f"Failed to load LightGBM model: {e}")

    return cnn_model, lgbm_model


def load_stacking_models(
    input_dim: int = 79, raw_feature_indices: Optional[list] = None
) -> Tuple[Any, Any, Any, Any, Any, Any, Any, Optional[np.ndarray]]:
    """
    Load new stacking model components (LightGBM, XGBoost, Causal GRU, Meta-learner, scaler_raw, meta_scaler, raw_feature_indices).

    Args:
        input_dim: Number of input features (default 79 for new model)
        raw_feature_indices: List of column indices for raw features (needed for GRU). If None,
                             will be loaded from raw_features.json and mapped to indices.

    Returns:
        Tuple of (lgbm_model, xgb_model, causal_gru_model, meta_model, scaler_raw, meta_scaler, raw_feature_indices, nnls_weights)
        where nnls_weights is a numpy array of shape (3,) with weights [GRU, LGBM, XGB] or None if not available.

    Raises:
        ModelLoadError: If models cannot be loaded
    """
    # Lazy imports: mirrors load_ensemble_models() so _init_models() is not
    # a runtime dependency. Without these, the bare call at lines 277/283/291
    # raises a NameError when _init_models() has not yet run.
    try:
        from src.models.lgbm import load_lgbm_model  # noqa: F401
        from src.models.xgb import load_xgb_model, predict_xgb  # noqa: F401
        from src.models.causal_gru import load_causal_gru_model, predict_causal_gru  # noqa: F401
    except ImportError as _e:
        raise ModelLoadError(
            f"Cannot import stacking model loaders (torch/model deps missing?): {_e}"
        )
    # Register in module globals so predict_stacking / other functions can find them
    _mod = sys.modules[__name__]
    _mod.load_lgbm_model = load_lgbm_model
    _mod.load_xgb_model = load_xgb_model
    _mod.predict_xgb = predict_xgb
    _mod.load_causal_gru_model = load_causal_gru_model
    _mod.predict_causal_gru = predict_causal_gru

    # Load raw feature indices if not provided
    if raw_feature_indices is None:
        try:
            with open(config.NEW_RAW_FEATURES_PATH, 'r', encoding='utf-8') as f:
                raw_features = json.load(f)
            # Validate raw_features structure
            if not isinstance(raw_features, list):
                raise ValueError("raw_features.json must contain a JSON array")
            if not all(isinstance(item, str) for item in raw_features):
                raise ValueError("raw_features.json array items must be strings")
            # Load feature columns to map names to integer indices
            try:
                with open(config.NEW_FEATURE_COLUMNS_PATH, 'r', encoding='utf-8') as f:
                    feature_columns = json.load(f)
                # Validate feature_columns structure
                if not isinstance(feature_columns, list):
                    raise ValueError("feature_columns.json must contain a JSON array")
                if not all(isinstance(item, str) for item in feature_columns):
                    raise ValueError("feature_columns.json array items must be strings")
                # Convert raw feature names to column indices
                raw_feature_indices = [
                    i for i, col in enumerate(feature_columns) if col in raw_features
                ]
                logger.info(
                    f"Mapped {len(raw_features)} raw features to {len(raw_feature_indices)} column indices"
                )
                if len(raw_feature_indices) != len(raw_features):
                    logger.warning(
                        f"Some raw features missing from feature_columns: "
                        f"expected {len(raw_features)}, got {len(raw_feature_indices)}"
                    )
            except (FileNotFoundError, PermissionError, json.JSONDecodeError, OSError) as e:
                logger.warning(f"Could not load feature_columns.json: {e}. Using sequential indices.")
                # Fallback: assign sequential indices (may be wrong but allows model to load)
                raw_feature_indices = list(range(len(raw_features)))
        except (FileNotFoundError, PermissionError, json.JSONDecodeError, OSError) as e:
            logger.warning(f"Could not load raw_features.json: {e}. Using first {input_dim} features.")
            raw_feature_indices = list(range(input_dim))

    # Determine causal_gru_input_dim from model_config.json (Bug #5 fix)
    causal_gru_input_dim = None
    causal_gru_hidden1 = 64
    causal_gru_dropout = 0.3
    try:
        with open(Path(config.NEW_MODEL_DIR) / "model_config.json", 'r', encoding='utf-8') as f:
            model_config = json.load(f)
            if not isinstance(model_config, dict):
                raise ValueError("model_config.json must be a JSON object")
            causal_gru_config = model_config.get("causal_gru_config", {})
            if not isinstance(causal_gru_config, dict):
                raise ValueError("causal_gru_config must be a JSON object")
            causal_gru_input_dim = causal_gru_config.get("input_dim", 19)
            causal_gru_hidden1 = causal_gru_config.get("hidden1", 64)
            causal_gru_dropout = causal_gru_config.get("dropout_rate", 0.3)
            # Validate types
            if not isinstance(causal_gru_input_dim, int) or causal_gru_input_dim <= 0:
                raise ValueError("causal_gru_input_dim must be a positive integer")
            if not isinstance(causal_gru_hidden1, int) or causal_gru_hidden1 <= 0:
                raise ValueError("causal_gru_hidden1 must be a positive integer")
            if not isinstance(causal_gru_dropout, (int, float)) or not (0 <= causal_gru_dropout <= 1):
                raise ValueError("causal_gru_dropout must be a number between 0 and 1")
            logger.info(f"Causal GRU input dimension from config: {causal_gru_input_dim}")
    except (FileNotFoundError, PermissionError, json.JSONDecodeError, OSError, KeyError, TypeError) as e:
        logger.warning(f"Could not read model_config.json: {e}. Using default input_dim=19.")
        causal_gru_input_dim = 19

    try:
        logger.info(f"Loading new LGBM model from {config.NEW_LGBM_MODEL_PATH}")
        lgbm_model = load_lgbm_model(model_path=config.NEW_LGBM_MODEL_PATH)
        logger.info("LGBM model loaded successfully")
    except Exception as e:
        raise ModelLoadError(f"Failed to load LGBM model: {e}")

    try:
        logger.info(f"Loading new XGB model from {config.NEW_XGB_MODEL_PATH}")
        xgb_model = load_xgb_model(model_path=config.NEW_XGB_MODEL_PATH)
        logger.info("XGB model loaded successfully")
    except Exception as e:
        raise ModelLoadError(f"Failed to load XGB model: {e}")

    try:
        logger.info(f"Loading new Causal GRU model from {config.NEW_CAUSAL_GRU_MODEL_PATH}")
        causal_gru_model = load_causal_gru_model(
            causal_gru_input_dim,
            config.NEW_CAUSAL_GRU_MODEL_PATH,
            hidden1=causal_gru_hidden1,
            dropout_rate=causal_gru_dropout,
        )
        logger.info("New Causal GRU model loaded successfully")
    except Exception as e:
        raise ModelLoadError(f"Failed to load new Causal GRU model: {e}")

    try:
        logger.info(f"Loading meta-learner from {config.NEW_META_MODEL_PATH}")
        meta_model = joblib.load(config.NEW_META_MODEL_PATH)
        logger.info("Meta-learner loaded successfully")

        # Validate meta_model type and shape
        if isinstance(meta_model, np.ndarray):
            if meta_model.shape != (3,):
                raise ModelLoadError(
                    f"Meta-learner NNLS weights have wrong shape: {meta_model.shape}, expected (3,)"
                )
            logger.info(
                f"Meta-learner type: NNLS weights array "
                f"(GRU={meta_model[0]:.3f}, LGBM={meta_model[1]:.3f}, XGB={meta_model[2]:.3f})"
            )
        elif hasattr(meta_model, "predict_proba"):
            # LogisticRegression / LogisticRegressionCV
            model_type_name = meta_model.__class__.__name__
            if hasattr(meta_model, "coef_"):
                coef = meta_model.coef_[0]
                logger.info(
                    f"Meta-learner type: {model_type_name} "
                    f"(coefs: GRU={coef[0]:.3f}, LGB={coef[1]:.3f}, XGB={coef[2]:.3f}, "
                    f"intercept={meta_model.intercept_[0]:.3f})"
                )
            else:
                logger.info(f"Meta-learner type: {model_type_name}")
        else:
            raise ModelLoadError(
                f"Unsupported meta-learner type: {type(meta_model).__name__}. "
                f"Expected numpy array (NNLS weights) or sklearn model with predict_proba."
            )
    except ModelLoadError:
        raise
    except Exception as e:
        raise ModelLoadError(f"Failed to load meta-learner: {e}")

    try:
        logger.info(f"Loading new scaler_raw from {config.NEW_SCALER_RAW_PATH}")
        scaler_raw = joblib.load(config.NEW_SCALER_RAW_PATH)
        logger.info("New raw scaler loaded successfully")
    except Exception as e:
        raise ModelLoadError(f"Failed to load new raw scaler: {e}")

    # Meta-scaler removed to prevent prediction saturation
    meta_scaler = None

    # Try to load NNLS weights (alternative meta-learner)
    # These are pre-computed non-negative least squares weights from training
    nnls_weights = None
    nnls_weights_path = Path(config.NEW_MODEL_DIR) / "nnls_weights.npy"
    if os.path.exists(nnls_weights_path):
        try:
            nnls_weights = np.load(nnls_weights_path)
            if nnls_weights.shape == (3,):
                logger.info(f"NNLS weights loaded: GRU={nnls_weights[0]:.3f}, LGBM={nnls_weights[1]:.3f}, XGB={nnls_weights[2]:.3f}")
            else:
                logger.warning(f"NNLS weights have wrong shape {nnls_weights.shape}, ignoring.")
                nnls_weights = None
        except (OSError, ValueError, np.lib.format.ReadError) as e:
            logger.warning(f"Could not load NNLS weights: {e}")
            nnls_weights = None
    else:
        logger.debug("NNLS weights not found (optional - uses LogisticRegression instead)")

    # Temperature scaling factor to temper overconfident predictions
    # Applied to sigmoid output: p_tempered = p ** (1/T) for T>1 reduces confidence
    # Alternatively: convert to logit, divide by temp, sigmoid back.
    INFERENCE_TEMPERATURE = float(os.getenv('INFERENCE_TEMPERATURE', '1.0'))
    if INFERENCE_TEMPERATURE != 1.0:
        logger.info(f"Inference temperature scaling enabled: T={INFERENCE_TEMPERATURE}")

    return lgbm_model, xgb_model, causal_gru_model, meta_model, scaler_raw, meta_scaler, raw_feature_indices, nnls_weights


def load_new_model_scaler():
    """Load scaler for new model."""
    return joblib.load(config.NEW_SCALER_PATH)


def load_new_model_threshold() -> float:
    """Load optimal threshold for new model."""
    with open(config.NEW_THRESHOLD_PATH, "r") as f:
        threshold_config = json.load(f)
    return threshold_config.get("optimal_threshold", 0.5)


def load_new_feature_columns() -> list:
    """Load feature columns for new model."""
    with open(config.NEW_FEATURE_COLUMNS_PATH, "r") as f:
        return json.load(f)


def predict_batch(
    X: np.ndarray,
    cnn_model: Optional[Any] = None,
    lgbm_model: Optional[Any] = None,
    batch_size: int = 64,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Run batch prediction using ensemble model (legacy).

    Args:
        X: Input features (n_samples, n_features)
        cnn_model: Pre-loaded CNN model (optional)
        lgbm_model: Pre-loaded LightGBM model (optional)
        batch_size: Batch size for CNN inference

    Returns:
        Tuple of (cnn_probs, lgbm_probs)
    """
    if cnn_model is None or lgbm_model is None:
        cnn_model, lgbm_model = load_ensemble_models(X.shape[1])

    logger.info(f"Input X shape: {X.shape}")

    # CNN Prediction
    cnn_probs = []
    try:
        logger.info("Running CNN prediction...")
        cnn_model.eval()
        _torch = _get_torch()
        if _torch is None:
            raise RuntimeError("PyTorch not available — cannot run CNN prediction")
        with _torch.no_grad():
            for i in range(0, len(X), batch_size):
                batch = _torch.tensor(X[i : i + batch_size], dtype=_torch.float32).to(
                    config.DEVICE
                )
                logits = cnn_model(batch)
                probs = _torch.sigmoid(logits).cpu().numpy()
                logger.info(
                    f"CNN batch logits: {logits[:3].cpu().numpy()}, probs: {probs[:3]}"
                )
                cnn_probs.extend(probs)
        cnn_probs = np.array(cnn_probs).flatten()
        logger.info(f"CNN final probs: {cnn_probs[:5]}")

        # Apply MORE AGGRESSIVE calibration to CNN if predictions are near zero
        # The model seems to output very low values, so we need to scale up significantly
        cnn_mean = cnn_probs.mean()
        logger.info(f"CNN mean probability: {cnn_mean:.6f}")

        if cnn_mean < 0.1:
            # Very aggressive scaling for near-zero predictions
            # Map 0.0-0.1 to 0.1-0.5 range
            cnn_calibrated = cnn_probs * 5.0 + 0.1
            cnn_calibrated = np.clip(cnn_calibrated, 0.0, 1.0)
            cnn_probs = cnn_calibrated
            logger.info(f"CNN AGGRESSIVE CALIBRATED: {cnn_probs[:5]}")
        elif cnn_mean < 0.25:
            # Moderate scaling for low predictions
            # Map 0.0-0.25 to 0.1-0.6 range
            cnn_calibrated = cnn_probs * 2.0 + 0.1
            cnn_calibrated = np.clip(cnn_calibrated, 0.0, 1.0)
            cnn_probs = cnn_calibrated
            logger.info(f"CNN CALIBRATED: {cnn_probs[:5]}")
    except Exception as e:
        logger.error(f"CNN prediction failed: {e}")
        raise PredictionError(f"CNN prediction failed: {e}")

    # LightGBM Prediction
    lgbm_probs = None
    try:
        logger.info("Running LightGBM prediction...")
        lgbm_probs = lgbm_model.predict(X)
        logger.info(f"LightGBM raw predictions: {lgbm_probs[:5]}")

        # Apply calibration if LightGBM predictions are too extreme
        lgbm_mean = lgbm_probs.mean()
        logger.info(f"LightGBM mean probability: {lgbm_mean:.6f}")

        if lgbm_mean > 0.75:
            # Too high - scale down
            lgbm_calibrated = np.where(
                lgbm_probs > 0.5, 0.5 + (lgbm_probs - 0.5) * 0.7, lgbm_probs * 0.85
            )
            lgbm_probs = np.clip(lgbm_calibrated, 0.0, 1.0)
            logger.info(f"LightGBM CALIBRATED (high): {lgbm_probs[:5]}")
        elif lgbm_mean < 0.1:
            # Too low - scale up similar to CNN
            lgbm_calibrated = lgbm_probs * 5.0 + 0.1
            lgbm_probs = np.clip(lgbm_calibrated, 0.0, 1.0)
            logger.info(f"LightGBM CALIBRATED (low): {lgbm_probs[:5]}")
    except (AttributeError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(
            f"predict_batch: LightGBM .predict() raised {type(e).__name__}: {e}. "
            "Falling back to _safe_lgbm_predict helper."
        )
        lgbm_probs = _safe_lgbm_predict(lgbm_model, X, cnn_probs)

    # Ensure probabilities are in valid range
    cnn_probs = np.clip(cnn_probs, 0.0, 1.0)
    lgbm_probs = np.clip(lgbm_probs, 0.0, 1.0)

    return cnn_probs, lgbm_probs


def load_meta_scaler() -> Any:
    """Load scaler for meta-features (used by LogisticRegression meta-learner)."""
    return joblib.load(config.NEW_META_SCALER_PATH)


# ---------------------------------------------------------------------------
# LGBM-safe prediction helper
# ---------------------------------------------------------------------------

def _safe_lgbm_predict(lgbm_model: Any, X: np.ndarray, cnn_probs: np.ndarray) -> np.ndarray:
    """
    Predict fire-risk probabilities from a LightGBM model, handling *every*
    variant of model object that may be deserialised from ``lgb_model.pkl``.

    Variants covered
    ----------------
    ① Native ``lightgbm.Booster`` (saved with ``joblib`` / ``pickle``)
       → ``Booster.predict()`` returns *raw margins*.  Apply logistic sigmoid
       to convert to probabilities in [0, 1].
    ② ``LGBMClassifier`` / ``LGBMModel`` (sklearn-compatible wrapper)
       → ``.predict_proba()`` returns probabilities directly.
    ③ Any object with a ``predict()`` that returns a 1-D probability array
       → assume values already in [0, 1].

    Falls back to /zero-array-when-available`` when lgbm_model is unusable.
    IMPORTANT: Never returns None so that callers can always call .min() etc.
    """
    n_samples = X.shape[0] if hasattr(X, "shape") else len(X)

    # ── Detect model type ────────────────────────────────────────────────
    _lgbm_mod_name = type(lgbm_model).__name__.lower() if lgbm_model is not None else ""

    try:
        # ── Path A: native lightgbm.Booster — direct raw→sigmoid pipeline ──
        try:
            from lightgbm import Booster as _LGBBooster
            is_booster = isinstance(lgbm_model, _LGBBooster)
        except ImportError:
            is_booster = False

        if is_booster:
            raw = lgbm_model.predict(X)
            if raw is None:
                raise RuntimeError("Booster.predict() returned None")
            # Booster.predict returns raw margins → sigmoid → [0,1]
            if np.issubdtype(np.asarray(raw).dtype, np.floating):
                probs = 1.0 / (1.0 + np.exp(-np.asarray(raw, dtype=float)))
            else:
                probs = np.clip(np.asarray(raw, dtype=float), 0.0, 1.0)
            logger.info(
                f"LGBM Booster → raw margin range [{probs.min():.4f}, {probs.max():.4f}]"
            )
            return np.clip(probs, 0.0, 1.0)

        # ── Path B: sklearn-compatible LGBMClassifier / wrapper ───────────
        # predict_proba first (avoids sklearn 2.0+ predict→predict_proba→handle bug)
        if hasattr(lgbm_model, "predict_proba"):
            try:
                proba = lgbm_model.predict_proba(X)
                return np.asarray(proba[:, 1], dtype=float)
            except Exception:
                pass  # fall through to raw predict()

        # ── Path C: generic objects with .predict() ────────────────────────
        if hasattr(lgbm_model, "predict"):
            raw = lgbm_model.predict(X)
            if raw is not None:
                arr = np.asarray(raw, dtype=float)
                # heuristics: negative or large values → sigmoid; already [0,1] → clip
                if arr.min() < -0.1 or arr.max() > 1.1:
                    arr = 1.0 / (1.0 + np.exp(-arr))
                return np.clip(arr, 0.0, 1.0)

    except Exception as e:
        logger.warning(
            f"_safe_lgbm_predict: all LGBM prediction paths failed ({e!r}). "
        )

    # ── Universal fallback: neutral 0.5 probabilities ────────────────────
    logger.warning(
        "LightGBM prediction failed entirely. "
        "Using neutral 0.5 fallback (results may be unreliable)."
    )
    return np.full(n_samples, 0.5, dtype=float)


def predict_stacking(
    X: np.ndarray,
    lgbm_model: Optional[Any] = None,
    xgb_model: Optional[Any] = None,
    causal_gru_model: Optional[Any] = None,
    meta_model: Optional[Any] = None,
    scaler_raw: Optional[Any] = None,
    meta_scaler: Optional[Any] = None,
    raw_feature_indices: Optional[list] = None,
    use_causal_gru: bool = True,
    seq_len: int = 7,
    nnls_weights: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Run batch prediction using new stacking model (LGB + XGB + Causal GRU + NNLS meta).

    IMPORTANT: The Causal GRU requires raw features (not engineered). This function
    will extract raw features from X using raw_feature_indices.

    Args:
        X: Input features (n_samples, n_features) - ALL engineered features
        lgbm_model: Pre-loaded LightGBM model (optional)
        xgb_model: Pre-loaded XGBoost model (optional)
        causal_gru_model: Pre-loaded Causal GRU model (optional)
        meta_model: Pre-loaded meta-learner weights (NNLS) as numpy array of shape (3,), or
                   a sklearn model with predict_proba method
        scaler_raw: Fitted StandardScaler for raw features (required if use_causal_gru=True)
        raw_feature_indices: List of column indices (integers) for raw features. If None,
                            will be loaded from raw_features.json and mapped via feature_columns.
        use_causal_gru: If False, skip Causal GRU and use weighted LGBM+XGB ensemble.
        seq_len: Sequence length for GRU (default 7, from training config).

    Returns:
        Array of ensemble probabilities aligned to input samples:
        - If use_causal_gru=False: shape (n_samples,), values in [0,1]
        - If use_causal_gru=True: shape (n_samples,) with first (seq_len-1) elements = NaN,
          and valid predictions from index (seq_len-1) onward.

    Raises:
        ValueError: If raw_feature_indices conversion fails or Causal GRU fails due to
                    insufficient samples (n_samples < seq_len) when use_causal_gru=True.
    """
    # Load all models if not provided
    if lgbm_model is None or xgb_model is None or causal_gru_model is None or meta_model is None or scaler_raw is None or raw_feature_indices is None:
        (lgbm_model, xgb_model, causal_gru_model, meta_model, scaler_raw, meta_scaler,
         raw_feature_indices, loaded_nnls_weights) = load_stacking_models(
            X.shape[1]
        )
        # If caller didn't provide nnls_weights, use the one just loaded (if any)
        if nnls_weights is None:
            nnls_weights = loaded_nnls_weights

    # Validate raw_feature_indices type - convert string names to int indices if needed
    if raw_feature_indices is not None and len(raw_feature_indices) > 0:
        if not isinstance(raw_feature_indices[0], (int, np.integer)):
            # Convert feature names to column indices using feature_columns
            try:
                feature_columns = load_new_feature_columns()
                raw_feature_indices = [
                    i for i, col in enumerate(feature_columns) if col in raw_feature_indices
                ]
                logger.info(f"Converted {len(raw_feature_indices)} raw feature names to indices")
                if len(raw_feature_indices) == 0:
                    raise ValueError("No raw features found in feature_columns.json")
            except Exception as e:
                logger.error(f"Failed to convert raw feature names to indices: {e}")
                raise ValueError("raw_feature_indices conversion failed. Check raw_features.json and feature_columns.json.") from e

    # If Causal GRU disabled, use weighted LGBM+XGB ensemble (full length)
    if not use_causal_gru:
        logger.info("Causal GRU disabled - using LGBM+XGB weighted ensemble")
        lgbm_probs = _safe_lgbm_predict(lgbm_model, X, None)
        logger.info(
            f"LGBM RAW probs: min={lgbm_probs.min():.4f}, max={lgbm_probs.max():.4f}, mean={lgbm_probs.mean():.4f}, std={lgbm_probs.std():.4f}"
        )
        xgb_probs = predict_xgb(xgb_model, X)
        logger.info(
            f"XGB RAW probs: min={xgb_probs.min():.4f}, max={xgb_probs.max():.4f}, mean={xgb_probs.mean():.4f}, std={xgb_probs.std():.4f}"
        )
        w = _WEIGHTS_LGBM_XGB
        ensemble_probs = w[0] * lgbm_probs + w[1] * xgb_probs
        logger.info(
            f"LGBM+XGB ensemble: min={ensemble_probs.min():.4f}, max={ensemble_probs.max():.4f}, mean={ensemble_probs.mean():.4f}, std={ensemble_probs.std():.4f}"
        )
        # Return padded array for consistency with full stacking mode
        padded_output = np.full(X.shape[0], np.nan, dtype=float)
        padded_output[:] = ensemble_probs  # All predictions are valid in LGBM+XGB mode
        return padded_output

    # Full stacking with Causal GRU
    logger.info("Running LightGBM stacking predictions...")
    lgbm_probs_full = _safe_lgbm_predict(lgbm_model, X, None)
    logger.info(
        f"LightGBM RAW probs: min={lgbm_probs_full.min():.4f}, max={lgbm_probs_full.max():.4f}, mean={lgbm_probs_full.mean():.4f}, std={lgbm_probs_full.std():.4f}"
    )

    logger.info("Running XGBoost stacking predictions...")
    xgb_probs_full = predict_xgb(xgb_model, X)
    logger.info(
        f"XGBoost RAW probs: min={xgb_probs_full.min():.4f}, max={xgb_probs_full.max():.4f}, mean={xgb_probs_full.mean():.4f}, std={xgb_probs_full.std():.4f}"
    )

    logger.info("Running Causal GRU stacking predictions...")
    # Predict using Causal GRU - returns array of length (n_samples - seq_len + 1)
    # or length 1 if input was synthesized for single-sample prediction.
    gru_probs = predict_causal_gru(
        causal_gru_model,
        X,
        scaler_raw,
        raw_feature_indices,
        seq_len=seq_len,
    )
    logger.info(
        f"Causal GRU probs: min={gru_probs.min():.4f}, max={gru_probs.max():.4f}, mean={gru_probs.mean():.4f}, std={gru_probs.std():.4f}"
    )

    # Align predictions:
    # For multi-sample inputs (n_samples >= seq_len):
    #   GRU predicts for samples [seq_len-1:], tree models predict all n_samples.
    #   Trim tree predictions to match GRU output length.
    # For single-sample inputs (n_samples < seq_len, synthesized sequence):
    #   GRU returns 1 prediction, tree models also return 1 prediction.
    #   No trimming needed.
    n_samples = X.shape[0]
    if n_samples >= seq_len:
        effective_start = seq_len - 1
        lgbm_probs_aligned = lgbm_probs_full[effective_start:]
        xgb_probs_aligned = xgb_probs_full[effective_start:]
    else:
        # Single-sample case: no alignment needed, all models return 1 prediction
        effective_start = 0
        lgbm_probs_aligned = lgbm_probs_full
        xgb_probs_aligned = xgb_probs_full

    # Ensure lengths match (safety check)
    min_len = min(len(gru_probs), len(lgbm_probs_aligned), len(xgb_probs_aligned))
    if len(gru_probs) != len(lgbm_probs_aligned) or len(gru_probs) != len(xgb_probs_aligned):
        logger.warning(
            f"Length mismatch: GRU={len(gru_probs)}, LGBM={len(lgbm_probs_aligned)}, XGB={len(xgb_probs_aligned)}. Trimming to {min_len}."
        )
        gru_probs = gru_probs[:min_len]
        lgbm_probs_aligned = lgbm_probs_aligned[:min_len]
        xgb_probs_aligned = xgb_probs_aligned[:min_len]

    # Apply meta-learner to combine base model predictions
    # Standardize meta-features if scaler is available (meta_scaler disabled to avoid saturation)
    meta_features = np.column_stack([gru_probs, lgbm_probs_aligned, xgb_probs_aligned])
    if meta_scaler is not None:
        logger.warning("meta_scaler is not None - this may cause prediction saturation. Consider setting meta_scaler=None.")
        meta_features_scaled = meta_scaler.transform(meta_features)
    else:
        meta_features_scaled = meta_features

    # Decide whether to use NNLS weights instead of LogisticRegressionCV
    use_nnls = (os.getenv('USE_NNLS_META', 'false').lower() == 'true')
    if use_nnls and nnls_weights is not None and len(nnls_weights) == 3:
        logger.info("Using NNLS meta-learner (non-negative least squares weights)")
        ensemble_short = (
            nnls_weights[0] * gru_probs +
            nnls_weights[1] * lgbm_probs_aligned +
            nnls_weights[2] * xgb_probs_aligned
        )
    elif hasattr(meta_model, "predict_proba"):
        # LogisticRegression / LogisticRegressionCV path (new meta-learner)
        try:
            ensemble_short = meta_model.predict_proba(meta_features_scaled)[:, 1]
            coef = meta_model.coef_[0] if hasattr(meta_model, "coef_") else None
            intercept = meta_model.intercept_[0] if hasattr(meta_model, "intercept_") else None
            logger.info(
                f"LogisticRegression meta-learner applied "
                f"(coefs: GRU={coef[0]:.3f}, LGB={coef[1]:.3f}, XGB={coef[2]:.3f}, "
                f"intercept={intercept:.3f}): "
                f"min={ensemble_short.min():.4f}, max={ensemble_short.max():.4f}, "
                f"mean={ensemble_short.mean():.4f}, std={ensemble_short.std():.4f}"
            )
        except (AttributeError, RuntimeError, ValueError, TypeError) as e:
            logger.warning(f"LogisticRegression meta-learner failed: {e}. Falling back to NNLS/simple average.")
            ensemble_short = (gru_probs + lgbm_probs_aligned + xgb_probs_aligned) / 3.0
    elif isinstance(meta_model, np.ndarray):
        # NNLS weights path (legacy backward compatibility)
        weights = meta_model

        # Validate shape
        if weights.shape != (3,):
            logger.warning(f"NNLS weights shape {weights.shape} != (3,). Using simple average.")
            ensemble_short = (gru_probs + lgbm_probs_aligned + xgb_probs_aligned) / 3.0
        else:
            # Warn about degenerate weights (e.g., [0, 0, 1] means only XGB is used)
            zero_count = np.sum(weights < 0.01)
            if zero_count >= 2:
                dominant_idx = np.argmax(weights)
                model_names = ["Causal GRU", "LightGBM", "XGBoost"]
                logger.warning(
                    f"DEGENERATE stacking weights: {weights}. "
                    f"Only {model_names[dominant_idx]} contributes (weight={weights[dominant_idx]:.3f}). "
                    f"Consider retraining the meta-learner."
                )

            ensemble_short = (
                weights[0] * gru_probs +
                weights[1] * lgbm_probs_aligned +
                weights[2] * xgb_probs_aligned
            )
            logger.info(
                f"NNLS stacking (GRU={weights[0]:.3f}, LGBM={weights[1]:.3f}, XGB={weights[2]:.3f}): "
                f"min={ensemble_short.min():.4f}, max={ensemble_short.max():.4f}, "
                f"mean={ensemble_short.mean():.4f}, std={ensemble_short.std():.4f}"
            )
    else:
        # Unknown meta-model type: simple average
        logger.warning(f"Unknown meta-model type: {type(meta_model)}. Using simple average.")
        ensemble_short = (gru_probs + lgbm_probs_aligned + xgb_probs_aligned) / 3.0

    # Pad the beginning with NaN to align with original input length
    padded_output = np.full(X.shape[0], np.nan, dtype=float)
    padded_output[effective_start:effective_start+len(ensemble_short)] = ensemble_short

    # Ensure output probabilities are in valid range
    valid_mask = ~np.isnan(padded_output)
    if np.any(valid_mask):
        padded_output[valid_mask] = np.clip(padded_output[valid_mask], 0.0, 1.0)

    return padded_output


def predict_fire_risk(
    features: Dict[str, Any],
    model_version: Optional[str] = None,
    model_type: str = "new",
) -> Dict[str, Any]:
    """
    Predict fire risk from input features.

    This is the main prediction function used by the frontend and API.

    Args:
        features: Dictionary containing input features
            Required keys:
            - temperature: float
            - humidity: float
            - wind_speed: float
            - latitude: float
            - longitude: float
            Optional keys:
            - wind_direction: float
            - rainfall: float
            - ndvi: float
            - vegetation_type: str
        model_version: Optional model version string. If None, uses active version.
        model_type: Model type to use - "legacy" for old CNN+LGBM, "new" for stacking (default: "new")

    Returns:
        Dictionary with prediction results:
            - risk_score: float (0-1)
            - risk_level: str ('Low', 'Medium', 'High', 'Extreme')
            - confidence: float
            - cnn_probability: float
            - lgbm_probability: float
            - factors: Dict[str, float] - contributing risk factors
            - shap_explanation: Dict - SHAP explanation (if available)
            - confidence_interval: float - |cnn - lgbm|
            - model_agreement: float - 1 - |cnn - lgbm|
            - timestamp: str
            - status: str

    Raises:
        PredictionError: If prediction fails
    """
    try:
        logger.info(f"Running prediction with features: {features}")
        logger.info(f"Using model_type: {model_type}")

        required_keys = [
            "temperature",
            "humidity",
            "wind_speed",
            "latitude",
            "longitude",
        ]
        for key in required_keys:
            if key not in features:
                raise PredictionError(f"Missing required feature: {key}")

        # Create feature vector using correct feature set for model type
        feature_vector = _create_feature_vector(features, use_new_features=(model_type == "new"))

        if model_type == "legacy":
            logger.info(f"Feature vector shape: {feature_vector.shape}")
            logger.info(f"Feature vector sample (first 10): {feature_vector[0][:10]}")

            try:
                scaler = joblib.load(config.SCALER_PATH)
                feature_vector_scaled = scaler.transform(feature_vector)
                logger.info(
                    f"Scaled feature vector sample (first 10): {feature_vector_scaled[0][:10]}"
                )
            except (OSError, FileNotFoundError, pickle.PickleError, ValueError, RuntimeError) as e:
                logger.warning(f"Could not load scaler: {e}, using unscaled features")
                feature_vector_scaled = feature_vector

            cnn_model, lgbm_model = load_ensemble_models(
                feature_vector.shape[1], version=model_version
            )

            cnn_probs, lgbm_probs = predict_batch(
                feature_vector_scaled, cnn_model, lgbm_model
            )

            # Log detailed prediction values for debugging
            logger.info(f"Raw CNN probability: {cnn_probs[0]}")
            logger.info(f"Raw LightGBM probability: {lgbm_probs[0]}")

            ensemble_prob = (cnn_probs[0] + lgbm_probs[0]) / 2

            logger.info(f"Ensemble probability (raw average): {ensemble_prob}")

            cnn_prob = float(cnn_probs[0])
            lgbm_prob = float(lgbm_probs[0])
            disagreement = abs(cnn_prob - lgbm_prob)
            model_name_used = "Model Ensemble"

            try:
                with open(config.FEATURE_COLUMNS_PATH, "r") as f:
                    legacy_feature_cols = json.load(f)
                shap_explanation = _compute_shap_explanation(
                    features, lgbm_model,
                    feature_vector=feature_vector_scaled,
                    feature_columns=legacy_feature_cols,
                )
            except Exception as shap_err:
                logger.debug(f"SHAP computation failed: {shap_err}")
                shap_explanation = {}

            risk_level = _get_risk_level(ensemble_prob)
            factors = _calculate_risk_factors(features)

            return {
                "risk_score": float(ensemble_prob),
                "risk_level": risk_level,
                "confidence": float(1.0 - disagreement),
                "cnn_probability": cnn_prob,
                "lgbm_probability": lgbm_prob,
                "confidence_interval": float(disagreement),
                "model_agreement": float(1.0 - disagreement),
                "factors": factors,
                "shap_explanation": shap_explanation,
                "timestamp": pd.Timestamp.now().isoformat(),
                "status": "success",
                "model_type": model_name_used,
            }
        else:
            # Use new stacking model (Causal GRU + LGBM + XGB + NNLS)
            feature_vector = _create_feature_vector(features, use_new_features=True)
            logger.info(f"Feature vector shape: {feature_vector.shape}")
            logger.info(f"Feature vector (first 10): {feature_vector[0][:10]}")
            logger.info(f"Feature vector (last 10): {feature_vector[0][-10:]}")

            # Load scaler for all engineered features
            try:
                new_scaler = load_new_model_scaler()
                feature_vector_scaled = new_scaler.transform(feature_vector)
                logger.info(
                    f"Scaled feature vector (first 10): {feature_vector_scaled[0][:10]}"
                )
            except Exception as e:
                logger.warning(f"Could not load new scaler: {e}, using unscaled features")
                feature_vector_scaled = feature_vector

            # Load stacking models including Causal GRU and raw scaler
            # Returns: lgbm, xgb, gru, meta, scaler_raw, meta_scaler, raw_indices, nnls_weights
            (
                lgbm_model,
                xgb_model,
                causal_gru_model,
                meta_model,
                scaler_raw,
                meta_scaler,
                raw_feature_indices,
                nnls_weights,
            ) = load_stacking_models()

            # Validate raw_feature_indices - must not be empty
            if raw_feature_indices is None or len(raw_feature_indices) == 0:
                raise ValueError("No raw feature indices available. Cannot run Causal GRU model. "
                                 "Check that raw_features.json and feature_columns.json exist and are valid.")  
            else:
                logger.info(f"Using {len(raw_feature_indices)} raw feature indices for Causal GRU")

            # Determine if Causal GRU should be used
            # Default: True (use Causal GRU). Set USE_CAUSAL_GRU_AOI=false to disable.
            use_causal_gru_flag = USE_CAUSAL_GRU_AOI

            # Get ensemble probability array
            try:
                ensemble_probs = predict_stacking(
                    feature_vector_scaled,
                    lgbm_model,
                    xgb_model,
                    causal_gru_model=causal_gru_model,
                    meta_model=meta_model,
                    scaler_raw=scaler_raw,
                    meta_scaler=meta_scaler,
                    raw_feature_indices=raw_feature_indices,
                    use_causal_gru=use_causal_gru_flag,
                    seq_len=7,
                    nnls_weights=nnls_weights,
                )
            except ValueError as e:
                # Causal GRU requires minimum seq_len samples; fall back to LGBM+XGB
                if "Not enough samples" in str(e) or "sequence length" in str(e).lower():
                    logger.warning(f"Causal GRU cannot run (single sample or too few): {e}. Using LGBM+XGB ensemble.")
                    use_causal_gru_flag = False
                    ensemble_probs = predict_stacking(
                        feature_vector_scaled,
                        lgbm_model,
                        xgb_model,
                        causal_gru_model=causal_gru_model,
                        meta_model=meta_model,
                        scaler_raw=scaler_raw,
                        meta_scaler=meta_scaler,
                        raw_feature_indices=raw_feature_indices,
                        use_causal_gru=False,
                        seq_len=7,
                        nnls_weights=nnls_weights,
                    )
                else:
                    raise

            # For single-sample input, extract the first valid (non-NaN) probability.
            # When use_causal_gru=False, result has no NaNs and length=1 -> take element 0.
            # When use_causal_gru=True, first (seq_len-1) positions are NaN, first valid at index seq_len-1.
            valid_mask = ~np.isnan(ensemble_probs)
            if np.any(valid_mask):
                ensemble_prob = float(ensemble_probs[valid_mask][0])
            else:
                logger.error(
                    f"All ensemble predictions are NaN. Input shape: {feature_vector_scaled.shape}, "
                    f"use_causal_gru: {use_causal_gru_flag}, raw indices valid: {raw_feature_indices is not None and len(raw_feature_indices) > 0}"
                )
                # Try fallback to LGBM prediction
                try:
                    lgbm_fallback = lgbm_model.predict(feature_vector_scaled)
                    ensemble_prob = float(lgbm_fallback[0])
                    logger.warning(f"Used LGBM fallback prediction: {ensemble_prob:.4f}")
                except Exception as fallback_err:
                    logger.error(f"LGBM fallback also failed: {fallback_err}")
                    raise ValueError("All ensemble predictions are NaN and fallback prediction failed")

            logger.info(
                f"Final ensemble_prob={ensemble_prob:.4f} (from {np.sum(valid_mask)} valid predictions, "
                f"raw array={ensemble_probs})"
            )

            # --- Calibration: Temperature scaling & probability capping ---
            # Temperature scaling reduces overconfidence by scaling logits before sigmoid.
            # T > 1 softens probabilities toward 0.5; T < 1 makes more extreme.
            temp = float(os.getenv('ENSEMBLE_TEMPERATURE', '1.0'))
            if temp != 1.0:
                # Avoid exactly 0 or 1 which break logit
                p_safe = np.clip(ensemble_prob, 1e-6, 1-1e-6)
                logit = np.log(p_safe / (1 - p_safe))
                ensemble_prob = 1.0 / (1.0 + np.exp(-logit / temp))
                logger.info(f"Applied temperature scaling (T={temp}): adjusted_prob={ensemble_prob:.4f}")

            # Optional hard cap on maximum probability
            max_prob = float(os.getenv('MAX_PROBABILITY', '1.0'))
            if max_prob < 1.0 and ensemble_prob > max_prob:
                logger.warning(f"Capping probability from {ensemble_prob:.4f} to {max_prob:.4f}")
                ensemble_prob = max_prob
            # --- End calibration ---

            new_threshold = load_new_model_threshold()
            logger.info(f"Model threshold: {new_threshold:.4f}")

            cnn_prob = float(ensemble_prob)  # For stacking model, CNN prob = ensemble prob
            lgbm_prob = float(ensemble_prob)  # For stacking model, LGBM prob = ensemble prob
            disagreement = 0.0  # No disagreement in ensemble model
            model_name_used = "Model Stacking"

            shap_explanation = {}
            try:
                new_feature_cols = load_new_feature_columns()
                shap_explanation = _compute_shap_explanation(
                    features, lgbm_model,
                    feature_vector=feature_vector_scaled,
                    feature_columns=new_feature_cols,
                )
            except Exception as shap_err:
                logger.debug(f"SHAP computation failed: {shap_err}")

            risk_level = _get_risk_level(ensemble_prob)
            factors = _calculate_risk_factors(features)

            # Validate probability is in [0, 1] range
            if not 0 <= ensemble_prob <= 1:
                logger.warning(f"Ensemble probability {ensemble_prob:.4f} outside [0,1], clipping")
                ensemble_prob = float(np.clip(ensemble_prob, 0.0, 1.0))

            confidence_interval = disagreement
            model_agreement = max(0.0, 1.0 - disagreement)

            result = {
                "risk_score": cnn_prob,
                "risk_level": risk_level,
                "confidence": float(1.0 - disagreement),
                "cnn_probability": cnn_prob,
                "lgbm_probability": lgbm_prob,
                "confidence_interval": float(confidence_interval),
                "model_agreement": float(model_agreement),
                "factors": factors,
                "shap_explanation": shap_explanation,
                "timestamp": pd.Timestamp.now().isoformat(),
                "status": "success",
                "model_type": model_name_used,
            }

            logger.info(
                f"Prediction result: {result['risk_level']} (score: {result['risk_score']:.3f})"
            )
            return result

    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise PredictionError(f"Failed to run prediction: {e}")


def _calculate_risk_factors(features: Dict[str, Any]) -> Dict[str, float]:
    """Calculate contributing risk factors."""
    factors = {}

    temp = features.get("temperature", 30)
    humidity = features.get("humidity", 50)
    wind = features.get("wind_speed", 5)
    rainfall = features.get("rainfall")  # Default is None (not provided)

    # Get thresholds from environment variables or use defaults
    # These thresholds should match the feature engineering thresholds used in model training
    temp_threshold = float(os.getenv("RISK_TEMP_THRESHOLD", "32"))  # Model uses 32°C
    # Humidity threshold corresponds to VPD >12; approximate humidity threshold ~40%
    humidity_threshold = float(os.getenv("RISK_HUMIDITY_THRESHOLD", "40"))
    wind_threshold = float(os.getenv("RISK_WIND_THRESHOLD", "4"))  # Model uses 4 m/s
    rainfall_threshold = float(os.getenv("RISK_RAINFALL_THRESHOLD", "1"))  # Model uses <1mm

    # Temperature factor (higher is worse)
    if temp > temp_threshold:
        factors["High Temperature"] = min((temp - temp_threshold) / 10 * 100, 100)

    # Humidity factor (lower is worse)
    if humidity < humidity_threshold:
        factors["Low Humidity"] = (humidity_threshold - humidity) / humidity_threshold * 100

    # Wind factor (higher is worse)
    if wind > wind_threshold:
        factors["Strong Wind"] = min((wind - wind_threshold) / 15 * 100, 100)

    # Rain factor (lower is worse - no recent rain)
    # Linear scale: 0 rainfall = max risk (80), threshold = 0 risk
    if rainfall is not None and rainfall < rainfall_threshold:
        factors["No Recent Rainfall"] = max(0, 80 * (1 - rainfall / rainfall_threshold))

    return factors


def _compute_shap_explanation(
    features: Dict[str, Any],
    lgbm_model: Any,
    feature_vector: Optional[np.ndarray] = None,
    feature_columns: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Compute SHAP explanation for a single prediction.

    Args:
        features: Input feature dictionary (fallback if feature_vector not provided).
        lgbm_model: LightGBM model.
        feature_vector: Pre-built engineered feature vector (1, n_features). Preferred.
        feature_columns: Feature column names corresponding to feature_vector.

    Returns:
        Dictionary with top contributing features and their SHAP values.
    """
    try:
        import shap

        if feature_vector is not None and feature_columns is not None:
            X = feature_vector
            feature_names = feature_columns
        else:
            df = pd.DataFrame([features])
            try:
                with open(config.FEATURE_COLUMNS_PATH, "r") as f:
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

        # Binary classification: TreeExplainer returns list [shap_class_0, shap_class_1]
        # We want positive class (fire risk = class 1)
        if isinstance(shap_values, list):
            # Determine which class is positive (fire)
            # For LightGBM binary, class 1 is typically the positive class
            if len(shap_values) == 2:
                shap_values_used = shap_values[1]
                # expected_value may be scalar or array; get positive class
                if hasattr(explainer.expected_value, '__len__') and len(explainer.expected_value) >= 2:
                    base_value = float(explainer.expected_value[1])
                else:
                    base_value = float(explainer.expected_value)
            else:
                # Multi-class: default to class 1 (should not happen in current model)
                shap_values_used = shap_values[1]
                base_value = explainer.expected_value[1] if hasattr(explainer.expected_value, '__len__') else float(explainer.expected_value)
        else:
            # Regression or single-output
            shap_values_used = shap_values
            base_value = float(explainer.expected_value)

        abs_shap = np.abs(shap_values_used[0])
        top_indices = np.argsort(abs_shap)[-5:][::-1]

        top_features = []
        for idx in top_indices:
            top_features.append(
                {
                    "feature": feature_names[idx],
                    "shap_value": float(shap_values_used[0][idx]),
                    "contribution": "positive" if shap_values_used[0][idx] > 0 else "negative",
                    "importance": float(abs_shap[idx]),
                }
            )

        return {
            "top_features": top_features,
            "base_value": base_value,
        }
    except Exception as e:
        logger.debug(f"SHAP explanation failed: {e}")
        return {}


def _estimate_temporal_feature(
    col_name: str, current_val: float, month: int, doy: int
) -> Tuple[float, float]:
    """
    Estimate lag3 (3 days ago) and roll7 (7-day average) values for a feature
    given its current value. Uses deterministic heuristics derived from typical
    temporal dynamics of meteorological and spectral variables.

    This replaces the previous buggy implementation that used current values for
    both lag and roll, which caused constant predictions.
    """
    # Helper for bounded clamping
    def clamp(v, vmin=None, vmax=None, rounded=False):
        if rounded:
            v = int(round(v))
        if vmin is not None:
            v = max(vmin, v)
        if vmax is not None:
            v = min(vmax, v)
        return v

    # Seasonal sine/cos components to add realistic drift based on day of year
    # Phase offset per feature to avoid all features shifting together
    # Use deterministic hash instead of Python's salted hash for reproducibility
    import hashlib
    phase = int(hashlib.md5(col_name.encode()).hexdigest(), 16) % 365
    seasonal = 0.1 * math.sin(2 * math.pi * (doy + phase) / 365)

    # Determine feature type and apply appropriate offset
    # Most features: lag3 = current - small drift, roll7 = current - even smaller drift
    if col_name in ("temp_max", "dewpoint"):
        # Temperature: can change several degrees over 3 days
        lag_val = current_val - 2.0 + 0.5 * math.sin(2 * math.pi * doy / 365) + seasonal
        roll_val = current_val - 0.8  # 7-day avg smoother
    elif col_name == "precip":
        # Precipitation: highly variable, often zero; lag could be zero or lower
        lag_val = max(0.0, current_val * 0.3)  # assume decreasing
        roll_val = max(0.0, current_val * 0.6)  # average includes rain events
    elif col_name in ("wind_speed", "wind_u", "wind_v"):
        # Wind: moderate day-to-day variation
        lag_val = current_val * 0.95 + 0.1
        roll_val = current_val * 0.98
    elif col_name in ("B2", "B3", "B4", "B8", "B11", "B12"):
        lag_val = current_val * 0.98
        roll_val = current_val * 0.995
    elif col_name == "ndvi":
        lag_val = clamp(current_val * 0.98 + 0.02, 0.0, 1.0)
        roll_val = clamp(current_val * 0.995 + 0.005, 0.0, 1.0)
    elif col_name in ("ndwi", "nbr", "evi"):
        lag_val = clamp(current_val * 0.98, -1.0, 1.0)
        roll_val = clamp(current_val * 0.995, -1.0, 1.0)
    elif col_name == "vpd":
        lag_val = current_val + 0.2 * math.sin(2 * math.pi * doy / 365)
        roll_val = current_val
    elif col_name == "wind_mag":
        lag_val = current_val * 0.96
        roll_val = current_val * 0.99
    elif col_name in ("dry_spell_7", "dry_spell_30"):
        # Dry spells accumulate; lag might be slightly less
        lag_val = max(0, int(round(current_val * 0.9)))
        roll_val = max(0, current_val * 0.95)
    elif col_name == "fuel_dryness":
        lag_val = current_val * 0.98
        roll_val = current_val * 0.99
    elif col_name == "extreme_fire_weather":
        lag_val = max(0, current_val - 0.2)
        roll_val = max(0, current_val - 0.1)
    elif col_name == "extreme_days_5d":
        lag_val = max(0, current_val - 0.1)
        roll_val = max(0, current_val - 0.05)
    elif col_name == "precip_deficit_7d":
        lag_val = current_val + 0.5
        roll_val = current_val + 0.2
    elif col_name in ("temp_change_3d", "wind_change_3d"):
        # These are already differences; shrink a bit for lag
        lag_val = current_val * 0.5
        roll_val = current_val * 0.7
    elif col_name in ("elevation", "land_cover", "lat", "lon", "month", "day"):
        # Static/slowly varying: no change
        lag_val = current_val
        roll_val = current_val
    else:
        # Default: small drift
        lag_val = current_val * 0.98 + 0.02 * math.sin(doy)
        roll_val = current_val * 0.99

    return lag_val, roll_val


def _create_feature_vector(
    features: Dict[str, Any], use_new_features: bool = False
) -> np.ndarray:
    """
    Create feature vector from input features.

    Args:
        features: Input feature dictionary.
        use_new_features: If True, use new model feature columns (79 features).
                         If False, use legacy feature columns (59 features).

    Returns:
        Feature vector as a 2D numpy array (1, n_features).
    """
    # Extract required parameters from features
    temp = features.get("temperature", 30)
    humidity = features.get("humidity", 50)
    wind_speed = features.get("wind_speed", 5)
    wind_direction = features.get("wind_direction", 0)
    rainfall = features.get("rainfall")  # Default is None (not provided)
    # Use 1.0mm (threshold) for feature engineering if not provided - neutral assumption
    # This ensures model receives valid numeric input without falsely triggering "dry" conditions
    rainfall_numeric = 1.0 if rainfall is None else rainfall
    ndvi = features.get("ndvi", 0.3)
    vegetation_type = features.get("vegetation_type", "Savana")
    lat = features.get("latitude", -2.0)
    lon = features.get("longitude", 112.0)

    # Elevation: use provided if available (from GEE), else default
    elevation = features.get("elevation", 100.0)

    # Land cover: use provided if available (from GEE Dynamic World), else map from vegetation
    if "land_cover" in features:
        land_cover = features["land_cover"]
    else:
        land_cover_map = {
            "Hutan": 10, "Forest": 10, "Hutan Tropis Lembab": 10,
            "Semak": 20, "Shrub": 20, "Semak Kering": 20,
            "Savana": 30, "Savanna": 30,
            "Rumput": 40, "Grass": 40, "Padang Rumput": 40, "Lahan Gambut": 40,
            "Lahan Pertanian": 50, "Agriculture": 50,
            "Lahan Terbuka": 60, "Open Land": 60,
            "Pemukiman": 70, "Settlement": 70,
        }
        land_cover = land_cover_map.get(vegetation_type, 30)

    # Convert wind direction to u/v components
    wind_rad = math.radians(wind_direction)
    wind_u = -wind_speed * math.sin(wind_rad)
    wind_v = -wind_speed * math.cos(wind_rad)

    # Get current date features
    now = datetime.now()
    month = now.month
    day = now.day
    doy = now.timetuple().tm_yday

    # Calculate derived meteorological features
    # Dewpoint approximation using Magnus formula
    a = 17.271
    b = 237.7
    alpha = ((a * temp) / (b + temp)) + math.log(humidity / 100.0)
    dewpoint = (b * alpha) / (a - alpha)

    # VPD (Vapor Pressure Deficit) - using proper Magnus formula
    # Saturation vapor pressure (hPa)
    es = 6.1078 * 10 ** ((7.5 * temp) / (237.3 + temp))
    # Actual vapor pressure from relative humidity
    ea = (humidity / 100.0) * es
    vpd = max(0, es - ea)  # VPD in hPa (0-~60 hPa range, matches model training)

    # Wind magnitude
    wind_mag = math.sqrt(wind_u**2 + wind_v**2)

    # Spectral bands: use GEE-provided values if available (bands in features)
    # GEE provides surface reflectance scaled 0-1
    # Fallback to synthetic estimation based on NDVI if not provided
    required_bands = ["B2", "B3", "B4", "B8", "B11", "B12"]
    if all(b in features for b in required_bands):
        B2 = features.get("B2", 0.0)
        B3 = features.get("B3", 0.0)
        B4 = features.get("B4", 0.0)
        B8 = features.get("B8", 0.0)
        B11 = features.get("B11", 0.0)
        B12 = features.get("B12", 0.0)
    else:
        # Synthetic estimation based on NDVI (fallback)
        if ndvi > 0.6:  # Dense vegetation
            B2, B3, B4, B8, B11, B12 = 0.03, 0.05, 0.04, 0.45, 0.08, 0.05
        elif ndvi > 0.3:  # Moderate
            B2, B3, B4, B8, B11, B12 = 0.05, 0.08, 0.09, 0.30, 0.15, 0.10
        else:  # Sparse
            B2, B3, B4, B8, B11, B12 = 0.10, 0.12, 0.15, 0.12, 0.25, 0.20

    # Calculate spectral indices with safe division
    ndwi = _safe_divide(B3 - B11, B3 + B11)
    nbr = _safe_divide(B8 - B12, B8 + B12)
    evi = 2.5 * _safe_divide(B8 - B4, B8 + 6 * B4 - 7.5 * B2 + 1)

    # Fire weather indices
    dry_day = 1 if rainfall is not None and rainfall < 1.0 else 0
    dry_spell_7 = dry_day * 3  # Assume 3-day dry spell for single prediction
    dry_spell_30 = dry_day * 3
    fuel_dryness = vpd * (1 - ndvi)

    # Threshold indicators - configurable via environment variables
    # Using more realistic percentile-based thresholds matching training distribution
    temp_threshold = float(os.getenv('RISK_TEMP_THRESHOLD', '32'))
    vpd_threshold = float(os.getenv('RISK_VPD_THRESHOLD', '12'))
    wind_threshold = float(os.getenv('RISK_WIND_THRESHOLD', '4'))
    
    hot_threshold = 1 if temp > temp_threshold else 0
    dry_threshold = 1 if vpd > vpd_threshold else 0
    windy_threshold = 1 if wind_speed > wind_threshold else 0
    extreme_fire_weather = hot_threshold + dry_threshold + windy_threshold

    # Trend features (approximated for single prediction)
    temp_change_3d = 0.0
    wind_change_3d = 0.0
    precip_deficit_7d = max(0, 10 - rainfall_numeric * 7)
    extreme_days_5d = extreme_fire_weather

    # Cyclical time features
    month_sin = math.sin(2 * math.pi * month / 12)
    month_cos = math.cos(2 * math.pi * month / 12)
    doy_sin = math.sin(2 * math.pi * doy / 365)
    doy_cos = math.cos(2 * math.pi * doy / 365)

    # Precipitation
    precip = rainfall_numeric
    temp_max = temp

    # Log key input features for debugging
    logger.info(
        f"Input features: temp={temp}, humidity={humidity}, wind_speed={wind_speed}, precip={precip}, ndvi={ndvi}"
    )

    # Build base feature dictionary
    base_dict = {
        "B11": B11,
        "B12": B12,
        "B2": B2,
        "B3": B3,
        "B4": B4,
        "B8": B8,
        "dewpoint": dewpoint,
        "elevation": elevation,
        "land_cover": land_cover,
        "lat": lat,
        "lon": lon,
        "ndvi": ndvi,
        "precip": precip,
        "temp_max": temp_max,
        "wind_speed": wind_speed,
        "wind_u": wind_u,
        "wind_v": wind_v,
        "month": month,
        "day": day,
    }

    # Calculate lag and rolling features using realistic estimators
    lag_features = {}
    for col, val in base_dict.items():
        lag3_val, roll7_val = _estimate_temporal_feature(col, val, month, doy)
        lag_features[f"{col}_lag3"] = lag3_val
        lag_features[f"{col}_roll7"] = roll7_val

    # Combine all features
    all_features = {
        **base_dict,
        **lag_features,
        "month_sin": month_sin,
        "month_cos": month_cos,
        "doy": doy,
        "doy_sin": doy_sin,
        "doy_cos": doy_cos,
        "vpd": vpd,
        "wind_mag": wind_mag,
        "dry_day": dry_day,
        "dry_spell_7": dry_spell_7,
        "dry_spell_30": dry_spell_30,
        "fuel_dryness": fuel_dryness,
        "hot_threshold": hot_threshold,
        "dry_threshold": dry_threshold,
        "windy_threshold": windy_threshold,
        "extreme_fire_weather": extreme_fire_weather,
        "ndwi": ndwi,
        "nbr": nbr,
        "evi": evi,
        "temp_change_3d": temp_change_3d,
        "wind_change_3d": wind_change_3d,
        "precip_deficit_7d": precip_deficit_7d,
        "extreme_days_5d": extreme_days_5d,
    }

    # Load feature columns to ensure correct order
    feature_columns = []  # Initialize before try to avoid UnboundLocalError in except handler
    try:
        # Use new model feature columns if requested
        if use_new_features:
            feature_columns = load_new_feature_columns()
            logger.info(f"Using new model features ({len(feature_columns)}): {feature_columns[:10]}...")
        else:
            with open(config.FEATURE_COLUMNS_PATH, "r") as f:
                feature_columns = json.load(f)
            logger.info(f"Using legacy features ({len(feature_columns)}): {feature_columns[:10]}...")

        # Create feature vector in correct order - must match exactly
        feature_vector = []
        missing_features = []
        for col in feature_columns:
            if col in all_features:
                feature_vector.append(all_features[col])
            else:
                missing_features.append(col)
                feature_vector.append(0.0)
        
        if missing_features:
            logger.warning(f"Missing features (using 0.0): {missing_features}")
        
        # CRITICAL: Feature count must match exactly
        if len(feature_vector) != len(feature_columns):
            raise ValueError(
                f"Feature count mismatch: expected {len(feature_columns)}, got {len(feature_vector)}"
            )

        # Log debugging info
        logger.debug(f"Feature vector shape: ({len(feature_vector)},)")
        logger.debug(f"First 10 values: {feature_vector[:10]}")

        return np.array([feature_vector])

    except Exception as e:
        logger.error(f"Fatal error in _create_feature_vector: {e}")
        logger.error(f"Feature columns: {feature_columns}")
        logger.error(f"Available features: {list(all_features.keys())}")
        raise  # Propagate error with additional context  # Propagate error instead of returning malformed vector


def _get_risk_level(probability: float) -> str:
    """Convert probability to risk level."""
    if probability < 0.3:
        return "Low"
    elif probability < 0.5:
        return "Medium"
    elif probability < 0.7:
        return "High"
    else:
        return "Extreme"


def predict_from_csv(
    csv_path: Union[str, Path], output_path: Optional[Union[str, Path]] = None
) -> pd.DataFrame:
    """
    Run predictions on a CSV file.

    Args:
        csv_path: Path to input CSV file
        output_path: Optional path to save predictions

    Returns:
        DataFrame with predictions added
    """
    logger.info(f"Loading data from {csv_path}")
    df = pd.read_csv(csv_path)

    # Apply feature engineering
    df = engineer_features(df, lag=config.LAG, roll=config.ROLL_WINDOW)

    # Load feature columns
    with open(config.FEATURE_COLUMNS_PATH, "r") as f:
        feature_names = json.load(f)

    available_cols = [col for col in feature_names if col in df.columns]
    X = df[available_cols].values

    # Load scaler
    scaler = joblib.load(config.SCALER_PATH)
    X_scaled = scaler.transform(X)

    # Run predictions
    cnn_probs, lgbm_probs = predict_batch(X_scaled)
    ensemble_probs = (cnn_probs + lgbm_probs) / 2

    # Add to dataframe
    df["cnn_probability"] = cnn_probs
    df["lgbm_probability"] = lgbm_probs
    df["ensemble_probability"] = ensemble_probs
    df["predicted_risk_level"] = [_get_risk_level(p) for p in ensemble_probs]

    if output_path:
        df.to_csv(output_path, index=False)
        logger.info(f"Predictions saved to {output_path}")

    return df


def main():
    """Main function for running evaluation on test data."""
    logger.info("\n🔥 FireCast - Fire Forecasting System")
    logger.info("=" * 60)

    try:
        logger.info("📦 Loading data and preprocessing...")
        X_test_scaled, y_test, feature_names = load_data_for_evaluation()
        logger.info(
            f"✅ Test data ready: {X_test_scaled.shape[0]} samples, {X_test_scaled.shape[1]} features"
        )

        logger.info("\n🧠 Loading models...")
        cnn_model, lgbm_model = load_ensemble_models(X_test_scaled.shape[1])

        logger.info("\n🔮 Running predictions...")
        cnn_probs, lgbm_probs = predict_batch(X_test_scaled, cnn_model, lgbm_model)

        logger.info("\n⚡ Evaluating ensemble...")
        evaluate_ensemble(y_test.values, cnn_probs, lgbm_probs)

    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        raise


if __name__ == "__main__":
    main()
