let map = null;
let routeLayer = null;
let stopMarkers = [];
let altMarkers = [];

function initMap() {
    map = L.map('map').setView([39.8283, -98.5795], 4);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 18,
    }).addTo(map);
}

function clearMap() {
    if (routeLayer) {
        map.removeLayer(routeLayer);
        routeLayer = null;
    }
    stopMarkers.forEach(marker => map.removeLayer(marker));
    stopMarkers = [];
    altMarkers.forEach(marker => map.removeLayer(marker));
    altMarkers = [];
}

function calculateRoute() {
    const startLocation = document.getElementById('start-location').value.trim();
    const destLocation = document.getElementById('dest-location').value.trim();
    const errorMsg = document.getElementById('error-msg');
    const btn = document.getElementById('calculate-btn');

    if (!startLocation || !destLocation) {
        errorMsg.textContent = 'Please enter both start and destination locations.';
        return;
    }

    errorMsg.textContent = '';
    btn.disabled = true;
    btn.textContent = 'Calculating...';
    document.getElementById('loader').style.display = 'flex';

    fetch('/api/route/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            start_location: startLocation,
            destination_location: destLocation,
        }),
    })
        .then(response => {
            if (!response.ok) {
                return response.json().then(err => { throw new Error(err.error || 'Request failed'); });
            }
            return response.json();
        })
        .then(data => {
            clearMap();
            renderRoute(data);
            renderRecommendedStops(data.recommended_stops);
            renderAlternativeStops(data.alternative_stops);
            renderSummary(data);
            fitMapBounds(data);
        })
        .catch(err => {
            errorMsg.textContent = err.message || 'An error occurred. Please try again.';
        })
        .finally(() => {
            btn.disabled = false;
            btn.textContent = 'Calculate Route';
            document.getElementById('loader').style.display = 'none';
        });
}

function renderRoute(data) {
    const coords = data.route_geometry.coordinates.map(c => [c[1], c[0]]);
    routeLayer = L.polyline(coords, {
        color: '#2196F3',
        weight: 4,
        opacity: 0.8,
    }).addTo(map);
}

function renderRecommendedStops(stops) {
    stops.forEach(stop => {
        const icon = L.divIcon({
            className: 'stop-marker',
            html: `<div class="stop-circle stop-circle-recommended"><span>${stop.stop_number}</span></div>`,
            iconSize: [30, 30],
            iconAnchor: [15, 15],
        });

        const marker = L.marker([stop.latitude, stop.longitude], { icon })
            .bindPopup(`
                <div class="popup">
                    <strong class="popup-tag recommended-tag">RECOMMENDED</strong>
                    <strong>Stop #${stop.stop_number}</strong><br/>
                    ${stop.name}<br/>
                    ${stop.city}, ${stop.state}<br/>
                    Price: $${stop.price_per_gallon.toFixed(2)}<br/>
                    Fuel Cost: $${stop.cost.toFixed(2)}<br/>
                    Gallons: ${stop.gallons_purchased}
                </div>
            `)
            .addTo(map);
        stopMarkers.push(marker);
    });
}

function renderAlternativeStops(stops) {
    const maxAltMarkers = 50;
    const displayStops = stops.slice(0, maxAltMarkers);

    displayStops.forEach((stop, idx) => {
        const icon = L.divIcon({
            className: 'stop-marker',
            html: `<div class="stop-circle stop-circle-alt"></div>`,
            iconSize: [18, 18],
            iconAnchor: [9, 9],
        });

        const marker = L.marker([stop.latitude, stop.longitude], { icon, opacity: 0.6 })
            .bindPopup(`
                <div class="popup">
                    <strong class="popup-tag alternative-tag">ALTERNATIVE</strong><br/>
                    ${stop.name}<br/>
                    ${stop.city}, ${stop.state}<br/>
                    Price: $${stop.price_per_gallon.toFixed(2)}<br/>
                    Distance from start: ${stop.distance_from_start} mi<br/>
                    Distance to destination: ${stop.distance_to_destination} mi<br/>
                    Distance to route: ${stop.distance_to_route} mi
                </div>
            `)
            .addTo(map);
        altMarkers.push(marker);
    });
}

function renderSummary(data) {
    document.getElementById('summary-distance').textContent = `${data.distance_miles.toFixed(1)} miles`;
    document.getElementById('summary-fuel').textContent = `${data.fuel_required_gallons} gallons`;
    document.getElementById('summary-cost').textContent = `$${data.estimated_total_fuel_cost.toFixed(2)}`;
    document.getElementById('summary-stops-count').textContent = data.recommended_stops.length;

    const stopsList = document.getElementById('stops-list');
    stopsList.innerHTML = '';

    if (data.recommended_stops.length > 0) {
        const h3 = document.createElement('h3');
        h3.className = 'section-title';
        h3.textContent = `Recommended Stops (${data.recommended_stops.length})`;
        stopsList.appendChild(h3);

        const table = document.createElement('table');
        table.className = 'stops-table';
        const thead = document.createElement('thead');
        thead.innerHTML = `
            <tr>
                <th>#</th>
                <th>Station</th>
                <th>City</th>
                <th>Price/gal</th>
                <th>Cost</th>
            </tr>
        `;
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        data.recommended_stops.forEach(stop => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${stop.stop_number}</td>
                <td>${stop.name}</td>
                <td>${stop.city}, ${stop.state}</td>
                <td>$${stop.price_per_gallon.toFixed(2)}</td>
                <td>$${stop.cost.toFixed(2)}</td>
            `;
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        stopsList.appendChild(table);
    }

    if (data.alternative_stops.length > 0) {
        const h3 = document.createElement('h3');
        h3.className = 'section-title';
        const displayCount = Math.min(data.alternative_stops.length, 50);
        h3.textContent = `Alternative Stops (${displayCount} of ${data.alternative_stops.length})`;
        stopsList.appendChild(h3);

        const note = document.createElement('p');
        note.className = 'alt-note';
        note.textContent = 'Sorted by closest to route, then cheapest. Not on the optimized route.';
        stopsList.appendChild(note);

        const table = document.createElement('table');
        table.className = 'stops-table';
        const thead = document.createElement('thead');
        thead.innerHTML = `
            <tr>
                <th>Station</th>
                <th>City</th>
                <th>Price/gal</th>
                <th>From Route</th>
            </tr>
        `;
        table.appendChild(thead);

        const tbody = document.createElement('tbody');
        data.alternative_stops.slice(0, 50).forEach(stop => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${stop.name}</td>
                <td>${stop.city}, ${stop.state}</td>
                <td>$${stop.price_per_gallon.toFixed(2)}</td>
                <td>${stop.distance_to_route} mi</td>
            `;
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);
        stopsList.appendChild(table);
    }

    document.getElementById('summary-panel').style.display = 'block';
}

function fitMapBounds(data) {
    const coords = data.route_geometry.coordinates.map(c => [c[1], c[0]]);
    if (data.recommended_stops) {
        data.recommended_stops.forEach(stop => {
            coords.push([stop.latitude, stop.longitude]);
        });
    }
    if (coords.length > 0) {
        const bounds = L.latLngBounds(coords);
        map.fitBounds(bounds, { padding: [50, 50] });
    }
}

document.addEventListener('DOMContentLoaded', initMap);
