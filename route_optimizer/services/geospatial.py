"""Geospatial utility functions for distance and projection calculations."""

import math

EARTH_RADIUS_MILES = 3958.8


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great-circle distance between two points in miles."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_MILES * c


def point_to_segment_distance(
    plat: float, plon: float, lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Calculate the minimum distance from a point to a line segment on the sphere."""
    d1 = haversine_miles(plat, plon, lat1, lon1)
    d2 = haversine_miles(plat, plon, lat2, lon2)
    d_endpoint = min(d1, d2)

    seg_len = haversine_miles(lat1, lon1, lat2, lon2)
    if seg_len < 0.01:
        return d_endpoint

    lat3, lon3 = _project_point(plat, plon, lat1, lon1, lat2, lon2)

    if _between(lat3, lon3, lat1, lon1, lat2, lon2):
        return haversine_miles(plat, plon, lat3, lon3)
    return d_endpoint


def _project_point(
    plat: float, plon: float, lat1: float, lon1: float, lat2: float, lon2: float
) -> tuple[float, float]:
    """Project a point onto the great-circle segment between two points."""
    plat_r, plon_r, lat1_r, lon1_r, lat2_r, lon2_r = map(
        math.radians, [plat, plon, lat1, lon1, lat2, lon2]
    )

    x1 = math.cos(plat_r) * math.cos(plon_r)
    y1 = math.cos(plat_r) * math.sin(plon_r)
    z1 = math.sin(plat_r)

    x2 = math.cos(lat1_r) * math.cos(lon1_r)
    y2 = math.cos(lat1_r) * math.sin(lon1_r)
    z2 = math.sin(lat1_r)

    x3 = math.cos(lat2_r) * math.cos(lon2_r)
    y3 = math.cos(lat2_r) * math.sin(lon2_r)
    z3 = math.sin(lat2_r)

    vx, vy, vz = x3 - x2, y3 - y2, z3 - z2
    wx, wy, wz = x1 - x2, y1 - y2, z1 - z2

    c1 = vx * wx + vy * wy + vz * wz
    if c1 <= 0:
        return math.degrees(lat1_r), math.degrees(lon1_r)
    c2 = vx * vx + vy * vy + vz * vz
    if c2 <= c1:
        return math.degrees(lat2_r), math.degrees(lon2_r)

    t = c1 / c2
    ix = x2 + t * vx
    iy = y2 + t * vy
    iz = z2 + t * vz

    lat_p = math.atan2(iz, math.sqrt(ix * ix + iy * iy))
    lon_p = math.atan2(iy, ix)
    return math.degrees(lat_p), math.degrees(lon_p)


def _between(
    lat: float, lon: float, lat1: float, lon1: float, lat2: float, lon2: float
) -> bool:
    """Check if a projected point lies between two segment endpoints."""
    d1 = haversine_miles(lat, lon, lat1, lon1)
    d2 = haversine_miles(lat, lon, lat2, lon2)
    d_total = haversine_miles(lat1, lon1, lat2, lon2)
    return abs(d1 + d2 - d_total) < 0.5
