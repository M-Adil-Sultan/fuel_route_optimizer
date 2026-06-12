"""Convenience wrapper for geocoding arbitrary user-provided location strings."""

import logging
import time
from .services.geocoder import _geocoder, rate_limit

logger = logging.getLogger(__name__)


def geocode_location(location: str) -> tuple[float, float] | None:
    """Geocode a free-form location string using Nominatim with retries."""
    query = f"{location}, USA" if not location.endswith('USA') else location
    for attempt in range(5):
        rate_limit()
        try:
            result = _geocoder.geocode(query, timeout=15)
            if result:
                return result.latitude, result.longitude
        except Exception as e:
            if 'RateLimited' in type(e).__name__:
                logger.warning("Nominatim rate limited, waiting 60s...")
                time.sleep(60)
            else:
                logger.debug("Geocoder error on attempt %d: %s", attempt + 1, e)
                time.sleep(3)
    return None
