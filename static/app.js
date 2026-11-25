'use strict';

const $ = (id) => document.getElementById(id);
let locations = [];
let routeController = null;
let routeSequence = 0;
let routeBusy = false;
let chatBusy = false;
let locationsReady = false;

function showMessage(message) {
  $('message').textContent = message;
  $('message').hidden = !message;
}

function clearRoute() {
  routeSequence += 1;
  if (routeController) routeController.abort();
  routeController = null;
  $('route-results').hidden = true;
  $('empty-state').hidden = false;
  $('directions').replaceChildren();
  document.dispatchEvent(new CustomEvent('campuspath:route-cleared'));
}

function updateRouteButton() {
  $('submit').disabled = !locationsReady || routeBusy;
  $('submit-label').textContent = routeBusy ? 'Finding route…' : 'Find my route';
}

async function fetchJSON(url, options = {}) {
  let response;
  try {
    response = await fetch(url, { ...options, headers: { Accept: 'application/json', ...options.headers } });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('Unable to connect to the campus service.');
  }
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(`The server returned an invalid response (HTTP ${response.status}).`);
  }
  if (!response.ok) throw new Error(data?.error?.message || `Request failed (HTTP ${response.status}).`);
  return data;
}

function validLocation(loc) {
  return loc && Number.isSafeInteger(loc.id) && loc.id > 0 &&
    typeof loc.name === 'string' && loc.name.trim() !== '' &&
    typeof loc.accessible === 'boolean';
}

async function initialize() {
  locationsReady = false;
  updateRouteButton();
  try {
    const data = await fetchJSON('/api/locations');
    if (!Array.isArray(data?.locations) || !data.locations.every(validLocation)) {
      throw new Error('The server returned invalid campus locations.');
    }
    const ids = data.locations.map(loc => loc.id);
    if (new Set(ids).size !== ids.length) throw new Error('Duplicate campus location IDs received.');
    locations = data.locations;
    document.dispatchEvent(new CustomEvent('campuspath:locations', {detail: {locations}}));
    for (const id of ['start', 'destination']) {
      const select = $(id);
      select.replaceChildren(new Option(locations.length ? 'Select a campus location' : 'No campus locations configured', ''));
      for (const loc of locations) select.add(new Option(loc.name, String(loc.id)));
    }
    locationsReady = locations.length > 0;
    $('mode-label').textContent = locationsReady ? 'CONNECTED — Flask API' : 'CONNECTED — no campus locations configured';
    if (!locationsReady) showMessage('Add buildings and pathways to the database to enable routing.');
  } catch (error) {
    locations = [];
    document.dispatchEvent(new CustomEvent('campuspath:locations', {detail: {locations}}));
    for (const id of ['start', 'destination']) $(id).replaceChildren(new Option('Unable to load locations', ''));
    $('mode-label').textContent = 'BACKEND UNAVAILABLE';
    showMessage(error.message || 'Unable to load campus locations.');
  } finally {
    updateRouteButton();
  }
}

function validateRoute(data) {
  if (!data || typeof data.routeId !== 'string' || !data.routeId.trim() ||
      !Array.isArray(data.directions) || data.directions.length === 0 ||
      !data.directions.every((step, i) => step && Number.isInteger(step.stepNumber) &&
        step.stepNumber === i + 1 && typeof step.instruction === 'string' &&
        step.instruction.trim() && Number.isFinite(step.distanceMeters) && step.distanceMeters >= 0) ||
      !Number.isFinite(data.distanceMeters) || data.distanceMeters < 0 ||
      !Number.isFinite(data.estimatedMinutes) || data.estimatedMinutes < 0 ||
      !['ai', 'distance-based'].includes(data.predictionSource) ||
      typeof data.accessible !== 'boolean' ||
      !(data.timePeriod == null || ['morning', 'midday', 'evening'].includes(data.timePeriod))) {
    throw new Error('The server returned an invalid route response.');
  }
}

function renderRoute(data, startId, destinationId, accessibleRequested = false) {
  validateRoute(data);
  const start = locations.find(loc => loc.id === startId);
  const destination = locations.find(loc => loc.id === destinationId);
  if (!start || !destination || startId === destinationId) throw new Error('The route contains invalid campus locations.');
  if (accessibleRequested && !data.accessible) throw new Error('The server could not confirm an accessible route.');
  $('result-start').textContent = start.name;
  $('result-destination').textContent = destination.name;
  $('minutes').textContent = data.estimatedMinutes.toFixed(1);
  $('distance').textContent = Math.round(data.distanceMeters).toLocaleString();
  $('accessibility-result').textContent = data.accessible ? 'Marked accessible in demo data' : 'Not confirmed accessible';
  $('traffic-period').textContent = data.timePeriod || 'Not applied';
  $('source').textContent = data.predictionSource === 'ai' ? 'AI prediction' : 'Distance-based demo estimate';
  const fragment = document.createDocumentFragment();
  for (const step of data.directions) {
    const li = document.createElement('li');
    li.className = 'direction-step';
    const p = document.createElement('p');
    p.textContent = step.instruction;
    const span = document.createElement('span');
    span.className = 'direction-distance';
    span.textContent = `About ${Math.round(step.distanceMeters)} m`;
    li.append(p, span);
    fragment.append(li);
  }
  $('directions').replaceChildren(fragment);
  $('empty-state').hidden = true;
  $('route-results').hidden = false;
  document.dispatchEvent(new CustomEvent('campuspath:route', {detail: {startId, destinationId}}));
}

async function handleRouteSubmit(event) {
  event.preventDefault();
  if (routeBusy || !locationsReady) return;
  showMessage('');
  const startValue = $('start').value;
  const destinationValue = $('destination').value;
  if (!startValue || !destinationValue) return showMessage('Please select both locations.');
  const startId = Number(startValue);
  const destinationId = Number(destinationValue);
  if (!locations.some(loc => loc.id === startId) || !locations.some(loc => loc.id === destinationId)) {
    return showMessage('Please select valid campus locations.');
  }
  if (startId === destinationId) return showMessage('Start and destination must be different.');
  const accessible = $('accessible').checked;
  const timePeriod = $('time-period').value || null;
  clearRoute();
  const sequence = routeSequence;
  const controller = new AbortController();
  routeController = controller;
  routeBusy = true;
  updateRouteButton();
  try {
    const data = await fetchJSON('/api/route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ startId, destinationId, accessible, timePeriod }),
      signal: controller.signal
    });
    if (sequence !== routeSequence) return;
    renderRoute(data, startId, destinationId, accessible);
  } catch (error) {
    if (sequence === routeSequence && error.name !== 'AbortError') {
      clearRoute();
      showMessage(error.message || 'Unable to calculate the route.');
    }
  } finally {
    if (routeController === controller) {
      routeController = null;
      routeBusy = false;
      updateRouteButton();
    }
  }
}

function addChatMessage(role, text, isError = false) {
  const element = document.createElement('p');
  element.className = `chat-message ${role}-message${isError ? ' chat-error' : ''}`;
  element.textContent = text;
  $('chat-messages').append(element);
  $('chat-messages').scrollTop = $('chat-messages').scrollHeight;
  return element;
}

async function handleChatSubmit(event) {
  event.preventDefault();
  if (chatBusy) return;
  const input = $('chat-input');
  const message = input.value.trim();
  if (!message) return;
  addChatMessage('user', message);
  input.value = '';
  chatBusy = true;
  $('chat-submit').disabled = true;
  const pending = addChatMessage('assistant', 'Thinking…');
  const routeSequenceAtSubmit = routeSequence;
  try {
    const data = await fetchJSON('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message })
    });
    if (typeof data?.reply !== 'string' || !data.reply.trim()) throw new Error('The server returned an invalid assistant response.');
    pending.textContent = data.reply;
    if (data.route) {
      try {
        if (!Number.isSafeInteger(data.route.startId) || !Number.isSafeInteger(data.route.destinationId)) {
          throw new Error('The assistant returned invalid location IDs.');
        }
        validateRoute(data.route);
        if (routeSequenceAtSubmit === routeSequence) {
          clearRoute();
          renderRoute(data.route, data.route.startId, data.route.destinationId);
        }
      } catch (error) {
        addChatMessage('assistant', `Route display unavailable: ${error.message}`, true);
      }
    }
  } catch (error) {
    pending.textContent = error.message || 'Unable to reach the campus assistant.';
    pending.classList.add('chat-error');
  } finally {
    chatBusy = false;
    $('chat-submit').disabled = false;
    input.focus();
  }
}

function startApplication() {
  for (const id of ['start', 'destination', 'submit', 'submit-label', 'message', 'mode-label',
    'route-form', 'swap', 'accessible', 'time-period', 'route-results', 'empty-state',
    'directions', 'result-start', 'result-destination', 'minutes', 'distance',
    'accessibility-result', 'traffic-period', 'source', 'chat-form', 'chat-input',
    'chat-submit', 'chat-messages']) {
    if (!$(id)) { console.error(`CampusPath: missing HTML element #${id}`); return; }
  }
  $('swap').addEventListener('click', () => {
    const previous = $('start').value;
    $('start').value = $('destination').value;
    $('destination').value = previous;
    clearRoute();
    showMessage('');
    document.dispatchEvent(new Event('campuspath:selection'));
  });
  for (const id of ['start', 'destination', 'accessible', 'time-period']) {
    $(id).addEventListener('change', () => { clearRoute(); showMessage(''); document.dispatchEvent(new Event('campuspath:selection')); });
  }
  $('route-form').addEventListener('submit', handleRouteSubmit);
  $('chat-form').addEventListener('submit', handleChatSubmit);
  initialize();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', startApplication, { once: true });
} else {
  startApplication();
}
