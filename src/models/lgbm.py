"""LightGBM artifact loading.

The active V4.2 bundle stores a scikit-learn ``LGBMClassifier`` (joblib). Older
bundles occasionally shipped a native ``Booster`` or a ``{"booster": ...}``
wrapper, so the loader keeps a small compatibility ladder. It never silently
returns an unusable object: callers get a ``RuntimeError`` with the underlying
reason.
"""

from __future__ import annotations

import logging
from pathlib import Path

import joblib

from src import config

logger = logging.getLogger(__name__)


def load_lgbm_model(model_path: str | Path | None = None):
    """Load a LightGBM model from ``model_path`` (default: legacy bundle).

    Supported formats, in order:
      1. joblib/pickle of a scikit-learn model exposing ``predict``.
      2. A native ``lightgbm.Booster`` text model next to a ``.pkl`` path.
      3. joblib/pickle of ``{"booster": <model string>}``.

    Raises:
        RuntimeError: if no supported representation can be loaded.
    """
    if model_path is None:
        model_path = config.LGBM_MODEL_PATH
    model_path = Path(model_path)

    try:
        model = joblib.load(model_path)
    except Exception as exc:
        logger.debug("joblib load failed for %s: %s", model_path, exc)
        model = None

    if model is not None and hasattr(model, "predict"):
        return model

    # Legacy fallback: a native Booster saved as text next to the pickle.
    try:
        import lightgbm as lgb

        txt_path = model_path.with_suffix(".txt")
        if txt_path.exists():
            return lgb.Booster(model_file=str(txt_path))
    except Exception as exc:
        logger.debug("native LightGBM load failed for %s: %s", model_path, exc)

    # Wrapped Booster (older training exports).
    if isinstance(model, dict) and "booster" in model:
        try:
            import lightgbm as lgb

            return lgb.Booster(model_str=model["booster"])
        except Exception as exc:
            raise RuntimeError(f"Failed to rebuild LightGBM booster: {exc}") from exc

    raise RuntimeError(f"Could not load a usable LightGBM model from {model_path}")
