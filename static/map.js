/* CampusPath map: UI only. No changes to Flask API or database. */
'use strict';
(() => {
  let map = null;
  let markerLayer = null;
  let routeLine = null;
  let points = new Map();
  const center = [38.99225, -76.94304];
  const byId = id => document.getElementById(id);
  const status = message => { const el = byId('map-status'); if (el) el.textContent = message; };
  const validCoordinates = loc => Number.isFinite(loc.latitude) && Number.isFinite(loc.longitude) &&
    Math.abs(loc.latitude) <= 90 && Math.abs(loc.longitude) <= 180;

  function initMap() {
    if (!byId('campus-map')) return;
    if (!window.L) { status('Map library unavailable. Check your internet connection.'); return; }
    map = L.map('campus-map', {scrollWheelZoom: false}).setView(center, 16);
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
    markerLayer = L.featureGroup().addTo(map);
    byId('map-reset')?.addEventListener('click', fitBuildings);
    status('Waiting for campus locations…');
  }

  function fitBuildings() {
    if (!map) return;
    if (markerLayer.getLayers().length) map.fitBounds(markerLayer.getBounds().pad(0.25), {maxZoom: 17});
    else map.setView(center, 16);
  }

  function chooseLocation(id, field) {
    const select = byId(field);
    if (!select) return;
    select.value = String(id);
    select.dispatchEvent(new Event('change', {bubbles: true}));
    status(`${field === 'start' ? 'Starting point' : 'Destination'} selected. Choose the other location and find your route.`);
  }

  function loadLocations(locations) {
    if (!map) return;
    markerLayer.clearLayers();
    points = new Map();
    if (routeLine) {map.removeLayer(routeLine); routeLine = null;}
    for (const loc of locations) {
      if (!validCoordinates(loc)) continue;
      points.set(loc.id, [loc.latitude, loc.longitude]);
      const marker = L.marker([loc.latitude, loc.longitude]);
      const popup = document.createElement('div');
      const name = document.createElement('strong'); name.textContent = loc.name;
      const actions = document.createElement('div'); actions.className = 'map-popup-actions';
      for (const [label, field] of [['Set as start', 'start'], ['Set as destination', 'destination']]) {
        const button = document.createElement('button'); button.type = 'button'; button.textContent = label;
        button.addEventListener('click', () => chooseLocation(loc.id, field));
        actions.append(button);
      }
      popup.append(name, actions);
      marker.bindPopup(popup);
      marker.addTo(markerLayer);
    }
    fitBuildings();
    status(points.size ? `${points.size} campus building markers loaded. Click a pin to select a location.` :
      'No locations with valid map coordinates were returned.');
  }

  function clearLine() {
    if (map && routeLine) {map.removeLayer(routeLine); routeLine = null;}
  }
  function showConnection({startId, destinationId}) {
    clearLine();
    if (!map || !points.has(startId) || !points.has(destinationId)) return;
    // Important: only a straight visual connector, NOT a pedestrian route geometry.
    routeLine = L.polyline([points.get(startId), points.get(destinationId)], {
      color: '#137f75', weight: 4, opacity: 0.9, dashArray: '9 10'
    }).addTo(map);
    map.fitBounds(routeLine.getBounds().pad(0.45), {maxZoom: 17});
    status('Selected buildings connected by a dashed visual guide (not a walking path).');
  }
  document.addEventListener('campuspath:locations', event => loadLocations(event.detail.locations));
  document.addEventListener('campuspath:route-cleared', clearLine);
  document.addEventListener('campuspath:route', event => showConnection(event.detail));
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initMap, {once: true});
  else initMap();
})();
