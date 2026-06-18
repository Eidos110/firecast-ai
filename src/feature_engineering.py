import pandas as pd
import numpy as np

def add_temporal_features(df, numeric_cols, lag=3, roll=7):
    for col in numeric_cols:
        if col not in ['label']:
            df[f'{col}_lag{lag}'] = df[col].shift(lag)
            df[f'{col}_roll{roll}'] = df[col].rolling(window=roll, min_periods=1).mean()
    return df

def add_fire_indices(df):
    df = df.copy()
    df['vpd'] = df['temp_max'] - df['dewpoint']
    df['wind_mag'] = np.sqrt(df['wind_u']**2 + df['wind_v']**2)
    df['dry_day'] = (df['precip'] < 1.0).astype(int)
    df['dry_spell_7'] = df['dry_day'].rolling(7, min_periods=1).sum()
    df['dry_spell_30'] = df['dry_day'].rolling(30, min_periods=1).sum()
    df['fuel_dryness'] = df['vpd'] * (1 - df['ndvi'])
    df['hot_threshold'] = (df['temp_max'] > df['temp_max'].quantile(0.75)).astype(int)
    df['dry_threshold'] = (df['vpd'] > df['vpd'].quantile(0.75)).astype(int)
    df['windy_threshold'] = (df['wind_speed'] > df['wind_speed'].quantile(0.75)).astype(int)
    df['extreme_fire_weather'] = df['hot_threshold'] + df['dry_threshold'] + df['windy_threshold']
    return df

def _safe_divide_series(numerator, denominator, epsilon=1e-8):
    """Safe division for pandas Series to prevent division by zero."""
    denom_safe = denominator.copy()
    denom_safe = denom_safe.replace(0, epsilon)
    return numerator / denom_safe

def add_spectral_indices(df):
    df = df.copy()
    df['ndwi'] = _safe_divide_series(df['B3'] - df['B11'], df['B3'] + df['B11'])
    df['nbr'] = _safe_divide_series(df['B8'] - df['B12'], df['B8'] + df['B12'])
    df['evi'] = 2.5 * _safe_divide_series(df['B8'] - df['B4'], df['B8'] + 6*df['B4'] - 7.5*df['B2'] + 1)
    return df

def add_cyclical_time(df):
    df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
    df['doy'] = pd.to_datetime(df['time']).dt.dayofyear
    df['doy_sin'] = np.sin(2 * np.pi * df['doy'] / 365)
    df['doy_cos'] = np.cos(2 * np.pi * df['doy'] / 365)
    return df

def add_trend_features(df):
    df['temp_change_3d'] = df['temp_max'].diff(3)
    df['wind_change_3d'] = df['wind_speed'].diff(3)
    df['precip_deficit_7d'] = np.maximum(df['precip'].rolling(7).mean() - df['precip'].mean(), 0)
    df['extreme_days_5d'] = (df['extreme_fire_weather'].rolling(5).sum() > 0).astype(int)
    return df

def engineer_features(df, lag=3, roll=7):
    """Gabungan semua langkah feature engineering"""
    df = df.copy()
    df['time'] = pd.to_datetime(df['time'])
    df = df.sort_values('time').reset_index(drop=True)
    
    numeric_cols = df.select_dtypes(include=[np.number]).columns.drop(['label'])
    df = add_temporal_features(df, numeric_cols, lag, roll)
    df = add_fire_indices(df)
    df = add_spectral_indices(df)
    df = add_cyclical_time(df)
    df = add_trend_features(df)
    
    # Ganti infinite dengan NaN, lalu drop
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df.dropna(inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df