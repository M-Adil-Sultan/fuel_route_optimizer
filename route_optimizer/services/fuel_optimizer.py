"""Fuel stop optimization along a driving route."""

import logging
from .geospatial import haversine_miles, point_to_segment_distance

logger = logging.getLogger(__name__)

# Vehicle assumptions
RANGE_MILES = 500
MPG = 10
TANK_CAPACITY_GALLONS = RANGE_MILES / MPG

# Optimization parameters
STOP_INTERVAL = 450
SEARCH_RADIUS = 60
SEARCH_RADIUS_EXPANDED = 150
BUFFER_MILES = 200
FIRST_STOP_DISTANCE = 30


def optimize_fuel_stops(
    route_coordinates: list[tuple[float, float]],
    start_lat: float,
    start_lon: float,
    dest_lat: float,
    dest_lon: float,
) -> dict:
    """Find optimal fuel stops along a route to minimize total fuel cost."""
    from .fuel_loader import stations, spatial_index

    if not stations or not spatial_index:
        return {
            'recommended_stops': [],
            'alternative_stops': [],
            'total_fuel_cost': 0,
            'fuel_needed_gallons': 0,
        }

    distance_miles = _total_route_distance(route_coordinates)
    fuel_needed = distance_miles / MPG

    best_at_location = _deduplicate_stations_by_location(stations)
    filtered = _filter_locations_in_corridor(route_coordinates, list(best_at_location.values()))

    if not filtered:
        return {
            'recommended_stops': [],
            'alternative_stops': [],
            'total_fuel_cost': 0,
            'fuel_needed_gallons': round(fuel_needed, 1),
        }

    station_route_dist = _compute_station_route_distances(filtered, route_coordinates)
    dist_start_to_dest = haversine_miles(start_lat, start_lon, dest_lat, dest_lon)

    recommended_stops, visited_locations = _greedy_interval_stops(
        filtered,
        route_coordinates,
        start_lat,
        start_lon,
        dest_lat,
        dest_lon,
        station_route_dist,
        dist_start_to_dest,
    )

    alternative_stops = _build_alternative_stops(
        filtered,
        start_lat,
        start_lon,
        dest_lat,
        dest_lon,
        station_route_dist,
        visited_locations,
    )

    if recommended_stops:
        avg_price = sum(s['price_per_gallon'] for s in recommended_stops) / len(recommended_stops)
        total_cost = round(fuel_needed * avg_price, 2)
    else:
        total_cost = 0.0

    return {
        'recommended_stops': recommended_stops,
        'alternative_stops': alternative_stops,
        'total_fuel_cost': total_cost,
        'fuel_needed_gallons': round(fuel_needed, 1),
    }


# ---------------------------------------------------------------------------
# Station filtering and deduplication
# ---------------------------------------------------------------------------

def _deduplicate_stations_by_location(stations: list[dict]) -> dict[tuple, dict]:
    """Keep only the cheapest station at each unique (lat, lon)."""
    best: dict[tuple[float, float], dict] = {}
    for idx, station in enumerate(stations):
        key = (station['lat'], station['lon'])
        if key not in best or station['price'] < best[key]['price']:
            best[key] = {**station, '_idx': idx}
    return best


def _filter_locations_in_corridor(
    route_coordinates: list[tuple[float, float]],
    locations: list[dict],
) -> list[dict]:
    """Filter stations that lie within BUFFER_MILES of the route."""
    sampled = _sample_route_points(route_coordinates, every_n=10)
    filtered: list[dict] = []

    for station in locations:
        min_dist = _min_distance_to_route(station['lat'], station['lon'], sampled)
        if min_dist <= BUFFER_MILES:
            filtered.append(station)

    return filtered


def _compute_station_route_distances(
    stations: list[dict],
    route_coordinates: list[tuple[float, float]],
) -> dict[tuple[float, float], float]:
    """Compute the minimum distance from each station to the route."""
    sampled = _sample_route_points(route_coordinates, every_n=10)
    distances: dict[tuple[float, float], float] = {}

    for station in stations:
        min_dist = _min_distance_to_route(station['lat'], station['lon'], sampled)
        distances[(station['lat'], station['lon'])] = round(min_dist, 1)

    return distances


def _min_distance_to_route(
    plat: float,
    plon: float,
    sampled: list[tuple[float, float]],
) -> float:
    """Find the minimum distance from a point to any segment in the sampled route."""
    min_dist = float('inf')
    for i in range(len(sampled) - 1):
        seg_dist = point_to_segment_distance(
            plat, plon,
            sampled[i][0], sampled[i][1],
            sampled[i + 1][0], sampled[i + 1][1],
        )
        min_dist = min(min_dist, seg_dist)
        if min_dist <= 1:
            break
    return min_dist


# ---------------------------------------------------------------------------
# Greedy stop placement
# ---------------------------------------------------------------------------

def _greedy_interval_stops(
    stations: list[dict],
    route_coords: list[tuple[float, float]],
    start_lat: float,
    start_lon: float,
    dest_lat: float,
    dest_lon: float,
    station_route_dist: dict[tuple[float, float], float],
    total_dist: float,
) -> tuple[list[dict], set[tuple[float, float]]]:
    """Place fuel stops at regular intervals along the route using a greedy strategy."""
    cum_dists = _cumulative_route_distances(route_coords)
    stop_markers = _compute_stop_markers(total_dist)
    recommended_stops: list[dict] = []
    visited_locations: set[tuple[float, float]] = set()

    for marker_mile in stop_markers:
        wp_lat, wp_lon = _point_at_mile(route_coords, cum_dists, marker_mile, total_dist)
        candidates = _find_candidates(
            stations, wp_lat, wp_lon, visited_locations, SEARCH_RADIUS, SEARCH_RADIUS_EXPANDED
        )

        if not candidates:
            continue

        candidates.sort(key=lambda x: (x[0]['price'], x[1]))
        best_station, _best_dist = candidates[0]

        dist_from_start = haversine_miles(start_lat, start_lon, best_station['lat'], best_station['lon'])
        cost = round(TANK_CAPACITY_GALLONS * best_station['price'], 2)

        recommended_stops.append({
            'stop_number': len(recommended_stops) + 1,
            'name': best_station['name'],
            'city': best_station['city'],
            'state': best_station['state'],
            'price_per_gallon': best_station['price'],
            'gallons_purchased': round(TANK_CAPACITY_GALLONS, 1),
            'cost': cost,
            'latitude': best_station['lat'],
            'longitude': best_station['lon'],
            'distance_covered': round(dist_from_start, 1),
            'distance_to_route': station_route_dist.get(
                (best_station['lat'], best_station['lon']), 0
            ),
        })
        visited_locations.add((best_station['lat'], best_station['lon']))

    return recommended_stops, visited_locations


def _find_candidates(
    stations: list[dict],
    wp_lat: float,
    wp_lon: float,
    visited: set[tuple[float, float]],
    radius: float,
    expanded_radius: float,
) -> list[tuple[dict, float]]:
    """Find candidate stations near a waypoint, expanding radius if needed."""
    candidates: list[tuple[dict, float]] = []
    for station in stations:
        loc_key = (station['lat'], station['lon'])
        if loc_key in visited:
            continue
        d = haversine_miles(wp_lat, wp_lon, station['lat'], station['lon'])
        if d <= radius:
            candidates.append((station, d))

    if not candidates:
        for station in stations:
            loc_key = (station['lat'], station['lon'])
            if loc_key in visited:
                continue
            d = haversine_miles(wp_lat, wp_lon, station['lat'], station['lon'])
            if d <= expanded_radius:
                candidates.append((station, d))

    return candidates


def _compute_stop_markers(total_dist: float) -> list[float]:
    """Compute mile markers where fuel stops should be placed."""
    markers = [1.0]
    mile = 1.0 + STOP_INTERVAL
    while mile < total_dist - STOP_INTERVAL * 0.1:
        markers.append(mile)
        mile += STOP_INTERVAL
    return markers


# ---------------------------------------------------------------------------
# Alternative stops
# ---------------------------------------------------------------------------

def _build_alternative_stops(
    filtered: list[dict],
    start_lat: float,
    start_lon: float,
    dest_lat: float,
    dest_lon: float,
    station_route_dist: dict[tuple[float, float], float],
    visited_locations: set[tuple[float, float]],
) -> list[dict]:
    """Build list of alternative fuel stops excluding recommended ones."""
    alternatives: list[dict] = []
    for station in filtered:
        loc_key = (station['lat'], station['lon'])
        if loc_key in visited_locations:
            continue

        alternatives.append({
            'name': station['name'],
            'city': station['city'],
            'state': station['state'],
            'price_per_gallon': station['price'],
            'latitude': station['lat'],
            'longitude': station['lon'],
            'distance_to_route': station_route_dist.get(loc_key, 0),
            'distance_from_start': round(
                haversine_miles(start_lat, start_lon, station['lat'], station['lon']), 1
            ),
            'distance_to_destination': round(
                haversine_miles(station['lat'], station['lon'], dest_lat, dest_lon), 1
            ),
        })

    alternatives.sort(key=lambda s: (s['distance_to_route'], s['price_per_gallon']))
    return alternatives


# ---------------------------------------------------------------------------
# Route geometry helpers
# ---------------------------------------------------------------------------

def _total_route_distance(coordinates: list[tuple[float, float]]) -> float:
    """Compute the total distance of the route by summing segment distances."""
    total = 0.0
    for i in range(len(coordinates) - 1):
        total += haversine_miles(
            coordinates[i][0], coordinates[i][1],
            coordinates[i + 1][0], coordinates[i + 1][1],
        )
    return total


def _cumulative_route_distances(
    route_coords: list[tuple[float, float]],
) -> list[float]:
    """Build cumulative distance array along the route."""
    cum_dists = [0.0]
    for i in range(len(route_coords) - 1):
        d = haversine_miles(
            route_coords[i][0], route_coords[i][1],
            route_coords[i + 1][0], route_coords[i + 1][1],
        )
        cum_dists.append(cum_dists[-1] + d)
    return cum_dists


def _point_at_mile(
    route_coords: list[tuple[float, float]],
    cum_dists: list[float],
    mile: float,
    total_dist: float,
) -> tuple[float, float]:
    """Interpolate the (lat, lon) point at a given mile marker along the route."""
    if mile <= 0:
        return route_coords[0]
    if mile >= total_dist:
        return route_coords[-1]

    for i in range(len(cum_dists) - 1):
        if cum_dists[i] <= mile <= cum_dists[i + 1]:
            seg_len = cum_dists[i + 1] - cum_dists[i]
            if seg_len < 0.001:
                return route_coords[i]
            t = (mile - cum_dists[i]) / seg_len
            lat = route_coords[i][0] + t * (route_coords[i + 1][0] - route_coords[i][0])
            lon = route_coords[i][1] + t * (route_coords[i + 1][1] - route_coords[i][1])
            return (lat, lon)

    return route_coords[-1]


def _sample_route_points(
    coordinates: list[tuple[float, float]],
    every_n: int = 10,
) -> list[tuple[float, float]]:
    """Sample route coordinates at regular intervals to reduce computation."""
    if len(coordinates) <= every_n * 2:
        return coordinates
    return [coordinates[i] for i in range(0, len(coordinates), every_n)]
