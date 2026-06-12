"""Fuel station CSV loader with spatial indexing and geocoding."""

import logging
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.neighbors import BallTree
from .geocoder import geocode_city_state, init_geocoder

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FUEL_CSV = BASE_DIR / 'fuel-prices-for-be-assessment.csv'

stations = []
spatial_index = None


def load_fuel_data() -> list[dict]:
    global stations, spatial_index

    init_geocoder()
    df = pd.read_csv(FUEL_CSV)

    processed: list[dict] = []
    total = len(df)
    logger.info("Processing %d rows from CSV...", total)

    for i, (_, row) in enumerate(df.iterrows()):
        if (i + 1) % 1000 == 0:
            logger.info("Processed %d/%d rows, %d stations so far...", i + 1, total, len(processed))

        name = str(row.get('Truckstop Name', '')).strip()
        city = str(row.get('City', '')).strip()
        state = str(row.get('State', '')).strip()
        price = float(row.get('Retail Price', 0))
        address = str(row.get('Address', '')).strip()

        if not name or not city or not state:
            continue

        coords = geocode_city_state(city, state)
        if coords is None:
            continue

        processed.append({
            'name': name,
            'address': address,
            'city': city,
            'state': state,
            'price': price,
            'lat': coords[0],
            'lon': coords[1],
        })

    stations = processed
    coords_rad = np.radians(np.array([[s['lat'], s['lon']] for s in stations]))
    spatial_index = BallTree(coords_rad, metric='haversine')
    logger.info("Loaded %d fuel stations with spatial index", len(stations))
    return stations
