"""
FireCast Weather API Integration
================================
Handles fetching real-time weather data from multiple sources.
"""

import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path

import requests
import streamlit as st

# Try to load environment variables from .env file
try:
    from dotenv import load_dotenv

    # Look for .env in current directory, parent, or project root
    possible_paths = [
        Path(".") / ".env",
        Path("..") / ".env",
        Path(__file__).parent.parent.parent / ".env",
    ]
    for env_path in possible_paths:
        if env_path.exists():
            load_dotenv(env_path)
            break
except ImportError:
    pass  # python-dotenv not installed

# Get logger
logger = logging.getLogger(__name__)

# API Configuration from environment
OPENWEATHER_API_KEY = os.getenv("OPENWEATHER_API_KEY", "").strip()
OPENWEATHER_API_URL = "https://api.openweathermap.org/data/2.5"
BMKG_API_URL = "https://api.bmkg.go.id/publik"


@st.cache_data(ttl=600, show_spinner=False)
def get_weather_data(lat: float, lon: float, source: str = "auto") -> Dict[str, Any]:
    """
    Get real-time weather data from API (cached for 10 minutes).

    Args:
        lat: Latitude coordinate
        lon: Longitude coordinate
        source: Weather API source ('openweather', 'bmkg', 'auto', or 'demo')

    Returns:
        Dictionary with weather data
    """
    return _fetch_weather_data(lat, lon, source)


def _fetch_weather_data(lat: float, lon: float, source: str = "auto") -> Dict[str, Any]:
    """Internal weather fetch logic (not cached, called by cached wrapper)."""
    # Validate coordinates
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        logger.warning(f"Invalid coordinates: lat={lat}, lon={lon}. Using demo data.")
        return _get_demo_weather_data(lat, lon)

    # Auto-detect which API to use
    if source == "auto":
        # Try OpenWeatherMap first if API key is configured
        if OPENWEATHER_API_KEY and OPENWEATHER_API_KEY not in [
            "demo_key",
            "",
            "your_api_key_here",
            "your_openweather_api_key_here",
        ]:
            try:
                logger.info(f"Trying OpenWeatherMap API for lat={lat}, lon={lon}")
                return _get_openweather_data(lat, lon)
            except Exception as e:
                logger.warning(f"OpenWeatherMap failed: {e}, trying BMKG...")

        # Try BMKG next
        try:
            logger.info(f"Trying BMKG API for lat={lat}, lon={lon}")
            return _get_bmkg_data(lat, lon)
        except Exception as e:
            logger.warning(f"BMKG failed: {e}, using demo data...")

    # Try specific source
    try:
        if source == "openweather":
            return _get_openweather_data(lat, lon)
        elif source == "bmkg":
            return _get_bmkg_data(lat, lon)
    except Exception as e:
        logger.error(f"Error fetching from {source}: {e}, falling back to demo data")

    # Fallback to demo data
    logger.info("Using demo weather data")
    return _get_demo_weather_data(lat, lon)


def _get_openweather_data(lat: float, lon: float) -> Dict[str, Any]:
    """Fetch weather data from OpenWeatherMap API."""

    # Check if API key is valid
    if not OPENWEATHER_API_KEY or OPENWEATHER_API_KEY in [
        "demo_key",
        "",
        "your_api_key_here",
        "your_openweather_api_key_here",
    ]:
        logger.warning("OpenWeatherMap API key not configured or is placeholder")
        raise ValueError("OpenWeatherMap API key not configured")

    # Current weather
    current_url = f"{OPENWEATHER_API_URL}/weather"
    forecast_url = f"{OPENWEATHER_API_URL}/forecast"

    params = {"lat": lat, "lon": lon, "appid": OPENWEATHER_API_KEY, "units": "metric"}

    try:
        # Fetch current weather
        logger.debug(f"GET {current_url} params={params}")
        current_response = requests.get(current_url, params=params, timeout=10)
        
        # Handle specific HTTP errors
        if current_response.status_code == 401:
            logger.error("OpenWeatherMap API key is invalid (401 Unauthorized)")
            raise ValueError("Invalid OpenWeatherMap API key. Please check your API key.")
        elif current_response.status_code == 429:
            logger.error("OpenWeatherMap rate limit exceeded (429 Too Many Requests)")
            raise ValueError("OpenWeatherMap rate limit exceeded. Try again later.")
        elif current_response.status_code != 200:
            logger.error(f"OpenWeatherMap current weather error: {current_response.status_code} {current_response.text[:200]}")
            raise ValueError(f"OpenWeatherMap API error: HTTP {current_response.status_code}")
        
        current_data = current_response.json()

        # Check if response has expected structure
        if "main" not in current_data or "wind" not in current_data:
            logger.error(f"OpenWeatherMap unexpected response structure: {list(current_data.keys())}")
            raise ValueError(f"Invalid API response structure: {list(current_data.keys())}")

        # Fetch forecast
        logger.debug(f"GET {forecast_url} params={params}")
        forecast_response = requests.get(forecast_url, params=params, timeout=10)
        
        if forecast_response.status_code == 401:
            logger.error("OpenWeatherMap API key is invalid (401) on forecast endpoint")
            raise ValueError("Invalid OpenWeatherMap API key.")
        elif forecast_response.status_code == 429:
            logger.error("OpenWeatherMap rate limit exceeded (429) on forecast endpoint")
            raise ValueError("OpenWeatherMap rate limit exceeded.")
        elif forecast_response.status_code != 200:
            logger.error(f"OpenWeatherMap forecast error: {forecast_response.status_code}")
            # Continue with just current weather if forecast fails
            forecast_data = {"list": []}
        else:
            forecast_data = forecast_response.json()

        return {
            "temperature": current_data["main"]["temp"],
            "humidity": current_data["main"]["humidity"],
            "wind_speed": current_data["wind"].get("speed", 0),
            "wind_direction": current_data["wind"].get("deg", 0),
            "rainfall": current_data.get("rain", {}).get("1h", 0)
            or current_data.get("rain", {}).get("3h", 0) / 3
            if "rain" in current_data
            else 0,
            "pressure": current_data["main"].get("pressure", 1013),
            "feels_like": current_data["main"].get("feels_like", current_data["main"]["temp"]),
            "description": current_data["weather"][0].get("description", "Unknown")
            if "weather" in current_data and len(current_data["weather"]) > 0
            else "Unknown",
            "forecast": _parse_openweather_forecast(forecast_data),
            "source": "OpenWeatherMap",
            "timestamp": datetime.now().isoformat(),
            "is_demo": False,
        }

    except requests.exceptions.Timeout:
        logger.error("OpenWeatherMap request timeout")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"OpenWeatherMap request error: {e}")
        raise
    except (KeyError, IndexError, ValueError, TypeError) as e:
        logger.error(f"OpenWeatherMap data parsing error: {e}")
        raise ValueError(f"Failed to parse OpenWeatherMap response: {e}")


def _get_bmkg_data(lat: float, lon: float) -> Dict[str, Any]:
    """
    Fetch weather data from BMKG API (Indonesian Meteorological Agency).
    Note: BMKG API has limited coverage, mainly for Indonesia.
    """
    try:
        # BMKG public API endpoint
        url = f"{BMKG_API_URL}/prakiraan-cuaca"

        params = {"lat": lat, "lon": lon}

        response = requests.get(url, params=params, timeout=10)

        # BMKG API may return different response codes
        if response.status_code == 200:
            data = response.json()

            return {
                "temperature": data.get("temperature", 30),
                "humidity": data.get("humidity", 70),
                "wind_speed": data.get("wind_speed", 3),
                "wind_direction": data.get("wind_direction", 0),
                "rainfall": data.get("rainfall", 0),
                "pressure": data.get("pressure", 1013),
                "description": data.get("weather_desc", "Clear"),
                "forecast": [],  # BMKG forecast format may vary
                "source": "BMKG",
                "timestamp": datetime.now().isoformat(),
                "is_demo": False,
            }
        else:
            raise ValueError(f"BMKG API returned status {response.status_code}")

    except Exception as e:
        logger.error(f"BMKG API error: {e}")
        raise


def _get_demo_weather_data(lat: float, lon: float) -> Dict[str, Any]:
    """
    Generate demo weather data based on location and time.
    This is used when real APIs are unavailable.
    """
    logger.info(f"Generating demo weather data for lat={lat}, lon={lon}")

    # Base values
    hour = datetime.now().hour

    # Temperature varies by time of day and latitude
    base_temp = 30 - abs(lat) / 10  # Cooler at higher latitudes
    if 6 <= hour <= 18:  # Daytime
        temp = base_temp + 5 + (hour - 12) ** 2 / 20
    else:  # Nighttime
        temp = base_temp - 3

    # Generate forecast
    forecast = []
    current_time = datetime.now()
    for i in range(24):
        forecast_hour = (hour + i) % 24
        if 6 <= forecast_hour <= 18:
            forecast_temp = base_temp + 5
        else:
            forecast_temp = base_temp - 2

        forecast.append(
            {
                "time": (current_time + timedelta(hours=i)).isoformat(),
                "temperature": forecast_temp + (i % 3 - 1),
                "humidity": 65 + (i % 10),
                "wind_speed": 3 + (i % 5),
                "rainfall": 0 if forecast_hour > 8 else 0.5,
            }
        )

    return {
        "temperature": round(temp, 1),
        "humidity": 65,
        "wind_speed": 4.5,
        "wind_direction": 90,
        "rainfall": 0,
        "pressure": 1013,
        "feels_like": round(temp + 2, 1),
        "description": "Partly cloudy (Demo Data)",
        "forecast": forecast,
        "source": "DEMO",
        "timestamp": datetime.now().isoformat(),
        "is_demo": True,
    }


def _parse_openweather_forecast(forecast_data: Dict) -> list:
    """Parse OpenWeatherMap forecast data."""
    forecast = []

    if "list" not in forecast_data:
        return forecast

    for item in forecast_data["list"][:24]:  # Next 24 periods (3-hour intervals)
        try:
            forecast.append(
                {
                    "time": item["dt_txt"],
                    "temperature": item["main"]["temp"],
                    "humidity": item["main"]["humidity"],
                    "wind_speed": item["wind"]["speed"],
                    "rainfall": item.get("rain", {}).get("3h", 0),
                    "description": item["weather"][0]["description"]
                    if "weather" in item
                    else "Unknown",
                }
            )
        except (KeyError, IndexError) as e:
            logger.warning(f"Error parsing forecast item: {e}")
            continue

    return forecast


def is_demo_mode(weather_data: Dict[str, Any]) -> bool:
    """Check if weather data is from demo mode."""
    return weather_data.get("is_demo", False) or weather_data.get("source") == "DEMO"


@st.cache_data(ttl=3600, show_spinner=False)
def get_weather_status() -> Dict[str, Any]:
    """Get current weather API configuration status (cached for 1 hour)."""
    return {
        "openweather_configured": bool(
            OPENWEATHER_API_KEY
            and OPENWEATHER_API_KEY
            not in ["demo_key", "", "your_openweather_api_key_here"]
        ),
        "bmkg_available": True,  # Always try BMKG
        "demo_fallback": True,
    }


if __name__ == "__main__":
    # Test the weather API
    logging.basicConfig(level=logging.INFO)

    print("Weather API Status:", get_weather_status())

    # Test with Jakarta coordinates
    result = get_weather_data(-6.2, 106.8)
    print(f"\nWeather data for Jakarta:")
    print(f"  Temperature: {result['temperature']}°C")
    print(f"  Humidity: {result['humidity']}%")
    print(f"  Wind: {result['wind_speed']} m/s")
    print(f"  Source: {result['source']}")
    print(f"  Is Demo: {result['is_demo']}")
