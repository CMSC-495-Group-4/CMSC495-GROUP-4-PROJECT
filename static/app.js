const $ = (id) => document.getElementById(id);
let locations = [];

function showMessage(message) {
  $('message').textContent = message;
  $('message').hidden = !message;
}

function isValidLocation(location) {
  return Number.isInteger(location?.id)
    && typeof location.name === 'string'
    && typeof location.accessible === 'boolean';
}

function setLocationOptions(message) {
  for (const id of ['start', 'destination']) {
    $(id).replaceChildren(new Option(message, ''));
  }
}

async function initialize() {
  try {
    const response = await fetch('/api/locations', {
      headers: {Accept: 'application/json'}
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.error?.message || 'Unable to load campus locations.');
    }
    if (!Array.isArray(data.locations) || !data.locations.every(isValidLocation)) {
      throw new Error('The server returned an invalid locations response.');
    }

    locations = data.locations;
    if (locations.length === 0) {
      setLocationOptions('No campus locations configured');
      $('mode-label').textContent = 'CONNECTED — no campus locations configured';
      $('submit').disabled = true;
      showMessage('Add buildings and pathways to the database to enable routing.');
      return;
    }

    for (const id of ['start', 'destination']) {
      const select = $(id);
      select.replaceChildren(new Option('Select a campus location', ''));
      locations.forEach((location) => {
        select.add(new Option(location.name, String(location.id)));
      });
    }
    $('mode-label').textContent = 'CONNECTED — Flask API';
    $('submit').disabled = false;
  } catch (error) {
    locations = [];
    setLocationOptions('Unable to load locations');
    $('mode-label').textContent = 'BACKEND UNAVAILABLE';
    $('submit').disabled = true;
    showMessage(error.message || 'Unable to load campus locations.');
  }
}

function renderRoute(data, startId, destinationId) {
  if (
    !data
    || typeof data.routeId !== 'string'
    || !Array.isArray(data.pathwayIds)
    || !data.pathwayIds.every(Number.isInteger)
    || !Number.isFinite(data.distanceMeters)
    || data.distanceMeters < 0
    || !Number.isFinite(data.estimatedMinutes)
    || data.estimatedMinutes < 0
    || !['ai', 'distance-based'].includes(data.predictionSource)
    || typeof data.accessible !== 'boolean'
  ) {
    throw new Error('The server returned an invalid route response.');
  }

  $('result-start').textContent = locations.find((location) => location.id === startId)?.name || String(startId);
  $('result-destination').textContent = locations.find((location) => location.id === destinationId)?.name || String(destinationId);
  $('minutes').textContent = data.estimatedMinutes.toFixed(1);
  $('distance').textContent = Math.round(data.distanceMeters).toLocaleString();
  $('route-id').textContent = data.routeId;
  $('accessibility-result').textContent = data.accessible ? 'Accessible route' : 'Standard route';
  $('source').textContent = data.predictionSource === 'ai' ? 'AI prediction' : 'Distance-based estimate';
  $('pathways').textContent = data.pathwayIds.join(', ') || 'Not provided';
  $('empty-state').hidden = true;
  $('route-results').hidden = false;
}

$('swap').addEventListener('click', () => {
  const start = $('start').value;
  $('start').value = $('destination').value;
  $('destination').value = start;
});

$('route-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  showMessage('');

  const startId = Number($('start').value);
  const destinationId = Number($('destination').value);
  const accessible = $('accessible').checked;
  if (!startId || !destinationId) {
    showMessage('Please select both locations.');
    return;
  }
  if (startId === destinationId) {
    showMessage('Start and destination must be different.');
    return;
  }

  $('submit').disabled = true;
  $('submit').firstChild.textContent = 'Finding route… ';
  try {
    const response = await fetch('/api/route', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json'
      },
      body: JSON.stringify({startId, destinationId, accessible})
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.error?.message || `Route request failed (HTTP ${response.status}).`);
    }
    renderRoute(data, startId, destinationId);
  } catch (error) {
    $('route-results').hidden = true;
    $('empty-state').hidden = false;
    showMessage(error.message || 'Unable to calculate the route.');
  } finally {
    $('submit').disabled = locations.length === 0;
    $('submit').firstChild.textContent = 'Find my route ';
  }
});

initialize();

