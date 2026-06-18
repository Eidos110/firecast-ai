"""
Google Earth Engine Integration for FireCast
Fetch elevation, Sentinel-2 bands, and land cover data.
"""

import os
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import ee
import streamlit as st

# Get logger
logger = logging.getLogger(__name__)

# ── GEE Authentication ────────────────────────────────────────────────────────

# Service account credentials
SERVICE_ACCOUNT = "popaye@firecast-001.iam.gserviceaccount.com"
KEY_FILE = Path(__file__).parent.parent.parent / "add_new_model" / "firecast-001-db06a187f9f4.json"

# Initialize GEE on module import (one-time)
try:
    if not KEY_FILE.exists():
        logger.warning(f"GEE key file not found: {KEY_FILE}")
        _gee_initialized = False
    else:
        credentials = ee.ServiceAccountCredentials(SERVICE_ACCOUNT, str(KEY_FILE))
        # Check if EE already initialized to avoid "Earth Engine has already been initialized" error
        try:
            ee.Initialize(credentials)
            _gee_initialized = True
            logger.info("Google Earth Engine initialized successfully")
        except Exception as init_err:
            # If already initialized with different credentials, that's okay
            if "already been initialized" in str(init_err).lower():
                logger.info("Google Earth Engine already initialized, using existing session")
                _gee_initialized = True
            else:
                raise init_err
except Exception as e:
    logger.error(f"Failed to initialize Earth Engine: {e}")
    _gee_initialized = False


# ── Dynamic World → Model Land Cover Mapping ──────────────────────────────────

# Dynamic World class labels (order matters: index = class ID 0-8)
DYNAMIC_WORLD_CLASSES = [
    "water",      # 0
    "trees",      # 1
    "grass",      # 2
    "flooded_vegetation",  # 3
    "crops",      # 4
    "shrub",      # 5
    "built",      # 6
    "bare",       # 7
    "snow_and_ice",  # 8
]

# Map Dynamic World index → FireCast land cover code
DYNAMIC_WORLD_TO_FIRECAST = {
    0: 0,    # water → 0 (water)
    1: 10,   # trees → 10 (forest)
    5: 20,   # shrub → 20 (shrubland)
    2: 40,   # grass → 40 (grassland)
    4: 50,   # crops → 50 (cropland)
    6: 70,   # built → 70 (built-up)
    7: 60,   # bare → 60 (barren)
    # flooded_vegetation → map to nearest (crops?); use 50
    3: 50,
    # snow_and_ice → barren
    8: 60,
}


def _map_dynamic_world_to_code(dw_class: Optional[int]) -> int:
    """Map Dynamic World class index to FireCast land cover code."""
    if dw_class is None:
        return 0
    return DYNAMIC_WORLD_TO_FIRECAST.get(dw_class, 0)


# ── Cloud Masking for Sentinel-2 ───────────────────────────────────────────────

def _mask_s2_clouds(image: ee.Image) -> ee.Image:
    """
    Mask Sentinel-2 Level-2A (Surface Reflectance) clouds using SCL band.
    
    SCL (Scene Classification Layer) values:
    - 0: no_data
    - 1: saturated/defective
    - 2: dark area
    - 3: cloud shadow
    - 4: vegetation
    - 5: not vegetated
    - 6: water
    - 7: unclassified
    - 8: cloud medium probability
    - 9: cloud high probability
    - 10: thin cirrus
    - 11: snow/ice
    
    We mask out: cloud shadows (3), medium/high clouds (8,9), cirrus (10)
    """
    # Use SCL band for cloud masking (Level-2A)
    try:
        scl = image.select("SCL")
        # Mask: 3=cloud_shadow, 8=cloud_medium, 9=cloud_high, 10=cirrus
        cloud_mask = scl.eq(3).Or(scl.eq(8)).Or(scl.eq(9)).Or(scl.eq(10))
        # Update mask: keep pixels where cloud_mask is False
        image_masked = image.updateMask(cloud_mask.Not())
    except Exception:
        # SCL not available, try QA60 (older Level-1C)
        try:
            qa = image.select("QA60")
            cloud_bit_mask = 1 << 10
            cirrus_bit_mask = 1 << 11
            mask = qa.bitwiseAnd(cloud_bit_mask).eq(0) \
                   .And(qa.bitwiseAnd(cirrus_bit_mask).eq(0))
            image_masked = image.updateMask(mask)
        except Exception:
            # Fallback: use cloud probability mask
            try:
                msk = image.select("MSK_CLASSI_OPAQUE")
                mask = msk.eq(0)
                image_masked = image.updateMask(mask)
            except Exception:
                # No cloud mask available, use image as-is
                image_masked = image
    
    # Scale to 0-1 reflectance (Level-2A uses 0-10000 scale)
    return image_masked.divide(10000)


# ── Main Data Fetch Function ───────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)  # 24 hours cache
def get_location_data(lat: float, lon: float) -> Dict[str, Any]:
    """
    Fetch elevation, Sentinel-2 bands, and land cover for a location.

    Args:
        lat: Latitude
        lon: Longitude

    Returns:
        Dictionary with keys:
            - elevation: float (meters)
            - B2, B3, B4, B8, B11, B12: float (reflectance 0-1)
            - land_cover_class: int (Dynamic World class index 0-8)
            - land_cover_code: int (FireCast code: 0,10,20,30,40,50,60,70)
    """
    if not _gee_initialized:
        logger.warning("GEE not initialized, returning synthetic fallback")
        return _get_synthetic_fallback()

    point = ee.Geometry.Point([lon, lat])

    try:
        # 1── Elevation from SRTM ───────────────────────────────────────────────
        srtm = ee.Image("USGS/SRTMGL1_003")
        elev_value = srtm.select("elevation") \
            .reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=point,
                scale=30,
                maxPixels=1e9
            )
        elevation = elev_value.get("elevation")
        elevation = elevation.getInfo() if elevation is not None else None

        # 2── Sentinel-2 Surface Reflectance (most recent cloud-free) ───────────
        s2_collection = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
            .filterBounds(point) \
            .filterDate(
                ee.Date(datetime.now()).advance(-30, 'day'),
                ee.Date(datetime.now())
            ) \
            .map(_mask_s2_clouds)

        # Get the least cloudy image
        s2_image = s2_collection.sort('CLOUDY_PIXEL_PERCENTAGE', False).first()
        if s2_image is None:
            raise ValueError("No cloud-free Sentinel-2 image found in last 30 days")

        # Sample bands at point
        bands_to_sample = ["B2", "B3", "B4", "B8", "B11", "B12"]
        band_values = s2_image.select(bands_to_sample) \
            .reduceRegion(
                reducer=ee.Reducer.mean(),
                geometry=point.buffer(100),  # 100m buffer to avoid edges
                scale=10,
                maxPixels=1e9
            ).getInfo()

        # Extract band values (already scaled 0-1 by _mask_s2_clouds)
        band_data = {}
        for band in bands_to_sample:
            val = band_values.get(band)
            band_data[band] = float(val) if val is not None else 0.0

        # 3── Land Cover from Dynamic World (most recent) ────────────────────────
        dw_collection = ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1") \
            .filterBounds(point) \
            .filterDate(
                ee.Date(datetime.now()).advance(-90, 'day'),
                ee.Date(datetime.now())
            )

        dw_image = dw_collection.sort('system:time_start', False).first()
        if dw_image is None:
            raise ValueError("No Dynamic World land cover image found in last 90 days")

        dw_class = dw_image.select("label") \
            .reduceRegion(
                reducer=ee.Reducer.mode(),
                geometry=point,
                scale=10,
                maxPixels=1e9
            )
        dw_class_val = dw_class.get("label")
        dw_class_int = dw_class_val.getInfo() if dw_class_val is not None else None

        land_cover_class = dw_class_int if dw_class_int is not None else 0
        land_cover_code = _map_dynamic_world_to_code(land_cover_class)

        # Compose result
        result = {
            "elevation": float(elevation) if elevation is not None else 100.0,
            "B2": band_data.get("B2", 0.0),
            "B3": band_data.get("B3", 0.0),
            "B4": band_data.get("B4", 0.0),
            "B8": band_data.get("B8", 0.0),
            "B11": band_data.get("B11", 0.0),
            "B12": band_data.get("B12", 0.0),
            "land_cover_class": land_cover_class,
            "land_cover_code": land_cover_code,
        }

        logger.info(f"GEE data fetched for {lat:.4f},{lon:.4f}: "
                    f"elev={result['elevation']:.1f}m, "
                    f"NDVI={(result['B8']-result['B4'])/(result['B8']+result['B4']+1e-8):.3f}, "
                    f"land_cover={land_cover_code}")
        return result

    except Exception as e:
        logger.error(f"GEE fetch failed: {e}", exc_info=True)
        st.warning(f"GEE data unavailable: {e}. Menggunakan nilai default.")
        return _get_synthetic_fallback()


def _get_synthetic_fallback() -> Dict[str, Any]:
    """Return synthetic fallback values if GEE fails."""
    return {
        "elevation": 100.0,
        "B2": 0.15,
        "B3": 0.25,
        "B4": 0.20,
        "B8": 0.45,
        "B11": 0.30,
        "B12": 0.25,
        "land_cover_class": 1,
        "land_cover_code": 10,
    }
