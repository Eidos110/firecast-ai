"""
FireCast Configuration Module
=============================
Unified configuration management with environment variable support.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Setup logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ── Lazy torch import ──
# Railway/CPU environments may hit: ImportError: libtorch_cpu.so: cannot enable
# executable stack. We centralise the lazy-load in ``src.utils.lazy`` so every
# backend module shares one cached torch instance (avoids triplicate helpers).
def _get_torch():
    """Thin wrapper around the shared ``src.utils.lazy.get_torch`` helper.

    Returns the torch module (``None`` if unavailable) so existing legacy
    references ``config._get_torch()`` continue to work unchanged.
    """
    from src.utils.lazy import get_torch as _shared_get_torch

    torch_mod, _nn_mod = _shared_get_torch()
    return torch_mod


def _get_float_env(key: str, default: float) -> float:
    """Get float from environment with fallback to default on error."""
    val = os.getenv(key, str(default))
    try:
        return float(val)
    except (TypeError, ValueError):
        logger.warning(f"Invalid float for {key}: {val!r}. Using default {default}")
        return default


def _get_int_env(key: str, default: int) -> int:
    """Get int from environment with fallback to default on error."""
    val = os.getenv(key, str(default))
    try:
        return int(val)
    except (TypeError, ValueError):
        logger.warning(f"Invalid int for {key}: {val!r}. Using default {default}")
        return default


@dataclass
class PathsConfig:
    """Path configuration for the project."""

    base_dir: Path = field(default_factory=lambda: Path(__file__).parent.parent)

    @property
    def data_dir(self) -> Path:
        return self.base_dir / "data"

    @property
    def models_dir(self) -> Path:
        return self.base_dir / "models"

    @property
    def logs_dir(self) -> Path:
        return self.base_dir / "logs"

    @property
    def new_model_dir(self) -> Path:
        return self.base_dir / "add_new_model"

    @property
    def data_path(self) -> Path:
        return self.data_dir / "firecast_data_readymodelling_final_V3.csv"

    @property
    def processed_features_path(self) -> Path:
        """Derived/inference-ready features CSV used by geo_api.py cache."""
        return self.data_dir / "processed_firecast_features_v3.csv"

    @property
    def locations_path(self) -> Path:
        """Indonesian city registry ``{key: {name, lat, lon}}`` served by
        ``GET /geo/locations`` for the React SPA sidebar lookup. Single source
        of truth shared by the API and the geocode fallback."""
        return self.data_dir / "locations.json"

    @property
    def cnn_model_path(self) -> Path:
        return self.models_dir / "cnn_best.pth"

    @property
    def lgbm_model_path(self) -> Path:
        return self.models_dir / "lgbm_best.pkl"

    @property
    def scaler_path(self) -> Path:
        return self.models_dir / "scaler.pkl"

    @property
    def threshold_path(self) -> Path:
        return self.models_dir / "ensemble_threshold.pkl"

    @property
    def feature_columns_path(self) -> Path:
        return self.models_dir / "feature_columns.json"

    @property
    def new_lgbm_model_path(self) -> Path:
        return self.new_model_dir / "lgb_model.pkl"

    @property
    def new_xgb_model_path(self) -> Path:
        return self.new_model_dir / "xgb_model.pkl"

    @property
    def new_scaler_path(self) -> Path:
        return self.new_model_dir / "scaler_all.pkl"

    @property
    def new_meta_model_path(self) -> Path:
        """Meta-learner of the two-leg stack (``LogisticRegressionCV``)."""
        return self.new_model_dir / "stacking_weights.pkl"

    @property
    def new_threshold_path(self) -> Path:
        return self.new_model_dir / "threshold_config.json"

    @property
    def new_calibration_path(self) -> Path:
        """Path to the stack probability calibrator (P3, V4.2).

        Optional artifact: a fitted ``IsotonicRegression`` mapping raw stack
        probabilities to calibrated fire frequencies. Absent for 3-leg V4.1
        bundles — the serving path must treat that as a no-op, not an error.
        """
        return self.new_model_dir / "calibration_isotonic.pkl"

    @property
    def new_manifest_path(self) -> Path:
        """Training manifest emitted by the retraining notebook (VERSION.json).

        Carries bundle-level metadata (schema, validation status). Absent for
        legacy bundles — readers must default sensibly.
        """
        return self.new_model_dir / "VERSION.json"

    @property
    def new_feature_columns_path(self) -> Path:
        return self.new_model_dir / "feature_cols.json"


@dataclass
class ModelConfig:
    """Machine learning model configuration."""

    device: str = field(default_factory=lambda: os.getenv("ML_DEVICE", "auto"))
    cnn_dropout: float = field(default_factory=lambda: _get_float_env("CNN_DROPOUT", 0.3))
    target_recall: float = field(default_factory=lambda: _get_float_env("TARGET_RECALL", 0.80))

    @property
    def torch_device(self):  # type: ignore[override]
        """Get PyTorch device (lazy import). Falls back to CPU if torch unavailable."""
        torch = _get_torch()
        if torch is None:
            import logging

            logging.warning("PyTorch not available; ML features disabled.")
            return "cpu"
        if self.device == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        return torch.device(self.device)


@dataclass
class DataConfig:
    """Data processing configuration."""

    train_split: float = field(default_factory=lambda: _get_float_env("TRAIN_SPLIT", 0.9))
    lag: int = field(default_factory=lambda: _get_int_env("LAG_DAYS", 3))
    roll_window: int = field(default_factory=lambda: _get_int_env("ROLLING_WINDOW", 7))


@dataclass
class APIConfig:
    """API server configuration."""

    host: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _get_int_env("API_PORT", 8000))
    secret_key: str | None = field(default_factory=lambda: os.getenv("API_SECRET_KEY"))


class FireCastConfig:
    """
    Main configuration class for FireCast.

    This class provides a unified interface to all configuration settings.
    It automatically loads values from environment variables with sensible defaults.

    Usage:
        config = FireCastConfig()
        print(config.paths.data_dir)
        print(config.model.torch_device)
    """

    def __init__(self):
        self.paths = PathsConfig()
        self.model = ModelConfig()
        self.data = DataConfig()
        self.api = APIConfig()
        self._validate()

    def _validate(self):
        """Validate configuration settings."""
        # Validate paths exist
        if not self.paths.data_dir.exists():
            logger.warning(f"Data directory does not exist: {self.paths.data_dir}")

        if not self.paths.models_dir.exists():
            logger.warning(f"Models directory does not exist: {self.paths.models_dir}")

        # Validate split ratio
        if not 0 < self.data.train_split < 1:
            raise ValueError(f"TRAIN_SPLIT must be between 0 and 1, got {self.data.train_split}")

        # Log configuration status. NOTE: we intentionally do NOT resolve
        # ``self.model.torch_device`` here — that would eagerly import torch
        # at module load time (slow + breaks Railway sandbox). The device is
        # resolved lazily on first access by code that actually needs it.
        logger.info("Configuration loaded successfully")
        logger.info(f"Data path: {self.paths.data_path}")

    @property
    def device_str(self) -> str:
        """Return the configured ML device as a string without forcing torch import.

        Mirrors :pyattr:`ModelConfig.torch_device` but never raises (returns
        ``"cpu"`` if torch is unavailable). Useful for ``logging`` /
        ``to_dict`` contexts where importing torch would be undesirable.
        """
        if self.model.device == "auto":
            torch_mod = _get_torch()
            if torch_mod is None:
                return "cpu"
            return "cuda" if torch_mod.cuda.is_available() else "cpu"
        return self.model.device

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary (for debugging)."""
        return {
            "paths": {
                "base_dir": str(self.paths.base_dir),
                "data_dir": str(self.paths.data_dir),
                "models_dir": str(self.paths.models_dir),
            },
            "model": {
                "device": self.device_str,
                "cnn_dropout": self.model.cnn_dropout,
                "target_recall": self.model.target_recall,
            },
            "data": {
                "train_split": self.data.train_split,
                "lag": self.data.lag,
                "roll_window": self.data.roll_window,
            },
            "api": {
                "host": self.api.host,
                "port": self.api.port,
            },
        }


# Global configuration instance (lazy loading)
_config_instance: FireCastConfig | None = None


def get_config() -> FireCastConfig:
    """Get the global configuration instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = FireCastConfig()
    return _config_instance


# Legacy compatibility - module-level variables
# These are kept for backward compatibility with existing code
def _init_legacy_vars():
    """Initialize legacy module-level variables."""
    cfg = get_config()

    global BASE_DIR, DATA_PATH, MODEL_DIR
    global CNN_MODEL_PATH, LGBM_MODEL_PATH, SCALER_PATH
    global THRESHOLD_PATH, FEATURE_COLUMNS_PATH
    global NEW_MODEL_DIR, NEW_LGBM_MODEL_PATH, NEW_XGB_MODEL_PATH
    global NEW_SCALER_PATH, NEW_META_MODEL_PATH, NEW_THRESHOLD_PATH
    global NEW_FEATURE_COLUMNS_PATH, NEW_CALIBRATION_PATH, NEW_MANIFEST_PATH
    global TRAIN_SPLIT, LAG, ROLL_WINDOW
    global CNN_DROPOUT, DEVICE, TARGET_RECALL

    # NOTE: path-like legacy vars are ``pathlib.Path`` (not ``str``) because
    # several call-sites (src/data_loader.py) invoke ``.exists()`` on them.
    # ``Path`` is a drop-in for ``open()``, ``pandas.read_csv``,
    # ``joblib.load`` and ``Path(...)`` arithmetic, so downstream code is
    # unaffected. String-data vars (BASE_DIR etc.) stay ``str``.
    BASE_DIR = str(cfg.paths.base_dir)
    DATA_PATH = cfg.paths.data_path
    MODEL_DIR = cfg.paths.models_dir
    CNN_MODEL_PATH = cfg.paths.cnn_model_path
    LGBM_MODEL_PATH = cfg.paths.lgbm_model_path
    SCALER_PATH = cfg.paths.scaler_path
    THRESHOLD_PATH = cfg.paths.threshold_path
    FEATURE_COLUMNS_PATH = cfg.paths.feature_columns_path

    NEW_MODEL_DIR = cfg.paths.new_model_dir
    NEW_LGBM_MODEL_PATH = cfg.paths.new_lgbm_model_path
    NEW_XGB_MODEL_PATH = cfg.paths.new_xgb_model_path
    NEW_SCALER_PATH = cfg.paths.new_scaler_path
    NEW_META_MODEL_PATH = cfg.paths.new_meta_model_path
    NEW_THRESHOLD_PATH = cfg.paths.new_threshold_path
    NEW_FEATURE_COLUMNS_PATH = cfg.paths.new_feature_columns_path
    NEW_CALIBRATION_PATH = cfg.paths.new_calibration_path
    NEW_MANIFEST_PATH = cfg.paths.new_manifest_path

    TRAIN_SPLIT = cfg.data.train_split
    LAG = cfg.data.lag
    ROLL_WINDOW = cfg.data.roll_window

    CNN_DROPOUT = cfg.model.cnn_dropout
    # NOTE: DEVICE is intentionally NOT set here to avoid eagerly importing
    # torch at module load time. It is resolved lazily on first attribute
    # access via the module-level ``__getattr__`` below.
    TARGET_RECALL = cfg.model.target_recall


# Initialize legacy variables on module load (torch-free path).
_init_legacy_vars()


def _resolve_device():
    """Resolve the runtime ML device string, importing torch on demand.

    Returns ``"cpu"`` if torch is unavailable (Railway sandbox).
    """
    torch_mod = _get_torch()
    if torch_mod is None:
        return "cpu"
    # cfg.model.device is "auto" by default → pick cuda if available
    config_device = get_config().model.device
    if config_device and config_device != "auto":
        return config_device
    return "cuda" if torch_mod.cuda.is_available() else "cpu"


def __getattr__(name):
    """Lazy module attribute hook.

    Currently used to lazily resolve ``DEVICE`` on first access so that
    importing ``src.config`` does NOT eagerly import torch (preserves the
    Railway sandbox survival guarantee documented in AGENTS §3).
    """
    if name == "DEVICE":
        device_value = _resolve_device()
        # Cache as a real module attribute so subsequent lookups bypass
        # ``__getattr__`` (allows ``config.DEVICE = ...`` overrides too).
        globals()["DEVICE"] = device_value
        return device_value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


if __name__ == "__main__":
    # Print configuration for debugging
    config = get_config()
    import json

    logger.info(json.dumps(config.to_dict(), indent=2))
