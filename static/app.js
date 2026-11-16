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
    || !Array.isArray(data.directions)
    || data.directions.length === 0
    || !data.directions.every((direction, index) => (
      Number.isInteger(direction?.stepNumber)
      && direction.stepNumber === index + 1
      && typeof direction.instruction === 'string'
      && Number.isFinite(direction.distanceMeters)
      && direction.distanceMeters >= 0
    ))
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
  $('accessibility-result').textContent = data.accessible ? 'Accessible route' : 'Standard route';
  $('traffic-period').textContent = data.timePeriod || 'Not applied';
  $('source').textContent = data.predictionSource === 'ai' ? 'AI prediction' : 'Distance-based estimate';
  const directions = $('directions');
  directions.replaceChildren();
  data.directions.forEach((step) => {
    const item = document.createElement('li');
    item.className = 'direction-step';
    const instruction = document.createElement('p');
    instruction.textContent = step.instruction;
    const distance = document.createElement('span');
    distance.className = 'direction-distance';
    distance.textContent = `About ${Math.round(step.distanceMeters)} m`;
    item.append(instruction, distance);
    directions.append(item);
  });
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
  const timePeriod = $('time-period').value || null;
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
      body: JSON.stringify({startId, destinationId, accessible, timePeriod})
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

function addChatMessage(role, text) {
  const message = document.createElement('p');
  message.className = `chat-message ${role}-message`;
  message.textContent = text;
  $('chat-messages').append(message);
  $('chat-messages').scrollTop = $('chat-messages').scrollHeight;
  return message;
}

$('chat-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const input = $('chat-input');
  const message = input.value.trim();
  if (!message) return;

  addChatMessage('user', message);
  input.value = '';
  $('chat-submit').disabled = true;
  const pending = addChatMessage('assistant', 'Thinking…');
  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json'
      },
      body: JSON.stringify({message})
    });
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data?.error?.message || `Assistant request failed (HTTP ${response.status}).`);
    }
    if (typeof data.reply !== 'string') {
      throw new Error('The server returned an invalid assistant response.');
    }
    pending.textContent = data.reply;
    if (data.route) {
      renderRoute(data.route, data.route.startId, data.route.destinationId);
    }
  } catch (error) {
    pending.textContent = error.message || 'Unable to reach the campus assistant.';
  } finally {
    $('chat-submit').disabled = false;
    input.focus();
  }
});

initialize();

