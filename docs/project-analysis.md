# Fuel Route Optimizer — Project Analysis

## What It Does

Given a starting point and a destination, the application finds the cheapest fuel stops for your road trip. It calculates the driving route, then intelligently places fuel stops at regular intervals, always picking the cheapest station near the route. A fuel stop is always enforced near the start location, regardless of trip distance.

---

## Architecture Overview

The application is a Django web app with a clean service-layer architecture. Every request flows through five stages:

```
Browser → Django View → Geocoding → OSRM Routing → Fuel Optimization → JSON Response
```

### Component Breakdown

| Component | File | Responsibility |
|---|---|---|
| **Views** | `views.py` | Entry point. Receives POST request, orchestrates all services, returns JSON |
| **Geocoding** | `geocoder.py`, `utils.py` | Converts text addresses ("Dallas, TX") into latitude/longitude coordinates |
| **Routing** | `routing_service.py` | Calls the free OSRM service to compute the actual driving route (not a straight line) |
| **Fuel Loader** | `fuel_loader.py` | Loads fuel station CSV at startup, attaches coordinates, builds spatial index |
| **Fuel Optimizer** | `fuel_optimizer.py` | Core algorithm — finds cheapest fuel stops along the route |
| **Geospatial Utils** | `geospatial.py` | Mathematical helpers for distance calculations on a sphere |

### Data Flow

1. User submits "Dallas, TX" → "Los Angeles, CA" in the browser
2. `views.py` geocodes both locations into coordinates
3. `routing_service.py` calls OSRM to get the driving route as a sequence of coordinate points
4. `fuel_optimizer.py` processes the route to find optimal fuel stops:
   - Filters stations within a 200-mile corridor of the route
   - Places stops at 450-mile intervals along the route
   - At each interval, picks the cheapest station within 60 miles (expands to 150 if needed)
5. Result is returned as JSON with recommended stops, alternatives, route geometry, and cost breakdown

---

## Algorithms Explained

### Greedy Interval Stop Placement

The fuel optimization uses a **greedy algorithm** — it makes the locally best choice at each step.

**How it works:**

1. **Compute stop markers**: Divide the total trip distance into intervals. First stop is 1 mile from start (enforcing a near-start fuel stop), then every 450 miles after that. This ensures the vehicle never runs out of fuel (500-mile range with 450-mile spacing leaves a 50-mile buffer).

2. **Find waypoint**: For each stop marker, interpolate the exact latitude/longitude on the route at that distance. This is done with linear interpolation between route coordinates using a cumulative distance array.

3. **Find cheapest candidate**: Within a 60-mile radius of the waypoint, find all stations not already visited. Sort by (price, distance) — cheapest first, then closest. Pick the first result.

4. **Expand if needed**: If no stations are found within 60 miles, expand the search to 150 miles.

5. **Repeat**: Continue until the destination is within the vehicle's remaining range.

6. **Calculate total cost**: Compute the average price per gallon across all recommended stops, then multiply by total fuel needed: `total_cost = fuel_needed_gallons × avg(price_per_gallon)`.

**Why greedy works here:** Fuel prices are relatively stable within a region, and the cost of a stop is independent of other stops (you always fill a full 50-gallon tank). There's no complex inter-dependency between stops that would require dynamic programming or branch-and-bound.

**Near-start enforcement:** A fuel stop is always placed near the start location (1 mile from start), even for trips shorter than 500 miles. This ensures travelers can refuel immediately before beginning their journey, regardless of destination distance.

**Vehicle assumptions that drive the algorithm:**
- Range: 500 miles per tank
- Efficiency: 10 MPG
- Tank capacity: 50 gallons (derived)
- Stop interval: 450 miles (leaves 50-mile safety margin)

### Corridor Filtering

Before optimization begins, stations are filtered to a **200-mile corridor** around the route. This reduces the candidate set from potentially thousands of stations nationwide to only those relevant to the trip.

The filtering works by:
1. Sampling the route at every 10th point (reduces computation)
2. For each station, computing its minimum distance to any segment in the sampled route
3. Keeping only stations within 200 miles of the route

### Distance Calculations

All distance calculations use the **Haversine formula**, which computes great-circle distance between two points on a sphere. This accounts for Earth's curvature and is accurate for road-trip-scale distances.

The `point_to_segment_distance` function projects a point onto the great-circle between two route points using 3D Cartesian coordinates, then checks if the projection falls between the segment endpoints.

---

## Caching System

The application uses two distinct caching layers, each serving a different purpose.

### Cache Layer 1: Geocoding Cache (Persistent Disk Cache)

**What it caches:** Latitude/longitude for each unique City+State pair.

**Where it lives:** `data/geocoded_cache.json` — a simple JSON file on disk.

**How it works:**

```
geocode_city_state("Amarillo", "TX")
    │
    ├── Step 1: Check in-memory dict (_cache)
    │       ├── HIT → return cached coordinates instantly
    │       └── MISS → continue
    │
    ├── Step 2: Call Nominatim API (if available)
    │       ├── Success → store in _cache, return coordinates
    │       └── Rate-limited → set _api_available = False, fall through
    │
    └── Step 3: Fallback to state centroid
            └── Store in _cache, return state center coordinates
```

**Cache-hit behavior:**
- On first startup, the cache file is empty. Every station's city/state must be geocoded via the Nominatim API, with a 1.2-second delay between requests (rate limiting).
- The cache is flushed to disk every 50 geocoded locations, so data is never lost mid-process.
- On subsequent startups, the cache file is loaded into memory at initialization. If a city/state was already geocoded, it returns instantly — no API call.
- Cache misses during normal operation (user geocoding of start/destination) do NOT write to the persistent cache — they're one-off queries.

**Fallback chain:**
1. In-memory cache → instant hit
2. Nominatim API → accurate coordinates, but rate-limited (1 request/sec enforced)
3. State centroid → less precise (all stations in a city get the state's center), but always available

**Performance impact:**
- **First run**: ~1-2 minutes to geocode all unique city/state pairs (1.2s delay × number of unique pairs)
- **Subsequent runs**: Near-instant startup if all pairs are cached — no API calls needed
- The cache grows over time as new city/state pairs are encountered

### Cache Layer 2: In-Memory Station Data

**What it caches:** The full list of processed fuel stations and the BallTree spatial index.

**Where it lives:** Module-level variables in `fuel_loader.py` (`stations` list, `spatial_index` BallTree).

**How it works:**
- `load_fuel_data()` is called once on the first API request
- The CSV is parsed, stations are geocoded and deduplicated, and the BallTree is built
- Everything stays in memory for the lifetime of the Django process
- Subsequent requests reuse the same data — no CSV re-read, no BallTree rebuild

**Cache-hit behavior:**
- The `views.py` checks `if not fuel_loader.stations` before calling `load_fuel_data()`, ensuring one-time initialization
- This is effectively a "compute-once, reuse-forever" pattern

**Performance impact:**
- First request pays the full cost: CSV parse + geocoding + BallTree construction
- All subsequent requests skip to the routing and optimization steps

---

## Performance Analysis

### BallTree Spatial Index

**What it is:** A BallTree is a spatial indexing data structure from scikit-learn that organizes points in N-dimensional space (here, latitude/longitude on a sphere) into nested hyperspheres. It's built once at startup and used for fast neighbor queries.

**How it's built** (`fuel_loader.py:58`):
```python
coords_rad = np.radians(np.array([[s['lat'], s['lon']] for s in stations]))
spatial_index = BallTree(coords_rad, metric='haversine')
```

All station coordinates are converted to radians and indexed with the haversine metric, which measures great-circle distance.

**Build cost:** O(n log n) where n is the number of stations. For ~10,000 stations, this takes a fraction of a second.

**Current usage:** The BallTree is built and stored but currently **not used** in the optimization. The `_find_candidates` function in `fuel_optimizer.py` still does a linear scan (O(n)) of all filtered stations. The architecture improvements design doc (`docs/.../architecture-improvements-design.md`) plans to replace this with `BallTree.query_radius()` for O(log n) lookups.

### Preprocessing Steps That Improve Performance

Several preprocessing steps reduce the work needed during each query:

1. **Deduplication** (`_deduplicate_stations_by_location`): Multiple stations at the same coordinates are collapsed to the cheapest one. This reduces the station count before any filtering.

2. **Route sampling** (`_sample_route_points`): The full route from OSRM can have thousands of coordinate points. Sampling every 10th point reduces the segment count by 10×, which directly speeds up corridor filtering and distance computation.

3. **Corridor filtering** (`_filter_locations_in_corridor`): The 200-mile corridor filter reduces ~10,000+ stations to typically a few hundred relevant to the trip. This is done once per request, then all subsequent optimization operates on the smaller set.

4. **Cumulative distance array** (`_cumulative_route_distances`): Precomputed once per request, this array enables O(log n) binary search for point-at-mile lookups instead of walking the route from the start each time.

### Complexity Comparison

| Operation | Naive Approach | Optimized Approach | Improvement |
|---|---|---|---|
| Station candidate lookup | O(n) scan of all stations | O(n) scan of corridor-filtered stations | ~10-50× fewer candidates |
| Route-segment distance | O(route_length) per station | O(route_length/10) via sampling | 10× fewer distance computations |
| Point-at-mile interpolation | O(route_length) linear walk | O(route_length) but with precomputed cumulative array | Same asymptotic, faster constant |
| Spatial index build | Not applicable | O(n log n) BallTree at startup | Enables future O(log n) queries |

**Overall impact:** For a 1,400-mile cross-country trip:
- The naive approach would check every station against every route segment
- The optimized approach reduces this to: check only corridor-filtered stations against sampled segments
- In practice, this brings computation from potentially millions of distance calculations to a few thousand

### Where Performance Could Be Better

The current `_find_candidates` function in `fuel_optimizer.py:214` performs an O(n) linear scan over all filtered stations for each stop marker. With the planned BallTree integration:

```python
# Current (naive):
for station in stations:
    d = haversine_miles(wp_lat, wp_lon, station['lat'], station['lon'])
    if d <= radius: candidates.append(station)

# Planned (BallTree):
indices = spatial_index.query_radius([[wp_rad]], r=radius_rad)
candidates = [stations[i] for i in indices[0]]
```

This changes each candidate lookup from O(filtered_stations) to O(log n + k), where k is the number of results. For 200 filtered stations, the difference is modest, but for larger datasets it would be significant.

---

## Summary

The Fuel Route Optimizer is a well-structured Django application that:
- Uses a **greedy interval algorithm** to place fuel stops at regular intervals along a route
- Picks the **cheapest station** within a configurable radius at each interval
- Caches geocoding results to disk for instant startup on subsequent runs
- Preprocesses data (deduplication, corridor filtering, route sampling) to reduce per-request computation
- Has a BallTree spatial index built at startup, ready for future O(log n) candidate lookups
