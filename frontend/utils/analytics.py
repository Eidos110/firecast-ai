"""
FireCast Historical Analytics
==============================
Provides real data analysis from the training CSV for the Historical Analysis tab.
"""

import os
import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from functools import lru_cache

import streamlit as st

_DATA_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "processed_firecast_features_v3.csv"
)


@st.cache_data(ttl=3600, show_spinner=False)
def _load_data() -> pd.DataFrame:
    """Load and preprocess the training CSV (cached)."""
    if not os.path.exists(_DATA_PATH):
        return pd.DataFrame()
    df = pd.read_csv(_DATA_PATH)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
    return df


@st.cache_data(ttl=3600, show_spinner=False)
def get_overview_stats() -> Dict[str, Any]:
    """Get overall dataset statistics."""
    df = _load_data()
    if df.empty:
        return _empty_stats()

    total = len(df)
    fires = int((df["label"] == 1).sum())
    no_fires = int((df["label"] == 0).sum())
    fire_rate = fires / total * 100 if total > 0 else 0

    date_min = df["time"].min()
    date_max = df["time"].max()

    unique_locations = int(df.groupby(["lat", "lon"]).ngroups)

    # Extreme weather events
    if "extreme_fire_weather" in df.columns:
        extreme_events = int((df["extreme_fire_weather"] >= 1).sum())
    else:
        extreme_events = 0

    # Average conditions during fire events
    fire_df = df[df["label"] == 1]
    avg_temp = (
        float(fire_df["temp_max"].mean() - 273.15)
        if "temp_max" in fire_df.columns
        else 0
    )
    avg_wind = (
        float(fire_df["wind_speed"].mean()) if "wind_speed" in fire_df.columns else 0
    )
    avg_ndvi = float(fire_df["ndvi"].mean()) if "ndvi" in fire_df.columns else 0

    return {
        "total_records": total,
        "fire_events": fires,
        "no_fire_events": no_fires,
        "fire_rate": round(fire_rate, 1),
        "date_start": str(date_min.date())
        if hasattr(date_min, "date")
        else str(date_min),
        "date_end": str(date_max.date())
        if hasattr(date_max, "date")
        else str(date_max),
        "unique_locations": unique_locations,
        "extreme_events": extreme_events,
        "avg_temp_c": round(avg_temp, 1),
        "avg_wind_ms": round(avg_wind, 1),
        "avg_ndvi": round(avg_ndvi, 3),
    }


@st.cache_data(ttl=3600, show_spinner=False)
def get_monthly_fire_data() -> pd.DataFrame:
    """Get monthly fire count and rate aggregation."""
    df = _load_data()
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["month_period"] = df["time"].dt.to_period("M")

    monthly = (
        df.groupby("month_period")
        .agg(
            total=("label", "count"),
            fires=("label", "sum"),
            avg_temp=("temp_max", "mean")
            if "temp_max" in df.columns
            else ("label", "mean"),
            avg_wind=("wind_speed", "mean")
            if "wind_speed" in df.columns
            else ("label", "mean"),
            avg_precip=("precip", "mean")
            if "precip" in df.columns
            else ("label", "mean"),
        )
        .reset_index()
    )

    monthly["fire_rate"] = (monthly["fires"] / monthly["total"] * 100).round(1)
    monthly["date"] = monthly["month_period"].dt.to_timestamp()
    monthly["label"] = monthly["month_period"].astype(str)

    if "avg_temp" in monthly.columns:
        monthly["avg_temp_c"] = (monthly["avg_temp"] - 273.15).round(1)

    return monthly[
        [
            "date",
            "label",
            "total",
            "fires",
            "fire_rate",
            "avg_temp_c" if "avg_temp_c" in monthly.columns else "fires",
            "avg_wind",
            "avg_precip",
        ]
    ]


@st.cache_data(ttl=3600, show_spinner=False)
def get_seasonal_pattern() -> pd.DataFrame:
    """Get fire rate aggregated by calendar month (across all years)."""
    df = _load_data()
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["cal_month"] = df["time"].dt.month

    seasonal = (
        df.groupby("cal_month")
        .agg(
            total=("label", "count"),
            fires=("label", "sum"),
        )
        .reset_index()
    )
    seasonal["fire_rate"] = (seasonal["fires"] / seasonal["total"] * 100).round(1)

    month_names = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
    ]
    seasonal["month_name"] = seasonal["cal_month"].apply(lambda m: month_names[m - 1])

    return seasonal[["cal_month", "month_name", "total", "fires", "fire_rate"]]


@st.cache_data(ttl=3600, show_spinner=False)
def get_geographic_hotspots(top_n: int = 20) -> pd.DataFrame:
    """Get top fire hotspot locations."""
    df = _load_data()
    if df.empty:
        return pd.DataFrame()

    fire_df = df[df["label"] == 1]
    hotspots = (
        fire_df.groupby(["lat", "lon"])
        .agg(
            fire_count=("label", "count"),
            avg_temp=("temp_max", "mean")
            if "temp_max" in fire_df.columns
            else ("label", "mean"),
            avg_wind=("wind_speed", "mean")
            if "wind_speed" in fire_df.columns
            else ("label", "mean"),
        )
        .reset_index()
    )

    hotspots = hotspots.sort_values("fire_count", ascending=False).head(top_n)
    if "avg_temp" in hotspots.columns:
        hotspots["avg_temp_c"] = (hotspots["avg_temp"] - 273.15).round(1)

    return hotspots


@st.cache_data(ttl=3600, show_spinner=False)
def get_weather_fire_correlation() -> Dict[str, Any]:
    """Calculate correlation between weather variables and fire occurrence."""
    df = _load_data()
    if df.empty:
        return {}

    weather_cols = ["temp_max", "wind_speed", "precip", "ndvi", "vpd", "fuel_dryness"]
    available = [c for c in weather_cols if c in df.columns]

    correlations = {}
    for col in available:
        corr = df[col].corr(df["label"])
        correlations[col] = round(float(corr), 3)

    # Temperature comparison: fire vs no-fire
    fire_df = df[df["label"] == 1]
    nofire_df = df[df["label"] == 0]

    comparison = {}
    for col in available:
        comparison[col] = {
            "fire_mean": round(float(fire_df[col].mean()), 4),
            "no_fire_mean": round(float(nofire_df[col].mean()), 4),
        }

    return {"correlations": correlations, "comparison": comparison}


@st.cache_data(ttl=3600, show_spinner=False)
def get_filtered_data(start_date: str, end_date: str) -> pd.DataFrame:
    """Get data filtered by date range."""
    df = _load_data()
    if df.empty:
        return pd.DataFrame()

    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date)
    return df[(df["time"] >= start) & (df["time"] <= end)]


def _empty_stats() -> Dict[str, Any]:
    return {
        "total_records": 0,
        "fire_events": 0,
        "no_fire_events": 0,
        "fire_rate": 0,
        "date_start": "N/A",
        "date_end": "N/A",
        "unique_locations": 0,
        "extreme_events": 0,
        "avg_temp_c": 0,
        "avg_wind_ms": 0,
        "avg_ndvi": 0,
    }
