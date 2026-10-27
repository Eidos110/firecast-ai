"""FireCast prediction service.

Serving contract:
  * ``model_type="new"`` (default) — V4.2 two-leg stack: LightGBM + XGBoost
    probabilities combined by a LogisticRegressionCV meta-learner, then
    isotonic-calibrated. No GRU leg (retired with V4.2).
  * ``model_type="legacy"`` — CNN + LightGBM mean ensemble under ``models/``.

Both paths raise :class:`PredictionError` on failure; there is no silent
0.5 fallback anywhere in this module (AGENTS.md §3).
"""

import copy
import json
import logging
import os
import pickle
from datetime import datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src import config
from src.data_loader import load_data_for_evaluation
from src.feature_engineering import engineer_features

# Torch is imported lazily so a worker whose sandbox blocks the native
# ``libtorch_cpu.so`` still boots (legacy inference then fails at request
# time instead of at import time). The shared loader handles ``ImportError``
# and ``OSError``.
from src.utils.lazy import get_torch as _shared_get_torch

_torch = None


def _get_torch():
    """Return torch module lazily. Returns None if unavailable.

    Delegates to :func:`src.utils.lazy.get_torch` so Railway/HF Spaces
    workers (where ``import torch`` raises ``OSError`` from the execstack
    block) still boot and fail the request cleanly instead of the import.
    """
    global _torch
    if _torch is None:
        _torch, _ = _shared_get_torch()
    return _torch


logger = logging.getLogger(__name__)


class PredictionError(Exception):
    """Custom exception for prediction errors."""

    pass


class ModelLoadError(Exception):
    """Custom exception for model loading errors."""

    pass


# Registry for model version management – safe (registry.py has no torch import)
from src.models import registry  # noqa: E402

# ── End of safe module-level imports ──


def load_ensemble_models(input_dim: int, version: str | None = None) -> tuple[Any, Any]:
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
        raise ModelLoadError(f"Cannot import model loaders (torch unavailable on Railway?): {e}")

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


def load_stacking_models() -> tuple[Any, Any, Any]:
    """Load the active V4.2 stacking bundle (LightGBM + XGBoost + meta).

    The active bundle is the 2-leg cross-section model trained by
    ``add_new_model/final_modelling_V4.2_crosssection.ipynb``. Its decision
    path is ``[p_lgbm, p_xgb] -> LogisticRegressionCV -> isotonic``. The GRU
    leg was retired with V4.2 and no GRU artifacts ship anymore, so this
    loader deliberately exposes only the two essential base models plus the
    meta-learner.

    Returns:
        ``(lgbm_model, xgb_model, meta_model)``.

    Raises:
        ModelLoadError: if an artifact is missing, unreadable, or the
            meta-learner was not fitted on exactly two input probabilities.
    """
    try:
        from src.models.lgbm import load_lgbm_model
        from src.models.xgb import load_xgb_model
    except ImportError as exc:  # pragma: no cover - depends on install
        raise ModelLoadError(f"Cannot import stacking model loaders: {exc}") from exc

    try:
        lgbm_model = load_lgbm_model(model_path=config.NEW_LGBM_MODEL_PATH)
    except Exception as exc:
        raise ModelLoadError(f"Failed to load LGBM model: {exc}") from exc

    try:
        xgb_model = load_xgb_model(model_path=config.NEW_XGB_MODEL_PATH)
    except Exception as exc:
        raise ModelLoadError(f"Failed to load XGB model: {exc}") from exc

    try:
        meta_model = joblib.load(config.NEW_META_MODEL_PATH)
    except Exception as exc:
        raise ModelLoadError(f"Failed to load meta-learner: {exc}") from exc

    if not hasattr(meta_model, "predict_proba"):
        raise ModelLoadError(
            f"Unsupported meta-learner type {type(meta_model).__name__}: "
            "expected a scikit-learn classifier with predict_proba()."
        )
    if getattr(meta_model, "n_features_in_", None) != 2:
        raise ModelLoadError(
            "Meta-learner expects "
            f"{getattr(meta_model, 'n_features_in_', 'unknown')} input features; "
            "the V4.2 two-leg bundle must be fitted on [p_lgbm, p_xgb]."
        )

    logger.info(
        "Stacking bundle loaded: LGBM=%s XGB=%s meta=%s",
        type(lgbm_model).__name__,
        type(xgb_model).__name__,
        type(meta_model).__name__,
    )
    return lgbm_model, xgb_model, meta_model


def load_new_model_scaler():
    """Load scaler for new model."""
    return joblib.load(config.NEW_SCALER_PATH)


def load_new_model_threshold() -> float:
    """Load optimal threshold for new model."""
    with open(config.NEW_THRESHOLD_PATH) as f:
        threshold_config = json.load(f)
    return threshold_config.get("optimal_threshold", 0.5)


def load_new_feature_columns() -> list:
    """Load feature columns for new model."""
    with open(config.NEW_FEATURE_COLUMNS_PATH) as f:
        return json.load(f)


def load_new_model_calibration():
    """Load the stack probability calibrator (P3, V4.2 bundle) if present.

    Returns the fitted calibrator (anything exposing ``predict`` mapping raw
    stack probabilities to calibrated fire frequencies) or ``None`` when the
    artifact is absent — legacy 3-leg bundles ship without one and serving
    must treat that as a no-op, not an error.

    Env override: ``FC_DISABLE_CALIBRATION=1`` forces the raw probability
    (comparison / A-B testing of the calibrated surface).
    """
    if os.getenv("FC_DISABLE_CALIBRATION", "").lower() in ("1", "true", "yes"):
        logger.info("Stack calibration disabled via FC_DISABLE_CALIBRATION")
        return None
    path = Path(config.NEW_CALIBRATION_PATH)
    if not path.exists():
        return None
    try:
        calibrator = joblib.load(path)
    except Exception as e:
        logger.warning(f"Failed to load stack calibrator ({e}) — using raw probabilities")
        return None
    if not hasattr(calibrator, "predict"):
        logger.warning(
            f"Unsupported calibrator type {type(calibrator).__name__} "
            "(no .predict) — using raw probabilities"
        )
        return None
    logger.info(f"Stack calibrator loaded: {type(calibrator).__name__} from {path}")
    return calibrator


def load_new_model_validation_status() -> str | None:
    """Read the bundle's own validation status from its training manifest.

    The retraining notebook (V4.2) writes ``VERSION.json`` alongside the
    models. ``validation_status`` there is the honest verdict of the training
    methodology ("experimental" while the calibrated bundle is being soaked,
    "validated" once field-checked). When the manifest is missing (legacy
    bundles) fall back to the hardcoded honest default — audit 2026-08-23
    (bug #17): offline validation of that bundle has open methodology issues.
    """
    try:
        with open(Path(config.NEW_MANIFEST_PATH), encoding="utf-8") as f:
            manifest = json.load(f)
        status = manifest.get("validation_status")
        if status in ("experimental", "validated"):
            return status
        logger.warning(
            f"VERSION.json validation_status={status!r} not recognised — defaulting to experimental"
        )
    except FileNotFoundError:
        pass
    except (PermissionError, json.JSONDecodeError, OSError) as e:
        logger.warning(f"Could not read VERSION.json ({e}) — defaulting to experimental")
    return "experimental"


def predict_batch(
    X: np.ndarray,
    cnn_model: Any | None = None,
    lgbm_model: Any | None = None,
    batch_size: int = 64,
) -> tuple[np.ndarray, np.ndarray]:
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
                batch = _torch.tensor(X[i : i + batch_size], dtype=_torch.float32).to(config.DEVICE)
                logits = cnn_model(batch)
                probs = _torch.sigmoid(logits).cpu().numpy()
                logger.info(f"CNN batch logits: {logits[:3].cpu().numpy()}, probs: {probs[:3]}")
                cnn_probs.extend(probs)
        cnn_probs = np.array(cnn_probs).flatten()
        logger.info(f"CNN final probs: {cnn_probs[:5]}")

        # Apply calibration via the shared helper (src/calibration.py) so the
        # CNN/LGBM mean-shift heuristics live in one unit-testable place.
        from src.calibration import calibrate_cnn_probs

        cnn_probs = calibrate_cnn_probs(cnn_probs)
    except Exception as e:
        logger.error(f"CNN prediction failed: {e}")
        raise PredictionError(f"CNN prediction failed: {e}")

    # LightGBM Prediction
    lgbm_probs = None
    try:
        logger.info("Running LightGBM prediction...")
        lgbm_probs = lgbm_model.predict(X)
        logger.info(f"LightGBM raw predictions: {lgbm_probs[:5]}")

        from src.calibration import calibrate_lgbm_probs

        lgbm_probs = calibrate_lgbm_probs(lgbm_probs)
    except (AttributeError, RuntimeError, ValueError, TypeError) as e:
        logger.warning(
            f"predict_batch: LightGBM .predict() raised {type(e).__name__}: {e}. "
            "Falling back to _safe_lgbm_predict helper."
        )
        lgbm_probs = _safe_lgbm_predict(lgbm_model, X)

    # Ensure probabilities are in valid range
    cnn_probs = np.clip(cnn_probs, 0.0, 1.0)
    lgbm_probs = np.clip(lgbm_probs, 0.0, 1.0)

    return cnn_probs, lgbm_probs


# ---------------------------------------------------------------------------
# LGBM-safe prediction helper
# ---------------------------------------------------------------------------


def _safe_lgbm_predict(lgbm_model: Any, X: np.ndarray) -> np.ndarray:
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

    IMPORTANT: On total prediction failure this function RAISES ``RuntimeError``
       rather than returning a silent 0.5 array. A bogus "Medium" risk label
       could hide a real fire (AGENTS.md §3, bug #3). Callers wrap as
       ``PredictionError`` → HTTP 500, or flag the point as ``status="error"``
       in AOI batch (see ``src/geo/services.py::run_aoi_batch``).
    """
    # ── Detect model type ────────────────────────────────────────────────
    try:
        # ── Path A: native lightgbm.Booster — direct raw→sigmoid pipeline ──
        try:
            from lightgbm import Booster as _LGBBooster

            is_booster = isinstance(lgbm_model, _LGBBooster)
        except ImportError:
            is_booster = False

        if is_booster:
            # ``Booster.predict`` already applies the objective link (sigmoid
            # for binary), so its default output is a PROBABILITY. Squashing
            # it again would pull every score toward 0.5 (e.g. 0.93 → 0.72)
            # and silently corrupt the stack. Ask for the raw margin
            # explicitly and apply the sigmoid exactly once.
            try:
                raw_margin = lgbm_model.predict(X, raw_score=True)
            except TypeError:  # very old Booster without raw_score
                probs = np.asarray(lgbm_model.predict(X), dtype=float)
                return np.clip(probs, 0.0, 1.0)
            if raw_margin is None:
                raise RuntimeError("Booster.predict(raw_score=True) returned None")
            probs = 1.0 / (1.0 + np.exp(-np.asarray(raw_margin, dtype=float)))
            logger.info(f"LGBM Booster → probability range [{probs.min():.4f}, {probs.max():.4f}]")
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
            raise RuntimeError("LightGBM .predict() returned None")

        # No usable prediction method: fail loudly instead of falling off the
        # end of the function (which used to return ``None`` and surface later
        # as a confusing ``AttributeError: 'NoneType' has no attribute min``).
        raise RuntimeError(
            f"Unsupported LightGBM model object {type(lgbm_model).__name__}: "
            "expected predict_proba() or predict()."
        )

    except RuntimeError:
        raise
    except Exception as e:
        logger.error("_safe_lgbm_predict: all LGBM prediction paths failed: %s", e, exc_info=True)
        # NEVER return a silent 0.5 (AGENTS.md §3, bug #3). Raise so the caller
        # can surface a real error instead of a bogus "Medium" risk label.
        raise RuntimeError(f"LightGBM prediction failed entirely: {e}") from e


def predict_stacking(
    X: np.ndarray,
    lgbm_model: Any | None = None,
    xgb_model: Any | None = None,
    meta_model: Any | None = None,
) -> np.ndarray:
    """Combine the two base learners with the trained two-leg meta-learner.

    Args:
        X: Scaled engineered feature matrix, shape ``(n_samples, 34)``.
        lgbm_model: Optional pre-loaded LightGBM leg.
        xgb_model: Optional pre-loaded XGBoost leg.
        meta_model: Optional pre-loaded meta-learner (LogisticRegressionCV).

    Missing legs are loaded from the active bundle. Supplied models are never
    replaced, which keeps test stubs and alternate bundles working.

    Returns:
        Calibrated-agnostic stack probability array of shape ``(n_samples,)``.
        The isotonic calibrator is applied by :func:`predict_fire_risk`, which
        owns the threshold decision.

    Raises:
        ModelLoadError: if a missing leg cannot be loaded.
        RuntimeError: if a base model or the meta-learner fails. Never falls
            back to a silent 0.5 (AGENTS.md §3).
    """
    # Local import keeps the legacy ``predict`` module import torch-free and
    # avoids depending on module-global registration side effects.
    from src.models.xgb import predict_xgb

    if lgbm_model is None or xgb_model is None or meta_model is None:
        loaded_lgbm, loaded_xgb, loaded_meta = load_stacking_models()
        if lgbm_model is None:
            lgbm_model = loaded_lgbm
        if xgb_model is None:
            xgb_model = loaded_xgb
        if meta_model is None:
            meta_model = loaded_meta

    expected_legs = getattr(meta_model, "n_features_in_", None)
    if expected_legs != 2:
        raise ValueError(
            "meta_model must take exactly [p_lgbm, p_xgb] (2 features); "
            f"got n_features_in_={expected_legs!r}. The GRU leg was retired."
        )

    lgbm_probs = _safe_lgbm_predict(lgbm_model, X)
    xgb_probs = predict_xgb(xgb_model, X)

    if lgbm_probs.shape[0] != X.shape[0] or xgb_probs.shape[0] != X.shape[0]:
        raise RuntimeError(
            "Base-learner output length mismatch: "
            f"X={X.shape[0]}, lgbm={lgbm_probs.shape[0]}, xgb={xgb_probs.shape[0]}"
        )

    meta_features = np.column_stack([lgbm_probs, xgb_probs])
    ensemble_probs = np.asarray(meta_model.predict_proba(meta_features)[:, 1], dtype=float)
    ensemble_probs = np.clip(ensemble_probs, 0.0, 1.0)

    logger.info(
        "2-leg stack: LGBM mean=%.4f XGB mean=%.4f -> meta mean=%.4f",
        float(np.mean(lgbm_probs)),
        float(np.mean(xgb_probs)),
        float(np.mean(ensemble_probs)),
    )
    return ensemble_probs


def predict_fire_risk(
    features: dict[str, Any],
    model_version: str | None = None,
    model_type: str = "new",
    use_cache: bool = False,
    reference_date: datetime | None = None,
) -> dict[str, Any]:
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
        use_cache: If True, the result is served from a 5-minute TTL cache
            keyed by ``(features, model_version, model_type)`` when available.
            Default False to preserve deterministic behaviour for callers
            that re-mutate the returned dict (e.g. test_prediction). Set
            True only at idempotent call sites (REST /predict, AOI reruns).
        reference_date: Optional explicit anchor date for temporal feature
            derivations (``month``, ``day``, ``doy``). ROADMAP §3-W1 feeds
            the SPA Header date-scrubber through this parameter so the
            "What was the fire risk on 2026-06-15?" workflow recomputes
            seasonal features instead of always anchoring on "today".
            ``None`` ⇒ historical behaviour (``datetime.now()``).

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
    # Audit priority 2 — best-effort TTL cache for idempotent inference.
    # Misses and disabled caches fall through transparently.
    if use_cache:
        try:
            from src.cache import cache_get, cache_set

            _cache_key = {
                "features": features,
                "model_version": model_version,
                "model_type": model_type,
                # Seasonal features (month/day/doy) depend on this anchor;
                # omitting it served yesterday's-date score for a replay.
                "reference_date": reference_date.isoformat() if reference_date else None,
            }
            hit, cached = cache_get(_cache_key)
            if hit:
                logger.debug("predict_fire_risk cache hit")
                # Return a copy: AOI batch mutates the result with lat/lon/row/
                # col, and mutating the cached object would leak those fields
                # into later single-point responses for the same key.
                return copy.deepcopy(cached)
        except Exception as e:  # pragma: no cover — cache must never block
            logger.debug("cache_get skipped: %s", e)
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

        # Create feature vector using correct feature set for model type.
        # ``reference_date`` (optional) shifts the seasonal/month features
        # to the user-picked date — see ROADMAP §3-W1.
        feature_vector = _create_feature_vector(
            features,
            use_new_features=(model_type == "new"),
            reference_date=reference_date,
        )

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

            cnn_probs, lgbm_probs = predict_batch(feature_vector_scaled, cnn_model, lgbm_model)

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
                with open(config.FEATURE_COLUMNS_PATH) as f:
                    legacy_feature_cols = json.load(f)
                shap_explanation = _compute_shap_explanation(
                    features,
                    lgbm_model,
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
            # Active serving path: V4.2 two-leg cross-section stack. LGBM and
            # XGBoost probabilities are combined by a LogisticRegressionCV
            # meta-learner; the isotonic calibrator is applied below. The GRU
            # leg was retired with V4.2, so no sequence/raw-feature plumbing
            # remains in the serving contract. ``feature_vector`` was built by
            # the shared call above with ``use_new_features=True``.
            logger.info("Feature vector shape: %s", feature_vector.shape)

            new_feature_cols = load_new_feature_columns()
            try:
                new_scaler = load_new_model_scaler()
                # ``scaler_all.pkl`` was fitted on a named DataFrame. Passing a
                # bare ndarray still works (same order) but emits a sklearn
                # warning on every request; passing the frame keeps the column
                # order explicit and validated by sklearn itself.
                if feature_vector.shape[1] == len(new_feature_cols):
                    scaler_input = pd.DataFrame(feature_vector, columns=new_feature_cols)
                else:
                    scaler_input = feature_vector
                feature_vector_scaled = new_scaler.transform(scaler_input)
            except Exception as exc:
                logger.warning("Could not load new scaler (%s); using raw features", exc)
                feature_vector_scaled = feature_vector

            lgbm_model, xgb_model, meta_model = load_stacking_models()
            ensemble_prob = float(
                predict_stacking(
                    feature_vector_scaled,
                    lgbm_model=lgbm_model,
                    xgb_model=xgb_model,
                    meta_model=meta_model,
                )[0]
            )
            logger.info("Stack probability: %.4f", ensemble_prob)

            # --- Stack calibration (P3, V4.2) ---
            # Raw stack probabilities under-predict fire frequency by ~0.05-0.15
            # across every reliability bin (reliability audit 2026-08-29). The
            # isotonic calibrator is fitted on VAL inside the retraining notebook
            # and shipped as ``calibration_isotonic.pkl``. Absent file = legacy
            # bundle = no-op. Applied BEFORE the env-tunable temperature/cap
            # knobs so those remain ops levers on the calibrated surface.
            stack_calibrator = load_new_model_calibration()
            if stack_calibrator is not None:
                calibrated = float(
                    np.atleast_1d(stack_calibrator.predict(np.array([ensemble_prob], dtype=float)))[
                        0
                    ]
                )
                logger.info(
                    f"Stack calibration applied: {ensemble_prob:.4f} -> {calibrated:.4f} "
                    f"({type(stack_calibrator).__name__})"
                )
                ensemble_prob = calibrated

            # --- Calibration: Temperature scaling & probability capping ---
            # Temperature scaling reduces overconfidence by scaling logits before sigmoid.
            # T > 1 softens probabilities toward 0.5; T < 1 makes more extreme.
            temp = float(os.getenv("ENSEMBLE_TEMPERATURE", "1.0"))
            if temp != 1.0:
                # Avoid exactly 0 or 1 which break logit
                p_safe = np.clip(ensemble_prob, 1e-6, 1 - 1e-6)
                logit = np.log(p_safe / (1 - p_safe))
                ensemble_prob = 1.0 / (1.0 + np.exp(-logit / temp))
                logger.info(
                    f"Applied temperature scaling (T={temp}): adjusted_prob={ensemble_prob:.4f}"
                )

            # Optional hard cap on maximum probability
            max_prob = float(os.getenv("MAX_PROBABILITY", "1.0"))
            if max_prob < 1.0 and ensemble_prob > max_prob:
                logger.warning(f"Capping probability from {ensemble_prob:.4f} to {max_prob:.4f}")
                ensemble_prob = max_prob
            # --- End calibration ---

            decision_threshold = load_new_model_threshold()

            cnn_prob = float(ensemble_prob)  # For stacking model, CNN prob = ensemble prob
            lgbm_prob = float(ensemble_prob)  # For stacking model, LGBM prob = ensemble prob
            disagreement = 0.0  # No disagreement in ensemble model
            model_name_used = "Model Stacking"

            shap_explanation = {}
            try:
                shap_explanation = _compute_shap_explanation(
                    features,
                    lgbm_model,
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
                # Binary decision cut-off fitted on the calibrated scale
                # (threshold_config.json). ``risk_level`` stays the four-band
                # UI taxonomy and is not derived from this value.
                "decision_threshold": float(decision_threshold),
                # Audit 2026-08-23 (bug #17) / P3 2026-08-29: the badge is
                # data-driven from the bundle's own manifest (``validation_status``
                # in VERSION.json, written by the retraining notebook). V4.1
                # bundles (no manifest) honestly default to "experimental".
                # The SPA renders it as an "experimental" badge.
                "model_validation_status": load_new_model_validation_status(),
            }

            logger.info(
                f"Prediction result: {result['risk_level']} (score: {result['risk_score']:.3f})"
            )
            if use_cache:
                try:
                    from src.cache import cache_set

                    cache_set(
                        {
                            "features": features,
                            "model_version": model_version,
                            "model_type": model_type,
                            "reference_date": (
                                reference_date.isoformat() if reference_date else None
                            ),
                        },
                        copy.deepcopy(result),
                    )
                except Exception as e:  # pragma: no cover — never block on write
                    logger.debug("cache_set skipped: %s", e)
            return result

    except Exception as e:
        logger.error(f"Prediction failed: {e}")
        raise PredictionError(f"Failed to run prediction: {e}")


def _calculate_risk_factors(features: dict[str, Any]) -> dict[str, float]:
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
    features: dict[str, Any],
    lgbm_model: Any,
    feature_vector: np.ndarray | None = None,
    feature_columns: list | None = None,
) -> dict[str, Any]:
    """Compute SHAP explanation for a single prediction.

    Task 6.7 (UI Revamp Fase 6): body migrated to
    :func:`src.features.shap_explain.compute_shap_explanation`. This wrapper
    preserves the underscore alias + kwargs signature that callers in
    predict.py still use, so behaviour is bit-for-bit identical without any
    change at call sites.

    Args:
        features: Input feature dictionary (fallback if feature_vector not provided).
        lgbm_model: LightGBM model.
        feature_vector: Pre-built engineered feature vector (1, n_features). Preferred.
        feature_columns: Feature column names corresponding to feature_vector.

    Returns:
        Dictionary with top contributing features and their SHAP values, or
        ``{}`` on failure (graceful — never raises per AGENTS.md §6 fallback
        philosophy).
    """
    from src.features.shap_explain import compute_shap_explanation

    return compute_shap_explanation(
        features=features,
        lgbm_model=lgbm_model,
        feature_vector=feature_vector,
        feature_columns=feature_columns,
    )


def _estimate_temporal_feature(
    col_name: str, current_val: float, month: int, doy: int
) -> tuple[float, float]:
    """Estimate lag3 + roll7 for a single feature value.

    Task 6.7 (UI Revamp Fase 6): body migrated to
    :func:`src.features.single_inference.estimate_temporal_feature`. This
    wrapper preserves the underscore alias used by :func:`_create_feature_vector`
    (which itself delegates to ``single_inference.create_feature_vector``).
    """
    from src.features.single_inference import estimate_temporal_feature

    return estimate_temporal_feature(col_name, current_val, month, doy)


def _create_feature_vector(
    features: dict[str, Any],
    use_new_features: bool = False,
    reference_date: datetime | None = None,
) -> np.ndarray:
    """Create feature vector from input features.

    Thin re-export of :func:`src.features.single_inference.create_feature_vector`
    (Task 6.7). ``reference_date`` (ROADMAP §3-W1) anchors the seasonal
    features to a caller-picked date; ``None`` falls back to "today" which
    is the historical behaviour.
    """
    from src.features.single_inference import create_feature_vector

    return create_feature_vector(
        features,
        use_new_features=use_new_features,
        reference_date=reference_date,
    )


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


def predict_from_csv(csv_path: str | Path, output_path: str | Path | None = None) -> pd.DataFrame:
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
    with open(config.FEATURE_COLUMNS_PATH) as f:
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
        from src.models.ensemble import evaluate_ensemble

        evaluate_ensemble(y_test.values, cnn_probs, lgbm_probs)

    except Exception as e:
        logger.error(f"Evaluation failed: {e}")
        raise


if __name__ == "__main__":
    main()
