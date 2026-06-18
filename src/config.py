"""
FireCast Configuration Module
=============================
Unified configuration management with environment variable support.
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
import threading

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
# executable stack. We catch that and run in torch-less (demo/API-only) mode.
_torch_module = None
_torch_lock = threading.Lock()

def _get_torch():
    """Return torch module, loading it on first call. Returns None if unavailable."""
    global _torch_module
    if _torch_module is not None:
        return _torch_module
    with _torch_lock:
        if _torch_module is None:
            try:
                import torch as _t  # type: ignore
                _torch_module = _t
            except (ImportError, OSError):
                pass  # Railway: torch execstack blocked or not installed; run in demo mode
        return _torch_module


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
    def new_bigru_model_path(self) -> Path:
        return self.new_model_dir / "bi_gru_best.pth"

    @property
    def new_causal_gru_model_path(self) -> Path:
        """Path to the Causal GRU model (uni-directional, for real-time inference)."""
        return self.new_model_dir / "causal_gru_best.pth"

    @property
    def new_scaler_path(self) -> Path:
        return self.new_model_dir / "scaler_all.pkl"

    @property
    def new_scaler_raw_path(self) -> Path:
        """Path to scaler for raw features only (used by Causal GRU)."""
        return self.new_model_dir / "scaler_raw.pkl"

    @property
    def new_raw_features_path(self) -> Path:
        """Path to raw feature column names for Causal GRU."""
        return self.new_model_dir / "raw_features.json"

    @property
    def new_meta_model_path(self) -> Path:
        return self.new_model_dir / "stacking_weights.pkl"

    @property
    def new_meta_scaler_path(self) -> Path:
        """Path to scaler for meta-features (used by LogisticRegression meta-learner)."""
        return self.new_model_dir / "meta_scaler.pkl"

    @property
    def new_threshold_path(self) -> Path:
        return self.new_model_dir / "threshold_config.json"

    @property
    def new_feature_columns_path(self) -> Path:
        return self.new_model_dir / "feature_cols.json"


@dataclass
class ModelConfig:
    """Machine learning model configuration."""

    device: str = field(default_factory=lambda: os.getenv("ML_DEVICE", "auto"))
    cnn_dropout: float = field(
        default_factory=lambda: _get_float_env("CNN_DROPOUT", 0.3)
    )
    target_recall: float = field(
        default_factory=lambda: _get_float_env("TARGET_RECALL", 0.80)
    )

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

    train_split: float = field(
        default_factory=lambda: _get_float_env("TRAIN_SPLIT", 0.9)
    )
    lag: int = field(default_factory=lambda: _get_int_env("LAG_DAYS", 3))
    roll_window: int = field(
        default_factory=lambda: _get_int_env("ROLLING_WINDOW", 7)
    )


@dataclass
class APIConfig:
    """API server configuration."""

    host: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _get_int_env("API_PORT", 8000))
    enable_cors: bool = field(
        default_factory=lambda: os.getenv("ENABLE_CORS", "true").lower() == "true"
    )
    secret_key: Optional[str] = field(
        default_factory=lambda: os.getenv("API_SECRET_KEY")
    )


@dataclass
class FrontendConfig:
    """Frontend (Streamlit) configuration."""

    port: int = field(default_factory=lambda: _get_int_env("STREAMLIT_PORT", 8501))
    address: str = field(
        default_factory=lambda: os.getenv("STREAMLIT_ADDRESS", "localhost")
    )
    enable_demo_mode: bool = field(
        default_factory=lambda: os.getenv("ENABLE_DEMO_MODE", "false").lower() == "true"
    )


@dataclass
class WeatherAPIConfig:
    """Weather API configuration."""

    openweather_key: Optional[str] = field(
        default_factory=lambda: os.getenv("OPENWEATHER_API_KEY")
    )
    openweather_url: str = "https://api.openweathermap.org/data/2.5"
    bmkg_url: str = "https://api.bmkg.go.id/publik"

    @property
    def has_openweather_key(self) -> bool:
        """Check if OpenWeather API key is configured."""
        return self.openweather_key is not None and self.openweather_key != "demo_key"


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
        self.frontend = FrontendConfig()
        self.weather = WeatherAPIConfig()
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
            raise ValueError(
                f"TRAIN_SPLIT must be between 0 and 1, got {self.data.train_split}"
            )

        # Log configuration status
        logger.info(f"Configuration loaded successfully")
        logger.info(f"Device: {self.model.torch_device}")
        logger.info(f"Data path: {self.paths.data_path}")

        if not self.weather.has_openweather_key:
            logger.warning(
                "OpenWeather API key not configured - will use demo/backup data"
            )

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary (for debugging)."""
        return {
            "paths": {
                "base_dir": str(self.paths.base_dir),
                "data_dir": str(self.paths.data_dir),
                "models_dir": str(self.paths.models_dir),
            },
            "model": {
                "device": str(self.model.torch_device),
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
                "enable_cors": self.api.enable_cors,
            },
            "frontend": {
                "port": self.frontend.port,
                "enable_demo_mode": self.frontend.enable_demo_mode,
            },
            "weather": {
                "has_openweather_key": self.weather.has_openweather_key,
            },
        }


# Global configuration instance (lazy loading)
_config_instance: Optional[FireCastConfig] = None


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
    global NEW_CAUSAL_GRU_MODEL_PATH, NEW_SCALER_PATH, NEW_SCALER_RAW_PATH
    global NEW_RAW_FEATURES_PATH, NEW_META_MODEL_PATH, NEW_META_SCALER_PATH, NEW_THRESHOLD_PATH
    global NEW_FEATURE_COLUMNS_PATH
    global TRAIN_SPLIT, LAG, ROLL_WINDOW
    global CNN_DROPOUT, DEVICE, TARGET_RECALL

    BASE_DIR = str(cfg.paths.base_dir)
    DATA_PATH = str(cfg.paths.data_path)
    MODEL_DIR = str(cfg.paths.models_dir)
    CNN_MODEL_PATH = str(cfg.paths.cnn_model_path)
    LGBM_MODEL_PATH = str(cfg.paths.lgbm_model_path)
    SCALER_PATH = str(cfg.paths.scaler_path)
    THRESHOLD_PATH = str(cfg.paths.threshold_path)
    FEATURE_COLUMNS_PATH = str(cfg.paths.feature_columns_path)

    NEW_MODEL_DIR = str(cfg.paths.new_model_dir)
    NEW_LGBM_MODEL_PATH = str(cfg.paths.new_lgbm_model_path)
    NEW_XGB_MODEL_PATH = str(cfg.paths.new_xgb_model_path)
    NEW_CAUSAL_GRU_MODEL_PATH = str(cfg.paths.new_causal_gru_model_path)
    NEW_SCALER_PATH = str(cfg.paths.new_scaler_path)
    NEW_SCALER_RAW_PATH = str(cfg.paths.new_scaler_raw_path)
    NEW_RAW_FEATURES_PATH = str(cfg.paths.new_raw_features_path)
    NEW_META_MODEL_PATH = str(cfg.paths.new_meta_model_path)
    NEW_META_SCALER_PATH = str(cfg.paths.new_meta_scaler_path)
    NEW_THRESHOLD_PATH = str(cfg.paths.new_threshold_path)
    NEW_FEATURE_COLUMNS_PATH = str(cfg.paths.new_feature_columns_path)

    TRAIN_SPLIT = cfg.data.train_split
    LAG = cfg.data.lag
    ROLL_WINDOW = cfg.data.roll_window

    CNN_DROPOUT = cfg.model.cnn_dropout
    DEVICE = cfg.model.torch_device
    TARGET_RECALL = cfg.model.target_recall


# Initialize legacy variables on module load
_init_legacy_vars()


if __name__ == "__main__":
    # Print configuration for debugging
    config = get_config()
    import json

    logger.info(json.dumps(config.to_dict(), indent=2))
