# Fuel Route Optimizer

A Django-based web application that calculates cost-optimized fuel stops for road trips across North America. Given a start and destination location, it computes the driving route via OSRM, then places fuel stops at regular intervals choosing the cheapest stations near the route. A fuel stop is always enforced near the start location, regardless of trip distance.

## Features

- **Route calculation** via OSRM (free, no API key required)
- **Cost-optimized fuel stop planning** using greedy interval placement
- **Alternative stops** listed for every recommended stop
- **Interactive Leaflet.js map** visualization with route and stops
- **Spatial indexing** via scikit-learn BallTree for fast station lookup
- **Cached geocoding** with Nominatim + state/province centroid fallback
- **Supports US and Canadian** fuel stations

## Prerequisites

- Python 3.14+
- pip

## Setup

1. Create and activate a virtual environment:
```bash
python -m venv venv
venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Ensure the fuel prices CSV is at `fuel-prices-for-be-assessment.csv` (included).

4. Run the development server:
```bash
python manage.py runserver
```

5. Open http://127.0.0.1:8000 in your browser.

## First Run

On first startup, the application geocodes all unique City+State combinations from the fuel CSV using OpenStreetMap's Nominatim service. This takes approximately 1-2 minutes and is cached to `data/geocoded_cache.json` for instant subsequent loads. If Nominatim rate-limits the requests, the system falls back to state/province centroids.

## Usage

1. Enter a start location (e.g., "Dallas, TX")
2. Enter a destination location (e.g., "Los Angeles, CA")
3. Click "Calculate Route"
4. View the optimized route on the map with recommended and alternative fuel stops
5. Review the route summary with cost breakdown

## API

### POST /api/route/

**Request:**
```json
{
    "start_location": "Dallas, TX",
    "destination_location": "Los Angeles, CA"
}
```

**Response:**
```json
{
    "start_location": "Dallas, TX",
    "destination_location": "Los Angeles, CA",
    "distance_miles": 1435.2,
    "fuel_required_gallons": 143.5,
    "estimated_total_fuel_cost": 465.82,
    "recommended_stops": [
        {
            "name": "SHEETZ #701",
            "city": "Amarillo",
            "state": "TX",
            "price_per_gallon": 2.874,
            "gallons_purchased": 50.0,
            "cost": 143.7,
            "latitude": 35.222,
            "longitude": -101.831,
            "stop_number": 1,
            "distance_to_route": 0.0
        }
    ],
    "alternative_stops": [
        {
            "name": "CATTREZ",
            "city": "Irving",
            "state": "NY",
            "price_per_gallon": 2.899,
            "latitude": 42.568,
            "longitude": -79.113,
            "distance_to_route": 2.1,
            "distance_from_start": 120.5,
            "distance_to_destination": 1310.0
        }
    ],
    "route_geometry": {
        "type": "LineString",
        "coordinates": [[-96.80, 32.78], [-118.24, 34.05]]
    }
}
```

### Response Fields

| Field | Description |
|-------|-------------|
| `distance_miles` | Total driving distance in miles |
| `fuel_required_gallons` | Total fuel needed based on vehicle MPG |
| `estimated_total_fuel_cost` | Total fuel needed × average price per gallon across all recommended stops |
| `recommended_stops` | Optimally placed fuel stops to minimize cost |
| `recommended_stops[].stop_number` | Sequential stop order along the route |
| `recommended_stops[].distance_to_route` | Miles off the main route |
| `alternative_stops` | Other available stations near the route |
| `route_geometry` | GeoJSON LineString of the driving route |

## Vehicle Assumptions

Configurable in `route_optimizer/services/fuel_optimizer.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `RANGE_MILES` | 500 | Maximum driving range on a full tank |
| `MPG` | 10 | Fuel efficiency in miles per gallon |
| `TANK_CAPACITY_GALLONS` | 50 | Derived as RANGE_MILES / MPG |
| `STOP_INTERVAL` | 450 | Miles between fuel stop placements |
| `SEARCH_RADIUS` | 60 | Primary search radius for stations near route |
| `SEARCH_RADIUS_EXPANDED` | 150 | Fallback search radius if no stations found |
| `BUFFER_MILES` | 200 | Maximum distance from route to include stations |
| `FIRST_STOP_DISTANCE` | 1 | Miles from start before first stop (enforced near-start stop) |

## Architecture

```
fuel_route_optimizer/
├── manage.py                          # Django management script
├── requirements.txt                   # Python dependencies
├── fuel-prices-for-be-assessment.csv  # Fuel station price data
├── data/
│   └── geocoded_cache.json            # Cached geocoding results (generated)
├── fuel_route_optimizer/              # Django project package
│   ├── settings.py                    # Django settings
│   ├── urls.py                        # Root URL configuration
│   ├── wsgi.py                        # WSGI entry point
│   └── asgi.py                        # ASGI entry point
└── route_optimizer/                   # Main application
    ├── views.py                       # REST API and template views
    ├── urls.py                        # App URL patterns
    ├── utils.py                       # Location geocoding wrapper
    ├── services/
    │   ├── fuel_loader.py             # CSV loading + BallTree spatial index
    │   ├── routing_service.py         # OSRM route fetching
    │   ├── fuel_optimizer.py          # Greedy fuel stop optimization
    │   ├── geocoder.py                # Nominatim geocoding + caching
    │   └── geospatial.py              # Haversine distance + point-to-segment
    ├── templates/
    │   └── index.html                 # Main page with Leaflet map
    └── static/
        ├── js/
        │   └── app.js                 # Frontend route calculation + map
        └── css/
            └── styles.css             # Application styles
```

## Dependencies

| Package | Purpose |
|---------|---------|
| Django >= 5.0 | Web framework |
| requests | HTTP client for OSRM and Nominatim |
| pandas | CSV parsing for fuel data |
| numpy | Numerical computations |
| scikit-learn | BallTree spatial indexing |
| geopy | Nominatim geocoding client |
| shapely | Geometric operations |
| polyline | OSRM polyline encoding/decoding |

## External Services

- **OSRM** (`router.project-osrm.org`) — free driving route calculation, no API key required
- **Nominatim** (`nominatim.openstreetmap.org`) — free geocoding, rate-limited (1 req/sec with 1.2s interval enforced)
