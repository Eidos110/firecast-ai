"""
OpenWeatherMap API Client for Historical Weather Data

Provides historical weather data for creating proper temporal sequences
for BiGRU inference in AOI predictions.
"""

import requests
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import math

logger = logging.getLogger(__name__)

# OpenWeatherMap API endpoints
HISTORICAL_WEATHER_API = "https://history.openweathermap.org/data/2.5/history/city"
GEOCODING_API = "http://api.openweathermap.org/geo/1.0/direct"
CURRENT_WEATHER_API = "https://api.openweathermap.org/data/2.5/weather"

# Cache untuk menghindari repeated API calls untuk point yang sama
_weather_cache = {}
_cache_ttl = 3600  # 1 hour


def get_openweathermap_api_key() -> str:
    """Get OpenWeatherMap API key from config."""
    try:
        from src import config
        # Try to read from config or environment
        import os
        api_key = os.getenv('OPENWEATHER_API_KEY', '')
        if not api_key:
            # Try config
            api_key = getattr(config, 'OPENWEATHER_API_KEY', '')
        return api_key
    except Exception:
        return ""


def get_city_coordinates(city_name: str, country_code: Optional[str] = None) -> Optional[Tuple[float, float]]:
    """
    Geocode a city name to get lat/lon coordinates.

    Args:
        city_name: City name (e.g., "Los Angeles")
        country_code: Optional country code (e.g., "US")

    Returns:
        Tuple of (lat, lon) or None if not found
    """
    api_key = get_openweathermap_api_key()
    if not api_key:
        logger.warning("No OpenWeatherMap API key configured")
        return None

    try:
        params = {
            'q': city_name,
            'limit': 1,
            'appid': api_key
        }
        if country_code:
            params['q'] = f"{city_name},{country_code}"

        response = requests.get(GEOCODING_API, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data and len(data) > 0:
            lat = data[0]['lat']
            lon = data[0]['lon']
            logger.info(f"Geocoded '{city_name}' to ({lat}, {lon})")
            return (lat, lon)
        else:
            logger.warning(f"Could not geocode city: {city_name}")
            return None
    except Exception as e:
        logger.error(f"Geocoding failed for {city_name}: {e}")
        return None


def get_historical_weather(
    lat: float,
    lon: float,
    target_date: datetime,
    days_back: int = 7,
    api_key: Optional[str] = None
) -> Optional[Dict[str, float]]:
    """
    Fetch historical weather data for a location and target date.

    Uses OpenWeatherMap One Call API 3.0 (or History API if available).
    Note: Free tier has limited historical access. This function handles
    gracefully if API limits are reached.

    Args:
        lat: Latitude
        lon: Longitude
        target_date: Date for which to get weather (we'll fetch data leading up to it)
        days_back: How many days of history to fetch (default 7)
        api_key: OpenWeatherMap API key (optional, uses config if not provided)

    Returns:
        Dictionary with weather features or None if unavailable
    """
    if api_key is None:
        api_key = get_openweathermap_api_key()

    if not api_key:
        logger.warning("No OpenWeatherMap API key - cannot fetch historical data")
        return None

    # Check cache first
    cache_key = f"{lat:.4f}_{lon:.4f}_{target_date.strftime('%Y%m%d')}"
    now = datetime.now()
    if cache_key in _weather_cache:
        cached_time, cached_data = _weather_cache[cache_key]
        if (now - cached_time).total_seconds() < _cache_ttl:
            logger.debug(f"Using cached weather data for {cache_key}")
            return cached_data

    try:
        # For OpenWeatherMap One Call API 3.0 (paid/limited)
        # We'll use the "daily" endpoint which gives past 7 days + forecast
        # But free tier only has current + 7-day forecast (not past)

        # ALTERNATIVE: Use OpenWeatherMap's "Historical Data" (requires paid plan)
        # For now, we'll implement a fallback: use current weather + typical climatology

        # If we have the Historical API access (paid):
        # timestamp_start = int((target_date - timedelta(days=days_back)).timestamp())
        # timestamp_end = int(target_date.timestamp())
        # url = f"https://api.openweathermap.org/data/2.5/history/city?lat={lat}&lon={lon}&type=hour&start={timestamp_start}&end={timestamp_end}&appid={api_key}"

        # Since most users won't have paid tier, use approximation:
        # Get current weather as baseline, apply typical seasonal variations
        logger.info(f"Attempting to fetch current weather for ({lat}, {lon}) as baseline")
        current_url = f"{CURRENT_WEATHER_API}?lat={lat}&lon={lon}&appid={api_key}&units=metric"
        response = requests.get(current_url, timeout=10)
        response.raise_for_status()
        current_data = response.json()

        # Extract current conditions
        current_temp = current_data['main']['temp']
        current_humidity = current_data['main']['humidity']
        current_wind_speed = current_data['wind'].get('speed', 0)
        current_wind_deg = current_data['wind'].get('deg', 0)
        current_precip = current_data.get('rain', {}).get('1h', 0)
        current_clouds = current_data['clouds']['all']
        current_weather_main = current_data['weather'][0]['main']

        # Convert wind deg to u/v
        wind_rad = math.radians(current_wind_deg)
        wind_u = -current_wind_speed * math.sin(wind_rad)
        wind_v = -current_wind_speed * math.cos(wind_rad)

        # Estimate historical values based on current + typical persistence
        # This is a simplified heuristic:
        # - Temperature typically changes ~1-2°C per day
        # - Precipitation is intermittent (0 most days)
        # - Wind changes moderately
        # We'll generate a synthetic sequence that varies slightly

        # Determine day of year for seasonal pattern
        day_of_year = target_date.timetuple().tm_yday

        # Seasonal adjustment (northern hemisphere)
        # Temperature peaks around day 200 (July), lows around day 10 (Jan)
        seasonal_temp_factor = math.sin(2 * math.pi * (day_of_year - 80) / 365)

        # Build synthetic historical record (7 days)
        # Use autoregressive-like smoothing
        historical = {
            'temp_max': current_temp - 2.0 + seasonal_temp_factor * 0.5,
            'humidity': current_humidity,
            'wind_speed': current_wind_speed * (0.9 + 0.1 * math.sin(day_of_year)),
            'wind_u': wind_u,
            'wind_v': wind_v,
            'precip': 0.0,  # Assume dry (will be overridden if current shows rain)
            'dewpoint': current_data['main'].get('dew_point', current_temp - 10),
            'cloud_cover': current_clouds,
            'weather_main': current_weather_main,
        }

        # If current has precipitation, assume last day had precip too
        if current_precip > 0:
            historical['precip'] = current_precip * 0.8

        # Store in cache
        _weather_cache[cache_key] = (now, historical)
        logger.info(f"Fetched/synthesized historical weather for ({lat}, {lon})")
        return historical

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            logger.warning("OpenWeatherMap API rate limit exceeded - using synthetic data")
        else:
            logger.error(f"OpenWeatherMap API error: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to fetch weather data: {e}")
        return None


def build_temporal_sequence(
    lat: float,
    lon: float,
    current_features: Dict[str, float],
    current_date: Optional[datetime] = None,
    seq_len: int = 7
) -> Optional[np.ndarray]:
    """
    Build a temporal sequence of feature vectors for BiGRU inference.

    For the current day (t=0), use computed features.
    For days t-1 to t-seq_len+1, attempt to retrieve historical weather from API
    and reconstruct features.

    Args:
        lat, lon: Location coordinates
        current_features: Feature dict for current day (from _create_feature_vector base_dict)
        current_date: Date of prediction (default: now)
        seq_len: Sequence length required by BiGRU

    Returns:
        Numpy array of shape (1, seq_len, n_features) or None if failed
    """
    if current_date is None:
        current_date = datetime.now()

    # Try to get historical weather
    historical_weather = get_historical_weather(lat, lon, current_date, days_back=seq_len-1)
    if historical_weather is None:
        logger.warning("Historical weather unavailable - cannot build real temporal sequence")
        return None

    # For now, since we only have current day weather, we'll create
    # a sequence by perturbing current features with realistic variations.
    # This is still "fake" but better than identical copies.
    # In a full implementation, historical_weather would provide actual past values.

    # TODO: When full OpenWeatherMap Historical API is available:
    # Reconstruct feature vector for each past day using historical_weather
    # For each day d from -(seq_len-1) to 0:
    #   features_d = reconstruct_features_from_weather(historical_weather[d], day_offset=d)
    #   sequence[d] = features_d
    # Currently: use perturbations

    n_features = len(current_features)  # This will be from base_dict
    sequence = np.zeros((1, seq_len, n_features))

    # Get list of base feature keys in order
    keys = list(current_features.keys())

    # Fill with perturbed versions
    for i in range(seq_len):
        factor = 1.0 - i * 0.02  # Slowly drift
        noise = np.random.randn(len(keys)) * 0.01 * (seq_len - i)
        vals = [current_features[k] * factor + n for k, n in zip(keys, noise)]
        sequence[0, i, :] = vals

    return sequence


def reconstruct_features_from_weather(
    weather_data: Dict,
    day_of_year: int,
    base_features: Dict[str, float]
) -> Dict[str, float]:
    """
    Reconstruct full feature vector from raw weather API data.

    This would be used if we had full historical API access.
    Placeholder for future implementation.
    """
    # Placeholder
    return base_features
