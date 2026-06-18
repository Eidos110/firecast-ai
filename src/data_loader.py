import pandas as pd
import json
import joblib
from src import config
from src.feature_engineering import engineer_features

def load_data_for_evaluation():
    """
    Load data, terapkan feature engineering, split temporal,
    dan scaling menggunakan scaler yang sudah disimpan.
    Mengembalikan X_test_scaled, y_test, dan nama fitur.
    """
    # Check file existence
    if not config.DATA_PATH.exists():
        raise FileNotFoundError(
            f"Data file not found at {config.DATA_PATH}. "
            "Check your DATA_PATH configuration."
        )
    df = pd.read_csv(config.DATA_PATH)
    
    if not config.FEATURE_COLUMNS_PATH.exists():
        raise FileNotFoundError(
            f"Feature columns file not found at {config.FEATURE_COLUMNS_PATH}. "
            "Check your MODEL_DIR configuration."
        )
    with open(config.FEATURE_COLUMNS_PATH, 'r', encoding='utf-8') as f:
        feature_names = json.load(f)
    
    df = engineer_features(df, lag=config.LAG, roll=config.ROLL_WINDOW)
    
    # Pastikan hanya menggunakan feature yang ada
    available_cols = [col for col in feature_names if col in df.columns]
    X = df[available_cols]
    y = df['label']
    
    # Split temporal 90/10 (sama seperti training)
    split_idx = int(config.TRAIN_SPLIT * len(df))
    X_test = X.iloc[split_idx:]
    y_test = y.iloc[split_idx:]
    
    # Muat scaler yang sudah di-fit saat training
    if not config.SCALER_PATH.exists():
        raise FileNotFoundError(
            f"Scaler file not found at {config.SCALER_PATH}. "
            "Check your MODEL_DIR configuration."
        )
    scaler = joblib.load(config.SCALER_PATH)
    X_test_scaled = scaler.transform(X_test)
    
    return X_test_scaled, y_test, feature_names