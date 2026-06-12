"""OSRM-based routing service for driving directions."""

import logging
import polyline
import requests

logger = logging.getLogger(__name__)

OSRM_BASE_URL = "http://router.project-osrm.org"


def get_route(start_lat: float, start_lon: float, dest_lat: float, dest_lon: float) -> dict:
    """Fetch a driving route from OSRM and return distance, duration, and coordinates."""
    url = f"{OSRM_BASE_URL}/route/v1/driving/{start_lon},{start_lat};{dest_lon},{dest_lat}"
    params = {
        'overview': 'full',
        'geometries': 'polyline',
        'steps': 'false',
    }

    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if data.get('code') != 'Ok' or not data.get('routes'):
        raise ValueError("OSRM failed to find a route")

    route = data['routes'][0]
    distance_miles = route['distance'] * 0.000621371
    coordinates = polyline.decode(route['geometry'])

    return {
        'distance_miles': round(distance_miles, 1),
        'duration_seconds': route['duration'],
        'coordinates': coordinates,
    }
