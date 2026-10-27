"""Data loading helpers (ROADMAP §2-I — Parquet-first).

The preprocessing pipeline produces two artefact formats in `data/`:
  - ``*.csv`` — human-readable, but slow to ingest (text parsing + type
    inference per column), particularly bad on the 100 MB+ processed
    features file used by ``/predict``.
  - ``*.parquet`` — columnar, schema-preserved, snappy-compressed.
    ``pd.read_parquet`` is 5–10× faster and uses less peak RAM than CSV.

Resolution rule: prefer Parquet **iff** the same-stem `.parquet` file
sits next to the requested `.csv`. Falls back to CSV silently so legacy
deployments that have not run ``scripts/migrate_to_parquet.py`` keep
working without any code path change.
"""

import json
from pathlib import Path

import joblib
import pandas as pd

from src import config
from src.feature_engineering import engineer_features


def _resolve_tabular(path: Path) -> Path:
    """Return the ``.parquet`` twin if it exists, else the original path.

    The lookup is intentionally stale-cache-free: we hit the filesystem on
    every call so an operator can drop in a rebuilt Parquet file and have it
    picked up on the next request without a worker restart. The cost of a
    single ``Path.exists`` stat is trivial next to a CSV parse.
    """
    if path.suffix == ".csv":
        parquet_twin = path.with_suffix(".parquet")
        if parquet_twin.exists():
            return parquet_twin
    return path


def _read_tabular(path: Path) -> pd.DataFrame:
    """Load CSV or Parquet transparently based on the resolved suffix."""
    resolved = _resolve_tabular(path)
    if resolved.suffix == ".parquet":
        # ``columns=None`` keeps full column set; pyarrow's Parquet reader
        # preserves dtypes (category, timestamp, …) so downstream code
        # doesn't need to re-cast. Requires ``pyarrow`` (already in
        # requirements.txt).
        return pd.read_parquet(resolved)
    return pd.read_csv(resolved)


def load_data_for_evaluation():
    """
    Load data, terapkan feature engineering, split temporal,
    dan scaling menggunakan scaler yang sudah disimpan.
    Mengembalikan X_test_scaled, y_test, dan nama fitur.
    """
    # Check file existence
    if not config.DATA_PATH.exists():
        raise FileNotFoundError(
            f"Data file not found at {config.DATA_PATH}. " "Check your DATA_PATH configuration."
        )
    df = _read_tabular(config.DATA_PATH)

    if not config.FEATURE_COLUMNS_PATH.exists():
        raise FileNotFoundError(
            f"Feature columns file not found at {config.FEATURE_COLUMNS_PATH}. "
            "Check your MODEL_DIR configuration."
        )
    with open(config.FEATURE_COLUMNS_PATH, encoding="utf-8") as f:
        feature_names = json.load(f)

    df = engineer_features(df, lag=config.LAG, roll=config.ROLL_WINDOW)

    # Pastikan hanya menggunakan feature yang ada
    available_cols = [col for col in feature_names if col in df.columns]
    X = df[available_cols]
    y = df["label"]

    # Split temporal 90/10 (sama seperti training)
    split_idx = int(config.TRAIN_SPLIT * len(df))
    X_test = X.iloc[split_idx:]
    y_test = y.iloc[split_idx:]

    # Muat scaler yang sudah di-fit saat training
    if not config.SCALER_PATH.exists():
        raise FileNotFoundError(
            f"Scaler file not found at {config.SCALER_PATH}. " "Check your MODEL_DIR configuration."
        )
    scaler = joblib.load(config.SCALER_PATH)
    X_test_scaled = scaler.transform(X_test)

    return X_test_scaled, y_test, feature_names
