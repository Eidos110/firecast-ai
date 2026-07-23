"""
Sidebar component for input parameters
"""

import streamlit as st
import pandas as pd
from typing import Dict, Any
import requests
import logging

from frontend.utils.weather_api import get_weather_data
from frontend.utils.gee_data import get_location_data

logger = logging.getLogger(__name__)

VEGETATION_TYPES = {
    "Savana": {"moisture_content": 35, "flammability": 0.8, "ndvi_default": 0.3},
    "Hutan Tropis Lembab": {"moisture_content": 60, "flammability": 0.5, "ndvi_default": 0.75},
    "Semak Kering": {"moisture_content": 20, "flammability": 0.95, "ndvi_default": 0.25},
    "Lahan Gambut": {"moisture_content": 45, "flammability": 0.7, "ndvi_default": 0.55},
    "Padang Rumput": {"moisture_content": 40, "flammability": 0.75, "ndvi_default": 0.4},
    "Hutan Pinus": {"moisture_content": 30, "flammability": 0.85, "ndvi_default": 0.6},
}

# Audit Fase 3b: the ~400-entry INDONESIA_LOCATIONS table was inlined
# here, taking ~430 lines and duplicating coords (e.g. "dki jakarta" /
# "jakarta" shared display name "Jakarta"; "buru" / "buru selatan"
# shared Namlea). It now lives in ``data/locations.json`` (378 deduped
# entries) and is loaded once per Streamlit session via the helper below.
import json as _json
import pathlib as _pathlib
from functools import lru_cache as _lru_cache


@_lru_cache(maxsize=1)
def _load_indonesia_locations() -> dict:
    """Load Indonesia location list from data/locations.json.

    Process-cached so repeated sidebar renders do NOT re-read the JSON.
    The file is ~30 KB at 378 entries, well under any sensible cache budget.
    Missing file falls back to an empty dict so the sidebar still renders
    (manual coords) rather than crashing the whole tab.
    """
    # Resolve via repo root (parents[2] from this file: sidebar.py inside
    # frontend/components/ -> repo root).
    repo_root = _pathlib.Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "data" / "locations.json",   # canonical location
        _pathlib.Path("data") / "locations.json",   # relative fallback (cwd)
    ]
    for pth in candidates:
        try:
            if pth.exists():
                with open(pth, "r", encoding="utf-8") as f:
                    return _json.load(f)
        except Exception as e:
            logger.warning("Failed loading locations.json from %s: %s", pth, e)
    logger.warning("locations.json not found; sidebar will present no presets.")
    return {}


INDONESIA_LOCATIONS = _load_indonesia_locations()


def geocode_location(location_name: str) -> Dict[str, Any]:
    """
    Geocode location name to coordinates
    Uses local database first, then falls back to Nominatim API
    """

    if not location_name:
        return None

    location_lower = location_name.lower().strip()

    # Check local database first
    for key, value in INDONESIA_LOCATIONS.items():
        if key in location_lower or location_lower in key:
            return {
                "lat": value["lat"],
                "lon": value["lon"],
                "name": value["name"],
                "source": "local",
            }

    # Try Nominatim API (OpenStreetMap) for other locations
    try:
        url = "https://nominatim.openstreetmap.org/search"
        params = {"q": f"{location_name}, Indonesia", "format": "json", "limit": 1}
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()

        results = response.json()
        if results:
            result = results[0]
            return {
                "lat": float(result["lat"]),
                "lon": float(result["lon"]),
                "name": result.get("display_name", location_name),
                "source": "nominatim",
            }
    except Exception as e:
        logger.error(f"Geocoding error: {e}")
        # Continue without location name - will use defaults

    return None


def _get_float(key: str, default: float) -> float:
    """Get a float value from session state, falling back to default if not numeric."""
    v = st.session_state.get(key, default)
    if isinstance(v, (int, float)):
        return float(v)
    return float(default)

def _get_int(key: str, default: int) -> int:
    """Get an int value from session state, falling back to default if not numeric."""
    v = st.session_state.get(key, default)
    if isinstance(v, (int, float)):
        return int(v)
    return int(default)


def render_sidebar() -> Dict[str, Any]:
    """
    Render sidebar input components.
    Returns dictionary with all input parameters.
    """
    
    input_data = {}
    
    # ── Location search / selection ───────────────────────────────────
    st.markdown("### 🔍 Lokasi")
    
    # Build display names for all locations (sorted, popular first)
    _location_display_names = ["-- Pilih Lokasi --"]
    _location_name_map = {}
    _popular = ["jakarta", "surabaya", "medan", "bandung", "yogyakarta",
                "riau", "kabupaten indragiri hulu", "pekanbaru"]
    for name in _popular:
        if name in INDONESIA_LOCATIONS:
            val = INDONESIA_LOCATIONS[name]
            display = val["name"]
            _location_display_names.append(display)
            _location_name_map[display] = name
    for key in INDONESIA_LOCATIONS:
        if key not in _popular:
            val = INDONESIA_LOCATIONS[key]
            display = val["name"]
            _location_display_names.append(display)
            _location_name_map[display] = key
    
    current_loc = st.session_state.get(
        "selected_location", {"lat": -1.1747, "lon": 100.4012, "name": "Indonesia (Default)"}
    )
    current_name = current_loc.get("name", "Indonesia (Default)")
    selected_display = current_name if current_name in _location_display_names else "-- Pilih Lokasi --"
    default_idx = _location_display_names.index(selected_display) if selected_display in _location_display_names else 0
    
    chosen_display = st.selectbox(
        "Pilih Lokasi",
        options=_location_display_names,
        index=default_idx,
        help="Cari dan pilih lokasi untuk prediksi",
    )
    
    if chosen_display != "-- Pilih Lokasi --":
        loc_key = _location_name_map[chosen_display]
        loc = INDONESIA_LOCATIONS[loc_key]
        st.session_state.selected_location = {
            "lat": loc["lat"],
            "lon": loc["lon"],
            "name": loc["name"],
        }
    
    selected_loc = st.session_state.get(
        "selected_location", {"lat": -1.1747, "lon": 100.4012, "name": "Indonesia (Default)"}
    )
    input_data["latitude"] = selected_loc.get("lat", -1.1747)
    input_data["longitude"] = selected_loc.get("lon", 100.4012)
    input_data["location_name"] = selected_loc.get("name", "lokasi ini")
    
    # ── Custom location input ─────────────────────────────────────────
    st.caption("Atau masukkan koordinat secara manual:")
    col_lat, col_lon = st.columns(2)
    with col_lat:
        custom_lat = st.number_input("Latitude", value=float(input_data["latitude"]), format="%.4f", key="custom_lat")
    with col_lon:
        custom_lon = st.number_input("Longitude", value=float(input_data["longitude"]), format="%.4f", key="custom_lon")
    
    if st.button("📍 Terapkan Koordinat", use_container_width=True, key="apply_coords"):
        st.session_state.selected_location = {
            "lat": custom_lat,
            "lon": custom_lon,
            "name": f"Custom: {custom_lat:.4f}°, {custom_lon:.4f}°",
        }
        st.rerun()
    
    # Re-read location after possible update
    selected_loc = st.session_state.get(
        "selected_location", {"lat": -1.1747, "lon": 100.4012, "name": "Indonesia (Default)"}
    )
    input_data["latitude"] = selected_loc.get("lat", -1.1747)
    input_data["longitude"] = selected_loc.get("lon", 100.4012)
    input_data["location_name"] = selected_loc.get("name", "lokasi ini")
    
    # ── Location display ─────────────────────────────────────────────
    st.caption(f"📍 Prediksi untuk: {input_data['location_name']} ({input_data['latitude']:.4f}, {input_data['longitude']:.4f})")
    
    st.markdown("---")
    
    # ── Preset Scenarios ───────────────────────────────────────────────
    st.markdown("### 🎯 Preset Skenario")
    col_p1, col_p2 = st.columns(2)
    col_p3, col_p4 = st.columns(2)
    
    with col_p1:
        if st.button("🔥 Kekeringan", use_container_width=True, help="Suhu tinggi, kelembaban rendah, tanpa hujan"):
            st.session_state.preset_applied = "drought"
            st.rerun()
    
    with col_p2:
        if st.button("🌧️ Badai", use_container_width=True, help="Hujan tinggi, kelembaban tinggi, angin kencang"):
            st.session_state.preset_applied = "storm"
            st.rerun()
    
    with col_p3:
        if st.button("💨 Angin Kencang", use_container_width=True, help="Angin sangat kencang, suhu sedang"):
            st.session_state.preset_applied = "windy"
            st.rerun()
    
    with col_p4:
        if st.button("🌿 Normal", use_container_width=True, help="Kondisi cuaca standar"):
            st.session_state.preset_applied = "normal"
            st.rerun()
    
    # Apply preset if selected
    if "preset_applied" in st.session_state:
        preset = st.session_state.preset_applied
        presets = {
            "drought": {
                "temperature": 42.0, "humidity": 20, "wind_speed": 8.0,
                "wind_direction": 180, "rainfall": 0.0, "fuel_moisture": 15,
            },
            "storm": {
                "temperature": 24.0, "humidity": 95, "wind_speed": 18.0,
                "wind_direction": 270, "rainfall": 150.0, "fuel_moisture": 75,
            },
            "windy": {
                "temperature": 30.0, "humidity": 50, "wind_speed": 25.0,
                "wind_direction": 90, "rainfall": 0.0, "fuel_moisture": 40,
            },
            "normal": {
                "temperature": 32.0, "humidity": 65, "wind_speed": 5.0,
                "wind_direction": 45, "rainfall": 5.0, "fuel_moisture": 45,
            },
        }
        if preset in presets:
            for key, value in presets[preset].items():
                st.session_state[f"preset_{key}"] = value
        del st.session_state.preset_applied
        st.success("✅ Preset diterapkan!")
    
    st.markdown("---")
    
    # ── Auto-fetch weather data ───────────────────────────────────────
    lat = input_data["latitude"]
    lon = input_data["longitude"]
    if lat is not None and lon is not None:
        loc_key = (round(lat, 4), round(lon, 4))
        last_loc = st.session_state.get("last_fetched_location")
        if loc_key != last_loc:
            location_name = input_data["location_name"]
            with st.spinner(f"Mengambil data cuaca untuk {location_name}..."):
                try:
                    weather = get_weather_data(lat, lon)
                    input_data["temperature"] = weather.get("temperature", 32.0)
                    input_data["humidity"] = weather.get("humidity", 50)
                    input_data["wind_speed"] = weather.get("wind_speed", 5.0)
                    input_data["wind_direction"] = weather.get("wind_direction", 0)
                    input_data["rainfall"] = weather.get("rainfall", 0.0)
                    st.session_state.preset_temperature = float(input_data["temperature"])
                    st.session_state.preset_humidity = int(input_data["humidity"])
                    st.session_state.preset_wind_speed = float(input_data["wind_speed"])
                    st.session_state.preset_wind_direction = int(input_data["wind_direction"])
                    st.session_state.preset_rainfall = float(input_data["rainfall"])
                    st.session_state.last_fetched_location = loc_key
                    st.success(f"✅ Data cuaca diambil dari {weather.get('source', 'API')}")
                except Exception as e:
                    st.warning(f"⚠️ Gagal mengambil data cuaca: {e}. Menggunakan nilai default.")
    
    # ── Auto-fetch GEE satellite data ──────────────────────────────────
    lat_g = input_data["latitude"]
    lon_g = input_data["longitude"]
    geo_key = (round(lat_g, 4), round(lon_g, 4))
    last_geo = st.session_state.get("last_fetched_gee")
    if geo_key != last_geo:
        location_name = input_data["location_name"]
        with st.spinner(f"Mengambil data satelit & elevasi untuk {location_name}..."):
            try:
                gee_data = get_location_data(lat_g, lon_g)
                input_data["elevation"] = gee_data.get("elevation", 100.0)
                st.session_state.preset_elevation = input_data["elevation"]
                for band in ["B2", "B3", "B4", "B8", "B11", "B12"]:
                    val = gee_data.get(band, 0.0)
                    input_data[band] = val
                    st.session_state[f"preset_{band}"] = val
                lc_code = gee_data.get("land_cover_code", 0)
                input_data["land_cover"] = lc_code
                st.session_state.preset_land_cover = lc_code
                if not st.session_state.get("ndvi_manually_set", False):
                    b8 = gee_data.get("B8", 0.0)
                    b4 = gee_data.get("B4", 0.0)
                    input_data["ndvi"] = (b8 - b4) / (b8 + b4 + 1e-8)
                    st.session_state.preset_ndvi = float(input_data["ndvi"])
                st.session_state.last_fetched_gee = geo_key
                # Audit Fase 2d: honestly report the data source. Previously
                # always showed "Data satelit (Google Earth Engine)" even when
                # get_location_data() returned the synthetic fallback
                # (GEE unreachable). The new "source" key disambiguates.
                gee_source = gee_data.get("source", "unknown")
                if gee_source == "Google Earth Engine":
                    st.success("✅ Data satelit & elevasi diambil (Google Earth Engine)")
                else:
                    st.warning(
                        f"⚠️ GEE tidak tersedia — menggunakan data sintetis "
                        f"(source={gee_source}). Nilai satelit/elevasi "
                        f"adalah placeholder; prediksi mungkin tidak akurat."
                    )
            except Exception as e:
                st.warning(f"⚠️ GEE gagal diambil: {e}. Menggunakan nilai default.")
                input_data.update({
                    "elevation": 100.0, "B2": 0.15, "B3": 0.25, "B4": 0.20,
                    "B8": 0.45, "B11": 0.30, "B12": 0.25, "land_cover": 10,
                })
    else:
        # Reuse cached values
        input_data["elevation"] = st.session_state.get("preset_elevation", 100.0)
        for band in ["B2", "B3", "B4", "B8", "B11", "B12"]:
            input_data[band] = st.session_state.get(f"preset_{band}", 0.0)
        input_data["land_cover"] = st.session_state.get("preset_land_cover", 0)
        if "preset_ndvi" in st.session_state:
            input_data["ndvi"] = st.session_state.preset_ndvi
    
    st.markdown("---")
    
    # ── Weather Conditions ────────────────────────────────────────────
    with st.expander("🌤️ Kondisi Cuaca", expanded=True):
        col_temp, col_humidity = st.columns(2)
        with col_temp:
            temperature = st.slider(
                "Suhu (°C)",
                min_value=15.0, max_value=50.0,
                value=_get_float("preset_temperature", 32.0),
                step=0.5, help="Suhu udara saat ini",
            )
            input_data["temperature"] = temperature
        
        with col_humidity:
            humidity = st.slider(
                "Kelembaban (%)",
                min_value=5, max_value=100,
                value=_get_int("preset_humidity", 45),
                step=1, help="Kelembaban udara relatif",
            )
            input_data["humidity"] = humidity
        
        col_ws, col_wd = st.columns(2)
        with col_ws:
            wind_speed = st.slider(
                "Kecepatan Angin (m/s)",
                min_value=0.0, max_value=30.0,
                value=_get_float("preset_wind_speed", 5.0),
                step=0.5, help="Kecepatan angin rata-rata",
            )
            input_data["wind_speed"] = wind_speed
        
        with col_wd:
            wind_direction = st.slider(
                "Arah Angin (°)",
                min_value=0, max_value=360,
                value=_get_int("preset_wind_direction", 45),
                step=5,
                help="0°=Utara, 90°=Timur, 180°=Selatan, 270°=Barat",
            )
            input_data["wind_direction"] = wind_direction
        
        rainfall = st.slider(
            "Curah Hujan 24 Jam (mm)",
            min_value=0.0, max_value=200.0,
            value=_get_float("preset_rainfall", 0.0),
            step=1.0, help="Total curah hujan 24 jam terakhir",
        )
        input_data["rainfall"] = rainfall
    
    st.markdown("---")
    
    # ── What-If Scenario ──────────────────────────────────────────────
    if st.checkbox("✏️ Ubah Manual (What-If Skenario)", key="manual_override"):
        st.markdown('<span class="sim-badge">SIMULASI</span> Sesuaikan parameter untuk simulasi:', unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            override_wind_speed = st.slider(
                "Simulasi Kecepatan Angin (m/s)",
                min_value=0.0, max_value=30.0,
                value=wind_speed, step=0.5, key="override_wind_speed",
            )
            input_data["override_wind_speed"] = override_wind_speed
        with col2:
            override_wind_direction = st.slider(
                "Simulasi Arah Angin (°)",
                min_value=0, max_value=360,
                value=wind_direction, step=5, key="override_wind_direction",
            )
            input_data["override_wind_direction"] = override_wind_direction
        input_data["is_what_if"] = True
    else:
        input_data["is_what_if"] = False
    
    st.markdown("---")
    
    # ── Vegetation / Fuel ─────────────────────────────────────────────
    with st.expander("🌳 Kondisi Bahan Bakar", expanded=True):
        veg_type = st.session_state.get("preset_vegetation_type", "Savana")
        vegetation_type = st.selectbox(
            "Tipe Vegetasi Dominan",
            list(VEGETATION_TYPES.keys()),
            index=list(VEGETATION_TYPES.keys()).index(veg_type) if veg_type in VEGETATION_TYPES else 0,
            help="Pilih tipe vegetasi di lokasi prediksi",
        )
        input_data["vegetation_type"] = vegetation_type
        st.session_state.preset_vegetation_type = vegetation_type
        
        veg_props = VEGETATION_TYPES[vegetation_type]
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.metric("Kadar Air Bahan Bakar", f"{veg_props['moisture_content']}%")
        with col_m2:
            st.metric("Indeks Ketercekamannya", f"{veg_props['flammability']:.2f}")
        
        # Auto-set NDVI default when vegetation changes
        last_veg = st.session_state.get("last_vegetation_type")
        if vegetation_type != last_veg:
            st.session_state.preset_ndvi = veg_props["ndvi_default"]
            st.session_state.ndvi_manually_set = False
            st.session_state.last_vegetation_type = vegetation_type
        
        ndvi = st.slider(
            "Indeks NDVI",
            min_value=0.0, max_value=1.0,
            value=_get_float("preset_ndvi", veg_props["ndvi_default"]),
            step=0.01,
            help="Indeks vegetasi (0-1). Berdasarkan tipe vegetasi, harga otomatis diisi.",
        )
        input_data["ndvi"] = ndvi
        st.session_state.preset_ndvi = float(ndvi)
        
        fuel_moisture = st.slider(
            "Kelembaban Bahan Bakar Manual (%)",
            min_value=0, max_value=100,
            value=_get_int("preset_fuel_moisture", veg_props["moisture_content"]),
            step=5, help="Sesuaikan kadar air bahan bakar (0-100%)",
        )
        input_data["fuel_moisture"] = fuel_moisture
    
    st.markdown("---")
    
    # ── Ignition Point ────────────────────────────────────────────────
    with st.expander("🔥 Sumber Kebakaran"):
        st.caption("Masukkan koordinat titik api awal secara manual di bawah.")
        current_data = st.session_state.get("selected_location", {"lat": -1.1747, "lon": 100.4012})
        ignition_lat = st.number_input(
            "Latitude Titik Api",
            value=current_data.get("lat", -1.1747), format="%.4f", key="ignition_lat",
        )
        ignition_lon = st.number_input(
            "Longitude Titik Api",
            value=current_data.get("lon", 100.4012), format="%.4f", key="ignition_lon",
        )
        input_data["ignition_point"] = {"latitude": ignition_lat, "longitude": ignition_lon}
    
    st.markdown("---")
    
    # ── Prediction Time Range ─────────────────────────────────────────
    with st.expander("⏰ Waktu Prediksi", expanded=True):
        prediction_hours = st.slider(
            "Prediksi untuk ... jam ke depan",
            min_value=1, max_value=72, value=12, step=1,
            help="Jangka waktu prediksi (1-72 jam)",
        )
        input_data["prediction_hours"] = prediction_hours
    
    return input_data
