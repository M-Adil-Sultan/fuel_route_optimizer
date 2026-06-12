"""Nominatim geocoding service with caching, rate-limiting, and state-centroid fallback."""

import json
import logging
import time
from pathlib import Path
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderUnavailable, GeocoderRateLimited

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CACHE_FILE = BASE_DIR / 'data' / 'geocoded_cache.json'

_geocoder = Nominatim(user_agent="fuel_route_optimizer")
_cache: dict[str, list[float] | None] = {}
_last_request_time = 0.0
REQUEST_INTERVAL = 1.2
_geo_count = 0
_api_available = False

STATE_CENTROIDS: dict[str, tuple[float, float]] = {
    "AL": (32.806671, -86.791130),
    "AK": (64.200841, -149.493673),
    "AZ": (34.212177, -111.681343),
    "AR": (34.969704, -92.373123),
    "CA": (36.116203, -119.681564),
    "CO": (39.059811, -105.311104),
    "CT": (41.597782, -72.755371),
    "DE": (39.318523, -75.507141),
    "FL": (27.766279, -81.686783),
    "GA": (32.165623, -82.900075),
    "HI": (21.094318, -157.498337),
    "ID": (44.240459, -114.478828),
    "IL": (40.000664, -89.156844),
    "IN": (39.849426, -86.258278),
    "IA": (42.011539, -93.210526),
    "KS": (38.526600, -98.379633),
    "KY": (37.668140, -85.903921),
    "LA": (31.169546, -91.867805),
    "ME": (44.693947, -69.381921),
    "MD": (39.063946, -76.802101),
    "MA": (42.230171, -71.530106),
    "MI": (43.326618, -84.536095),
    "MN": (45.694454, -93.900192),
    "MS": (32.741646, -89.678696),
    "MO": (38.456085, -92.288368),
    "MT": (47.052952, -109.634986),
    "NE": (41.125370, -100.446516),
    "NV": (39.163780, -116.753833),
    "NH": (43.452492, -71.563896),
    "NJ": (40.298904, -74.521011),
    "NM": (34.840010, -106.248482),
    "NY": (42.165726, -74.948051),
    "NC": (35.630066, -79.806419),
    "ND": (47.528912, -101.002197),
    "OH": (40.388783, -82.764915),
    "OK": (35.565342, -96.928917),
    "OR": (44.572021, -122.070938),
    "PA": (41.203322, -77.194524),
    "RI": (41.680893, -71.511780),
    "SC": (33.856892, -80.945007),
    "SD": (44.299782, -100.227689),
    "TN": (35.747845, -86.692345),
    "TX": (31.054859, -100.504705),
    "UT": (39.162886, -111.648862),
    "VT": (44.040716, -72.710686),
    "VA": (37.769337, -78.169968),
    "WA": (47.400902, -121.490494),
    "WV": (38.491224, -80.954455),
    "WI": (44.268543, -89.616508),
    "WY": (42.756043, -107.302490),
    "DC": (38.897438, -77.026817),
    "AB": (53.933270, -116.576503),
    "BC": (53.726669, -127.647620),
    "MB": (53.760863, -98.813876),
    "NB": (46.565319, -66.461916),
    "NS": (44.681985, -63.744327),
    "ON": (51.253775, -85.323214),
    "QC": (52.939915, -73.549136),
    "SK": (52.939915, -106.450864),
    "YT": (64.245186, -135.003598),
}


def _load_cache() -> None:
    if CACHE_FILE.exists():
        with open(CACHE_FILE, 'r') as f:
            _cache.update(json.load(f))


def _save_cache() -> None:
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump(_cache, f)


def rate_limit() -> None:
    """Enforce a minimum interval between Nominatim API requests."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < REQUEST_INTERVAL:
        time.sleep(REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def geocode_city_state(city: str, state: str) -> tuple[float, float] | None:
    """Geocode a city/state pair using cache, Nominatim API, or state centroid fallback."""
    global _geo_count, _api_available

    key = f"{city},{state}"
    if key in _cache:
        cached = _cache[key]
        return tuple(cached) if cached is not None else None

    if _api_available:
        query = f"{city}, {state}, USA"
        for attempt in range(2):
            rate_limit()
            try:
                location = _geocoder.geocode(query, timeout=10)
                if location:
                    coords = [location.latitude, location.longitude]
                    _cache[key] = coords
                    _geo_count += 1
                    if _geo_count % 50 == 0:
                        _save_cache()
                        logger.info("Geocoded %d locations...", _geo_count)
                    return tuple(coords)
            except GeocoderRateLimited:
                _api_available = False
                logger.warning("Nominatim rate limited, switching to state centroids.")
                break
            except (GeocoderTimedOut, GeocoderUnavailable):
                logger.debug("Geocoder timeout/unavailable, retrying...")
                time.sleep(2)

    if state in STATE_CENTROIDS:
        coords = list(STATE_CENTROIDS[state])
        _cache[key] = coords
        if len(_cache) % 500 == 0:
            _save_cache()
        return tuple(coords)

    _cache[key] = None
    return None


def init_geocoder() -> None:
    """Load the geocoding cache from disk."""
    _load_cache()
    logger.info("Loaded geocoder cache with %d cached locations", len(_cache))
