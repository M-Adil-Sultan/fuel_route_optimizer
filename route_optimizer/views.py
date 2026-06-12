"""REST API and template views for the fuel route optimizer."""

import json
import logging
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.template import loader
from .services import fuel_loader
from .services.routing_service import get_route
from .services.fuel_optimizer import optimize_fuel_stops, RANGE_MILES, MPG
from .utils import geocode_location

logger = logging.getLogger(__name__)

RECOMMENDED_STOP_FIELDS = (
    'name', 'city', 'state', 'price_per_gallon',
    'gallons_purchased', 'cost', 'latitude', 'longitude',
    'stop_number', 'distance_to_route',
)

ALTERNATIVE_STOP_FIELDS = (
    'name', 'city', 'state', 'price_per_gallon',
    'latitude', 'longitude', 'distance_to_route',
    'distance_from_start', 'distance_to_destination',
)


def index(request) -> HttpResponse:
    """Render the main page with vehicle assumptions."""
    template = loader.get_template('index.html')
    return HttpResponse(template.render({
        'range_miles': RANGE_MILES,
        'mpg': MPG,
    }, request))


@csrf_exempt
@require_http_methods(["POST"])
def calculate_route(request) -> JsonResponse:
    """API endpoint to compute an optimized fuel route between two locations."""
    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON in request body'}, status=400)

    start_location = body.get('start_location', '').strip()
    destination_location = body.get('destination_location', '').strip()

    if not start_location or not destination_location:
        return JsonResponse(
            {'error': 'Both start_location and destination_location are required'},
            status=400,
        )

    if not fuel_loader.stations:
        fuel_loader.load_fuel_data()

    start_coords = geocode_location(start_location)
    if not start_coords:
        return JsonResponse(
            {'error': f'Could not geocode start location: {start_location}'},
            status=400,
        )

    dest_coords = geocode_location(destination_location)
    if not dest_coords:
        return JsonResponse(
            {'error': f'Could not geocode destination: {destination_location}'},
            status=400,
        )

    try:
        route = get_route(start_coords[0], start_coords[1], dest_coords[0], dest_coords[1])
    except Exception as e:
        logger.error("Route calculation failed: %s", e)
        return JsonResponse({'error': str(e)}, status=500)

    fuel_result = optimize_fuel_stops(
        route['coordinates'],
        start_coords[0], start_coords[1],
        dest_coords[0], dest_coords[1],
    )

    recommended_response = [
        {field: stop[field] for field in RECOMMENDED_STOP_FIELDS}
        for stop in fuel_result['recommended_stops']
    ]
    alternative_response = [
        {field: stop[field] for field in ALTERNATIVE_STOP_FIELDS}
        for stop in fuel_result['alternative_stops']
    ]

    coordinates = [[lon, lat] for lat, lon in route['coordinates']]

    return JsonResponse({
        'start_location': start_location,
        'destination_location': destination_location,
        'distance_miles': route['distance_miles'],
        'fuel_required_gallons': fuel_result['fuel_needed_gallons'],
        'estimated_total_fuel_cost': fuel_result['total_fuel_cost'],
        'recommended_stops': recommended_response,
        'alternative_stops': alternative_response,
        'route_geometry': {
            'type': 'LineString',
            'coordinates': coordinates,
        },
    })
