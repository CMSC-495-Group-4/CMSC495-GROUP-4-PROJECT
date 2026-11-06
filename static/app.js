// Frontend contract: GET /api/locations, POST /api/route.
// If no Flask API is available, explicitly labeled demonstration data is used.
const demoLocations = [
  {id:101,name:'Science Building',accessible:true},
  {id:205,name:'University Library',accessible:true},
  {id:310,name:'Student Center',accessible:true},
  {id:420,name:'Engineering Hall',accessible:false},
  {id:530,name:'Administration Building',accessible:true}
];
const $ = (id) => document.getElementById(id);
let locations = [];
let demoMode = false;
function showMessage(message) { $('message').textContent=message; $('message').hidden=!message; }
function isValidLocation(item) { return Number.isInteger(item?.id) && typeof item.name === 'string' && typeof item.accessible === 'boolean'; }
async function initialize() {
  try {
    const response = await fetch('/api/locations', {headers:{Accept:'application/json'}});
    if (!response.ok) throw new Error('Locations API unavailable');
    const data = await response.json();
    if (!Array.isArray(data.locations) || !data.locations.every(isValidLocation)) throw new Error('Invalid locations response');
    locations = data.locations;
  } catch (_) {
    demoMode = true;
    locations = demoLocations;
  }
  $('mode-label').textContent = demoMode ? 'DEMO MODE — example locations and illustrative route estimates' : 'CONNECTED — Flask API';
  for (const id of ['start','destination']) {
    const select = $(id);
    select.replaceChildren(new Option('Select a campus location',''));
    locations.forEach((loc)=>select.add(new Option(loc.name, String(loc.id))));
  }
}
function demoRoute(startId,destinationId,accessible) {
  // This is NOT Dijkstra routing or a trained AI prediction.
  const start = locations.find(l=>l.id===startId);
  const end = locations.find(l=>l.id===destinationId);
  if (accessible && (!start.accessible || !end.accessible)) {
    const error = new Error('No accessible route was found for these demo locations.');
    error.code='ROUTE_NOT_FOUND';throw error;
  }
  const distanceMeters = 300 + Math.abs(startId-destinationId)*0.75;
  return {routeId:'demo-route-001',pathwayIds:[12,15,21],distanceMeters:Math.round(distanceMeters),accessible,estimatedMinutes:Math.round(distanceMeters/75*10)/10,predictionSource:'distance-based'};
}
function renderRoute(data,startId,destinationId) {
  if (!data || typeof data.routeId!=='string' || !Array.isArray(data.pathwayIds) || !Number.isFinite(data.distanceMeters) || data.distanceMeters<=0 || !Number.isFinite(data.estimatedMinutes) || data.estimatedMinutes<=0 || !['ai','distance-based'].includes(data.predictionSource) || typeof data.accessible!=='boolean') throw new Error('The server returned an invalid route response.');
  $('result-start').textContent=locations.find(l=>l.id===startId)?.name||String(startId);
  $('result-destination').textContent=locations.find(l=>l.id===destinationId)?.name||String(destinationId);
  $('minutes').textContent=data.estimatedMinutes.toFixed(1);
  $('distance').textContent=Math.round(data.distanceMeters).toLocaleString();
  $('route-id').textContent=data.routeId;
  $('accessibility-result').textContent=data.accessible?'Accessible route':'Standard route';
  $('source').textContent=data.predictionSource==='ai'?'AI prediction':'Distance-based estimate';
  $('pathways').textContent=data.pathwayIds.join(', ')||'Not provided';
  $('empty-state').hidden=true;$('route-results').hidden=false;
}
$('swap').addEventListener('click',()=>{const a=$('start').value;$('start').value=$('destination').value;$('destination').value=a;});
$('route-form').addEventListener('submit',async(e)=>{
  e.preventDefault();showMessage('');
  const startId=Number($('start').value),destinationId=Number($('destination').value),accessible=$('accessible').checked;
  if (!startId||!destinationId){showMessage('Please select both locations.');return;}
  if(startId===destinationId){showMessage('Start and destination must be different.');return;}
  $('submit').disabled=true;$('submit').firstChild.textContent='Finding route… ';
  try {
    let route;
    if(demoMode){route=demoRoute(startId,destinationId,accessible);}
    else {
      const response=await fetch('/api/route',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({startId,destinationId,accessible})});
      const data=await response.json().catch(()=>null);
      if(!response.ok){throw new Error(data?.error?.message||`Route request failed (HTTP ${response.status}).`);}
      route=data;
    }
    renderRoute(route,startId,destinationId);
  }catch(error){$('route-results').hidden=true;$('empty-state').hidden=false;showMessage(error.message||'Unable to calculate the route.');}
  finally{$('submit').disabled=false;$('submit').firstChild.textContent='Find my route ';}
});
initialize();
