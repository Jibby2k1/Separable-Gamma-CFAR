const embedded = document.getElementById('review-data');
const data = JSON.parse(embedded.textContent);
const appRoot = document.getElementById('appRoot');
const img = document.getElementById('frameImg');
const evidenceImg = document.getElementById('evidenceImg');
const overlay = document.getElementById('overlay');
const ctx = overlay.getContext('2d');
const slider = document.getElementById('frameSlider');
const frameLabel = document.getElementById('frameLabel');
const statusEl = document.getElementById('statusText');
const selectionText = document.getElementById('selectionText');
const saveStateEl = document.getElementById('saveState');
const traceCanvas = document.getElementById('traceCanvas');
const traceCtx = traceCanvas.getContext('2d');
const cropCanvas = document.getElementById('roiCropCanvas');
const cropCtx = cropCanvas?.getContext('2d');
const roiNotes = document.getElementById('roiNotes');
const eventNotes = document.getElementById('eventNotes');
const viewerScroll = document.getElementById('viewerScroll');
const viewerWrap = document.getElementById('viewerWrap');
const datasetId = data.dataset?.dataset_id || data.video?.name || 'calcium-video';
const storeKey = `neuron-review-workbench-v3-${datasetId}`;
const traceCache = new Map();

let currentFrame = 1;
let selectedId = data.rois.length ? data.rois[0].id : null;
let selectedRoiIds = new Set(selectedId ? [String(selectedId)] : []);
let selectedEventFrame = null;
let selectedSuggestionId = data.discovery?.suggestions?.[0]?.id || null;
let playing = false;
let timer = null;
let saveTimer = null;
let serverBacked = location.protocol.startsWith('http');
let annotations = defaultAnnotations();

function defaultAnnotations() {
  return {
    version: 3,
    schema_version: 3,
    updatedAt: new Date().toISOString(),
    rois: {},
    events: {},
    suggestions: {},
    promotedRois: {},
    virtualRois: {},
    reviewStats: {
      sessionStartedAt: new Date().toISOString(),
      lastActionAt: null,
      actions: {}
    },
    settings: {
      eventThreshold: 2.4,
      kalmanGain: 0.06,
      spikeGain: 0.008,
      zoom: 3.0,
      brightness: 1,
      contrast: 1.08,
      overlayOpacity: 0.72,
      queue: 'unlabeled',
      discoveryQueue: 'all',
      evidenceMap: data.discovery?.evidenceMaps?.[0]?.id || '',
      showEvidence: false,
      showSuggestions: true,
      minArea: 0,
      minEvents: 0
    }
  };
}

function mergeAnnotations(incoming) {
  annotations = Object.assign(defaultAnnotations(), incoming || {});
  annotations.version = 3;
  annotations.schema_version = 3;
  annotations.rois = {};
  for(const [id, ann] of Object.entries(incoming?.rois || {})) annotations.rois[id] = migrateRoiAnn(ann);
  annotations.events = {};
  for(const [id, ann] of Object.entries(incoming?.events || {})) annotations.events[id] = migrateEventAnn(ann);
  annotations.suggestions = Object.assign({}, incoming?.suggestions || {});
  annotations.promotedRois = Object.assign({}, incoming?.promotedRois || {});
  annotations.virtualRois = Object.assign({}, incoming?.virtualRois || {});
  annotations.reviewStats = Object.assign(defaultAnnotations().reviewStats, incoming?.reviewStats || {});
  annotations.reviewStats.actions = Object.assign({}, incoming?.reviewStats?.actions || {});
  annotations.settings = Object.assign(defaultAnnotations().settings, incoming?.settings || {});
}

function migrateRoiAnn(ann) {
  const out = Object.assign({state:'', notes:'', deleted:false}, ann || {});
  if(!out.cell_state) out.cell_state = out.state === 'accept' ? 'accepted' : out.state === 'reject' ? 'rejected' : out.state === 'unsure' ? 'unsure' : '';
  if(out.cell_state && !out.state) out.state = out.cell_state === 'accepted' ? 'accept' : out.cell_state === 'rejected' ? 'reject' : out.cell_state === 'unsure' ? 'unsure' : '';
  out.trace_quality = out.trace_quality || '';
  out.control_ready = out.control_ready || '';
  out.artifact_class = out.artifact_class || out.artifactClass || '';
  out.identity_group = out.identity_group || '';
  out.needs_action = out.needs_action || '';
  return out;
}

function migrateEventAnn(ann) {
  const out = Object.assign({state:'', notes:''}, ann || {});
  if(!out.event_state) out.event_state = out.state === 'accept' ? 'accepted' : out.state === 'reject' ? 'rejected' : out.state === 'unsure' ? 'unsure' : '';
  if(out.event_state && !out.state) out.state = out.event_state === 'accepted' ? 'accept' : out.event_state === 'rejected' ? 'reject' : out.event_state === 'unsure' ? 'unsure' : '';
  out.event_type = out.event_type || '';
  out.timing_quality = out.timing_quality || '';
  return out;
}

async function loadAnnotations() {
  const local = localStorage.getItem(storeKey);
  if (local) mergeAnnotations(JSON.parse(local));
  if (serverBacked) {
    try {
      const res = await fetch('annotations.json', {cache: 'no-store'});
      if (res.ok) {
        mergeAnnotations(await res.json());
        setSaveState('autosave ready', 'ok');
      }
    } catch (_) {
      setSaveState('local browser save only', 'bad');
    }
  } else {
    setSaveState('static mode: export to save files', '');
  }
  applySettingsToControls();
}

function setSaveState(text, cls) {
  saveStateEl.textContent = text;
  saveStateEl.className = 'saveState ' + (cls || '');
}

function saveAnnotationsNow() {
  annotations.updatedAt = new Date().toISOString();
  localStorage.setItem(storeKey, JSON.stringify(annotations));
  if (!serverBacked) {
    setSaveState('saved in browser', 'ok');
    return;
  }
  fetch('annotations.json', {
    method: 'PUT',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(annotations, null, 2)
  }).then(res => {
    setSaveState(res.ok ? 'autosaved to annotations.json' : 'autosave failed', res.ok ? 'ok' : 'bad');
  }).catch(() => setSaveState('autosave failed', 'bad'));
}

function queueSave() {
  setSaveState('saving...', '');
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveAnnotationsNow, 220);
}

function framePath(frame){ return data.video.framePattern.replace('%03d', String(frame).padStart(3, '0')); }
function selectedRoi(){ return data.rois.find(r => r.id === selectedId) || data.rois[0] || null; }
function roiAnn(id){ return annotations.rois[id] || migrateRoiAnn({}); }
function selectedRoiIdList(){ return [...selectedRoiIds].map(id => Number(id)).filter(id => Number.isFinite(id)); }
function selectedRois(){ return selectedRoiIdList().map(id => data.rois.find(r => r.id === id)).filter(Boolean); }
function scoreValue(item, key, fallback=0){ const v = Number(item?.[key]); return Number.isFinite(v) ? v : fallback; }
function eventKey(roiId, frame){ return `${roiId}:${frame}`; }
function eventAnn(roiId, frame){ return annotations.events[eventKey(roiId, frame)] || migrateEventAnn({}); }
function suggestionAnn(id){ return annotations.suggestions[id] || {state:'', artifactClass:'', artifact_class:'', notes:''}; }
function setting(name){ return annotations.settings[name]; }
function setSetting(name, value){ annotations.settings[name] = value; queueSave(); }
function recordAction(kind){
  annotations.reviewStats = annotations.reviewStats || {sessionStartedAt: new Date().toISOString(), lastActionAt: null, actions: {}};
  annotations.reviewStats.actions = annotations.reviewStats.actions || {};
  annotations.reviewStats.actions[kind] = (annotations.reviewStats.actions[kind] || 0) + 1;
  annotations.reviewStats.lastActionAt = new Date().toISOString();
}
function threshold(){ return Number(setting('eventThreshold')); }
function kalmanGain(){ return Number(setting('kalmanGain')); }
function spikeGain(){ return Number(setting('spikeGain')); }
function minAreaFilter(){ return Number(setting('minArea')); }
function minEventsFilter(){ return Number(setting('minEvents')); }

function median(arr){ const a = [...arr].sort((x,y)=>x-y); const m = Math.floor(a.length/2); return a.length % 2 ? a[m] : 0.5*(a[m-1]+a[m]); }
function madSigma(arr, center){ return Math.max(1e-6, 1.4826 * median(arr.map(v => Math.abs(v - center)))); }
function modeledTrace(roi){
  const gain = kalmanGain(), sgain = spikeGain();
  const center = median(roi.dffTrace);
  const sigma = madSigma(roi.dffTrace, center);
  let baseline = center;
  const baselineTrace = [], eventTrace = [], zTrace = [];
  for(const v of roi.dffTrace){
    const residual = v - baseline;
    let k = gain;
    if(residual > 2.5 * sigma) k = sgain;
    if(residual < -1.0 * sigma) k = Math.min(0.18, gain * 1.8);
    baseline += k * residual;
    baselineTrace.push(baseline);
    const ev = Math.max(0, v - baseline);
    eventTrace.push(ev);
    zTrace.push(ev / sigma);
  }
  return {baselineTrace, eventTrace, zTrace, sigma};
}
function traceCacheKey(roi){
  return `${roi.id}|${Number(kalmanGain()).toFixed(4)}|${Number(spikeGain()).toFixed(4)}`;
}
function modeledTraceCached(roi){
  const key = traceCacheKey(roi);
  if(!traceCache.has(key)) traceCache.set(key, modeledTrace(roi));
  return traceCache.get(key);
}
function eventsForRoi(roi){
  if(!roi) return [];
  const model = modeledTraceCached(roi);
  const zt = model.zTrace;
  const th = threshold();
  const out = [];
  for(let i=1;i<zt.length-1;i++){
    if(zt[i] >= th && zt[i] >= zt[i-1] && zt[i] >= zt[i+1]){
      out.push({frame:i+1, z:zt[i], amplitude:model.eventTrace[i]});
    }
  }
  return out;
}
function eventFrames(roi){ return eventsForRoi(roi).map(e => e.frame); }
function eventNearFrame(roi, frame){ return eventFrames(roi).some(f => Math.abs(f - frame) <= 1); }

function roiQualityScore(roi) {
  return scoreValue(roi, 'priorityScore', roi.peakScore / Math.max(0.04, roi.noiseSigma) + eventsForRoi(roi).length * 0.4);
}
function roiUncertaintyScore(roi) {
  const ev = eventsForRoi(roi).length;
  const ann = roiAnn(roi.id);
  return (ann.state ? 0 : 20) + roi.noiseSigma * 12 + Math.abs(roi.area - 65) / 50 - ev * 0.15;
}
function roiArtifactLike(roi) {
  const ann = roiAnn(roi.id);
  const artifactClass = ann.artifact_class || ann.artifactClass || '';
  return Boolean(artifactClass && artifactClass !== 'none') || scoreValue(roi, 'artifactScore') >= 0.4;
}
function roiMergedClusterLike(roi) {
  const ann = roiAnn(roi.id);
  return ann.needs_action === 'merge_needed' || ann.artifact_class === 'merge_needed' || ann.artifactClass === 'merge_needed' || roi.area >= 180;
}
function roiWeakTraceLike(roi) {
  const ann = roiAnn(roi.id);
  return ['weak','noisy','unusable'].includes(ann.trace_quality) || scoreValue(roi, 'traceSnr', 99) < 1.5;
}
function roiNeedsEventReview(roi) {
  return eventsForRoi(roi).some(ev => !eventAnn(roi.id, ev.frame).state && !eventAnn(roi.id, ev.frame).event_state);
}
function roiStrongNeuronLike(roi) {
  const ann = roiAnn(roi.id);
  return ann.state === 'accept' || ann.cell_state === 'accepted' ||
    (roiQualityScore(roi) >= 4 && eventsForRoi(roi).length >= 1 && !roiArtifactLike(roi) && !roiWeakTraceLike(roi));
}
function roiTriageCategory(roi) {
  if(roiArtifactLike(roi)) return 'artifact_like';
  if(roiMergedClusterLike(roi)) return 'merged_cluster';
  if(roiWeakTraceLike(roi)) return 'weak_trace';
  if(roiNeedsEventReview(roi)) return 'needs_event_review';
  if(roiStrongNeuronLike(roi)) return 'strong_neuron';
  return 'standard_review';
}
function visibleRois(){
  const queue = setting('queue');
  let rows = data.rois.filter(r => r.area >= minAreaFilter() && eventsForRoi(r).length >= minEventsFilter());
  rows = rows.filter(r => {
    const ann = roiAnn(r.id);
    if (queue !== 'deleted' && ann.deleted) return false;
    if (queue === 'unlabeled') return !ann.state;
    if (queue === 'accepted') return ann.state === 'accept';
    if (queue === 'rejected') return ann.state === 'reject';
    if (queue === 'unsure') return ann.state === 'unsure';
    if (queue === 'deleted') return ann.deleted;
    if (queue === 'needsAction') return Boolean(ann.needs_action);
    if (queue === 'controlReady') return ann.control_ready === 'yes' || ann.control_ready === 'maybe';
    if (queue === 'problemTrace') return ann.trace_quality === 'noisy' || ann.trace_quality === 'unusable';
    if (queue === 'artifactRisk') return scoreValue(r, 'artifactScore') >= 0.4;
    if (queue === 'strongNeuron') return roiStrongNeuronLike(r);
    if (queue === 'artifactLike') return roiArtifactLike(r);
    if (queue === 'mergedCluster') return roiMergedClusterLike(r);
    if (queue === 'weakTrace') return roiWeakTraceLike(r);
    if (queue === 'needsEventReview') return roiNeedsEventReview(r);
    return true;
  });
  if (queue === 'highNoise') rows.sort((a,b) => b.noiseSigma - a.noiseSigma);
  else if (queue === 'highEvents') rows.sort((a,b) => eventsForRoi(b).length - eventsForRoi(a).length);
  else if (queue === 'priority') rows.sort((a,b) => roiQualityScore(b) - roiQualityScore(a));
  else if (queue === 'localCorrelation') rows.sort((a,b) => scoreValue(b, 'localCorrelationMean') - scoreValue(a, 'localCorrelationMean'));
  else if (queue === 'eventSupport') rows.sort((a,b) => scoreValue(b, 'eventSupport') - scoreValue(a, 'eventSupport'));
  else if (queue === 'traceSnr') rows.sort((a,b) => scoreValue(b, 'traceSnr') - scoreValue(a, 'traceSnr'));
  else if (queue === 'artifactRisk') rows.sort((a,b) => scoreValue(b, 'artifactScore') - scoreValue(a, 'artifactScore'));
  else if (queue === 'strongNeuron') rows.sort((a,b) => roiQualityScore(b) - roiQualityScore(a));
  else if (queue === 'artifactLike') rows.sort((a,b) => scoreValue(b, 'artifactScore') - scoreValue(a, 'artifactScore'));
  else if (queue === 'mergedCluster') rows.sort((a,b) => b.area - a.area);
  else if (queue === 'weakTrace') rows.sort((a,b) => scoreValue(a, 'traceSnr', 99) - scoreValue(b, 'traceSnr', 99));
  else if (queue === 'needsEventReview') rows.sort((a,b) => eventsForRoi(b).length - eventsForRoi(a).length);
  else if (queue === 'uncertain') rows.sort((a,b) => roiUncertaintyScore(b) - roiUncertaintyScore(a));
  else rows.sort((a,b) => roiQualityScore(b) - roiQualityScore(a));
  return rows;
}

function selectedSuggestion(){
  const suggestions = data.discovery?.suggestions || [];
  return suggestions.find(s => s.id === selectedSuggestionId) || suggestions[0] || null;
}
function visibleSuggestions(){
  const queue = setting('discoveryQueue') || 'all';
  let rows = [...(data.discovery?.suggestions || [])];
  rows = rows.filter(s => {
    const ann = suggestionAnn(s.id);
    if (queue === 'unlabeled') return !ann.state;
    if (queue === 'promoted') return ann.state === 'promoted' || Boolean(annotations.promotedRois[s.id]);
    if (queue === 'missed') return ann.state === 'missed';
    if (queue === 'artifact') return ann.state === 'artifact';
    if (queue === 'artifactSuspects') return s.artifactCue && s.artifactCue !== 'none';
    return true;
  });
  rows.sort((a,b) => scoreValue(b, 'priorityScore', b.discoveryScore || 0) - scoreValue(a, 'priorityScore', a.discoveryScore || 0));
  return rows;
}

function applySettingsToControls() {
  const pairs = [
    ['eventThreshold', 'eventThresholdLabel', 1],
    ['kalmanGain', 'kalmanGainLabel', 3],
    ['spikeGain', 'spikeGainLabel', 3],
    ['zoom', 'zoomLabel', 2],
    ['brightness', 'brightnessLabel', 2],
    ['contrast', 'contrastLabel', 2],
    ['overlayOpacity', 'overlayOpacityLabel', 2],
    ['minArea', 'minAreaLabel', 0],
    ['minEvents', 'minEventsLabel', 0]
  ];
  for (const [id, label, digits] of pairs) {
    const el = document.getElementById(id);
    if (!el) continue;
    el.value = setting(id);
    document.getElementById(label).textContent = Number(setting(id)).toFixed(digits);
  }
  document.getElementById('queueSelect').value = setting('queue');
  document.getElementById('discoveryQueueSelect').value = setting('discoveryQueue') || 'all';
  document.getElementById('evidenceSelect').value = setting('evidenceMap') || '';
  document.getElementById('showEvidence').checked = Boolean(setting('showEvidence'));
  document.getElementById('showSuggestions').checked = Boolean(setting('showSuggestions'));
  applyDisplaySettings();
}

function populateEvidenceSelect(){
  const select = document.getElementById('evidenceSelect');
  if(!select) return;
  select.innerHTML = '';
  for(const m of data.discovery?.evidenceMaps || []){
    const opt = document.createElement('option');
    opt.value = m.id;
    opt.textContent = m.label;
    select.appendChild(opt);
  }
}

function applyDisplaySettings() {
  img.style.width = `${data.video.width * Number(setting('zoom'))}px`;
  img.style.filter = `brightness(${setting('brightness')}) contrast(${setting('contrast')})`;
  evidenceImg.style.width = img.style.width;
  const evidenceMap = (data.discovery?.evidenceMaps || []).find(m => m.id === setting('evidenceMap'));
  evidenceImg.src = evidenceMap ? evidenceMap.file : '';
  evidenceImg.style.opacity = setting('showEvidence') ? '0.58' : '0';
  ctx.globalAlpha = Number(setting('overlayOpacity'));
  resizeOverlay();
}

function resizeOverlay(){
  const rect = img.getBoundingClientRect();
  overlay.width = data.video.width;
  overlay.height = data.video.height;
  overlay.style.width = rect.width + 'px';
  overlay.style.height = rect.height + 'px';
  drawOverlay();
}

function drawOverlay(){
  ctx.clearRect(0,0,overlay.width,overlay.height);
  const showRois = document.getElementById('showRois').checked;
  const showLabels = document.getElementById('showLabels').checked;
  const showEvents = document.getElementById('showEvents').checked;
  const showSuggestions = document.getElementById('showSuggestions').checked;
  if(!showRois && !showSuggestions) return;
  const opacity = Number(setting('overlayOpacity'));
  if(showRois) for(const roi of visibleRois()){
    const ann = roiAnn(roi.id);
    const isSel = roi.id === selectedId;
    const isMultiSel = selectedRoiIds.has(String(roi.id));
    const isEvent = showEvents && eventNearFrame(roi, currentFrame);
    let color = ann.state === 'accept' ? '#16a34a' : ann.state === 'reject' ? '#dc2626' : ann.state === 'unsure' ? '#9333ea' : '#38bdf8';
    if(isEvent) color = '#facc15';
    ctx.globalAlpha = isSel || isMultiSel ? 0.96 : opacity;
    ctx.fillStyle = color;
    for(const p of roi.points){ ctx.fillRect(p[0], p[1], 1, 1); }
    ctx.globalAlpha = 1;
    ctx.strokeStyle = isSel ? '#ffffff' : isMultiSel ? '#22c55e' : color;
    ctx.lineWidth = isSel || isMultiSel ? 2 : 1;
    const r = Math.max(4, Math.sqrt(roi.area / Math.PI) + 2);
    ctx.beginPath(); ctx.arc(roi.centroidX, roi.centroidY, r, 0, Math.PI*2); ctx.stroke();
    if(showLabels){
      ctx.font = '10px Arial';
      ctx.fillStyle = '#ffffff';
      ctx.strokeStyle = '#111827';
      ctx.lineWidth = 3;
      ctx.strokeText(String(roi.id), roi.centroidX + 5, roi.centroidY - 5);
      ctx.fillText(String(roi.id), roi.centroidX + 5, roi.centroidY - 5);
    }
  }
  if(showSuggestions){
    for(const s of visibleSuggestions()){
      const ann = suggestionAnn(s.id);
      const isSel = s.id === selectedSuggestionId;
      let color = ann.state === 'promoted' || annotations.promotedRois[s.id] ? '#16a34a' :
        ann.state === 'artifact' ? '#dc2626' :
        ann.state === 'missed' ? '#facc15' :
        ann.state === 'unsure' ? '#9333ea' : '#fb7185';
      ctx.globalAlpha = isSel ? 0.96 : Math.max(0.38, opacity * 0.82);
      ctx.fillStyle = color;
      for(const p of s.points || []) ctx.fillRect(p[0], p[1], 1, 1);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = isSel ? '#ffffff' : color;
      ctx.lineWidth = isSel ? 2 : 1;
      const r = Math.max(5, Math.sqrt((s.area || 20) / Math.PI) + 3);
      ctx.beginPath(); ctx.arc(s.centroidX, s.centroidY, r, 0, Math.PI*2); ctx.stroke();
      if(showLabels){
        ctx.font = '10px Arial';
        ctx.fillStyle = '#ffffff';
        ctx.strokeStyle = '#111827';
        ctx.lineWidth = 3;
        ctx.strokeText(String(s.id), s.centroidX + 5, s.centroidY - 5);
        ctx.fillText(String(s.id), s.centroidX + 5, s.centroidY - 5);
      }
    }
  }
}

function drawTrace(){
  const roi = selectedRoi();
  const w = traceCanvas.width, h = traceCanvas.height;
  traceCtx.clearRect(0,0,w,h);
  traceCtx.fillStyle = '#fff'; traceCtx.fillRect(0,0,w,h);
  if(!roi) return;
  const pad = 30;
  const model = modeledTraceCached(roi);
  const zScaled = model.zTrace.map(v => v * 0.05);
  const vals = [roi.dffTrace, model.baselineTrace, zScaled].flat();
  let lo = Math.min(...vals), hi = Math.max(...vals);
  if(hi - lo < 1e-6){ hi = lo + 1; }
  function x(i){ return pad + i * (w - 2*pad) / (data.video.frames - 1); }
  function y(v){ return h - pad - (v - lo) * (h - 2*pad) / (hi - lo); }
  traceCtx.strokeStyle = '#e2e8f0'; traceCtx.lineWidth = 1;
  for(let k=0;k<5;k++){ const yy = pad + k*(h-2*pad)/4; traceCtx.beginPath(); traceCtx.moveTo(pad,yy); traceCtx.lineTo(w-pad,yy); traceCtx.stroke(); }
  const drawLine = (arr, color, width=1.6) => {
    traceCtx.strokeStyle=color; traceCtx.lineWidth=width; traceCtx.beginPath();
    arr.forEach((v,i)=>{ if(i===0) traceCtx.moveTo(x(i),y(v)); else traceCtx.lineTo(x(i),y(v)); });
    traceCtx.stroke();
  };
  drawLine(roi.dffTrace, '#2563eb');
  drawLine(model.baselineTrace, '#64748b');
  drawLine(zScaled, '#f59e0b');
  traceCtx.strokeStyle = '#ef4444'; traceCtx.lineWidth = 1;
  const xf = x(currentFrame - 1); traceCtx.beginPath(); traceCtx.moveTo(xf,pad); traceCtx.lineTo(xf,h-pad); traceCtx.stroke();
  for(const ev of eventsForRoi(roi)){
    const ann = eventAnn(roi.id, ev.frame);
    traceCtx.fillStyle = ann.state === 'accept' ? '#16a34a' : ann.state === 'reject' ? '#dc2626' : ann.state === 'unsure' ? '#9333ea' : '#facc15';
    traceCtx.beginPath(); traceCtx.arc(x(ev.frame-1), pad + 8, ev.frame === selectedEventFrame ? 5 : 3, 0, Math.PI*2); traceCtx.fill();
  }
  traceCanvas.setAttribute('aria-label', `ROI ${roi.id} trace with ${eventsForRoi(roi).length} called events. Current frame ${currentFrame}.`);
  traceCtx.fillStyle = '#0f172a'; traceCtx.font = '13px Arial';
  traceCtx.fillText(`ROI ${roi.id} | area ${roi.area} | noise sigma ${model.sigma.toFixed(5)} | events ${eventsForRoi(roi).length}`, pad, 18);
}

function roiCropBounds(roi, pad=18){
  if(!roi) return null;
  const bbox = roi.bbox || [
    Math.floor(roi.centroidX - 8), Math.floor(roi.centroidY - 8),
    Math.ceil(roi.centroidX + 8), Math.ceil(roi.centroidY + 8)
  ];
  const x0 = Math.max(0, Math.floor(bbox[0] - pad));
  const y0 = Math.max(0, Math.floor(bbox[1] - pad));
  const x1 = Math.min(data.video.width - 1, Math.ceil(bbox[2] + pad));
  const y1 = Math.min(data.video.height - 1, Math.ceil(bbox[3] + pad));
  return {x0, y0, x1, y1, w: Math.max(1, x1 - x0 + 1), h: Math.max(1, y1 - y0 + 1)};
}

function drawCrop(){
  if(!cropCanvas || !cropCtx) return;
  const roi = selectedRoi();
  cropCtx.clearRect(0,0,cropCanvas.width,cropCanvas.height);
  cropCtx.fillStyle = '#08111f';
  cropCtx.fillRect(0,0,cropCanvas.width,cropCanvas.height);
  if(!roi || !img.complete || !img.naturalWidth) return;
  const b = roiCropBounds(roi);
  const scale = Math.min(cropCanvas.width / b.w, cropCanvas.height / b.h);
  const dw = b.w * scale, dh = b.h * scale;
  const ox = (cropCanvas.width - dw) / 2, oy = (cropCanvas.height - dh) / 2;
  cropCtx.imageSmoothingEnabled = false;
  cropCtx.drawImage(img, b.x0, b.y0, b.w, b.h, ox, oy, dw, dh);
  cropCtx.fillStyle = 'rgba(56, 189, 248, 0.72)';
  for(const p of roi.points || []){
    const x = ox + (p[0] - b.x0) * scale;
    const y = oy + (p[1] - b.y0) * scale;
    cropCtx.fillRect(x, y, Math.max(1, scale), Math.max(1, scale));
  }
  cropCtx.strokeStyle = selectedEventFrame && eventNearFrame(roi, currentFrame) ? '#facc15' : '#ffffff';
  cropCtx.lineWidth = 2;
  cropCtx.beginPath();
  cropCtx.arc(ox + (roi.centroidX - b.x0) * scale, oy + (roi.centroidY - b.y0) * scale, Math.max(5, Math.sqrt(roi.area / Math.PI) * scale), 0, Math.PI * 2);
  cropCtx.stroke();
  cropCanvas.setAttribute('aria-label', `Crop around ROI ${roi.id}, area ${roi.area} pixels, centered at x ${Number(roi.centroidX).toFixed(1)}, y ${Number(roi.centroidY).toFixed(1)}.`);
}

function renderRoiContext(){
  const roi = selectedRoi();
  const card = document.getElementById('roiEvidenceCard');
  const strip = document.getElementById('eventFilmstrip');
  drawCrop();
  if(!roi){
    if(card) card.innerHTML = '';
    if(strip) strip.innerHTML = '';
    return;
  }
  const events = eventsForRoi(roi);
  const diameterPx = 2 * Math.sqrt(roi.area / Math.PI);
  const pixelSize = Number(data.dataset?.pixel_size_microns);
  const diameterUm = Number.isFinite(pixelSize) ? `${(diameterPx * pixelSize).toFixed(1)} um` : 'n/a';
  const warnings = [];
  if(scoreValue(roi, 'artifactScore') >= 0.45) warnings.push('artifact-risk');
  if(scoreValue(roi, 'backgroundCorrelation') >= 0.55) warnings.push('background-correlated');
  if(scoreValue(roi, 'localCorrelationMean') > 0 && scoreValue(roi, 'localCorrelationMean') < 0.40) warnings.push('low local correlation');
  if(scoreValue(roi, 'eventSupport') > 0 && scoreValue(roi, 'eventSupport') < 0.35) warnings.push('weak event support');
  const warningHtml = warnings.length ? `<tr><td>warnings</td><td>${warnings.map(w => `<span class="riskPill">${w}</span>`).join(' ')}</td></tr>` : '';
  if(card) card.innerHTML = `
    <table class="smallTable">
      <tr><th>Field</th><th>Value</th></tr>
      <tr><td>ROI</td><td>${roi.id}</td></tr>
      <tr><td>priority score</td><td>${fmt(scoreValue(roi, 'priorityScore', null), 3)}</td></tr>
      <tr><td>area</td><td>${roi.area} px</td></tr>
      <tr><td>equiv. diameter</td><td>${diameterPx.toFixed(1)} px / ${diameterUm}</td></tr>
      <tr><td>peak score</td><td>${Number(roi.peakScore).toFixed(2)}</td></tr>
      <tr><td>noise sigma</td><td>${Number(roi.noiseSigma).toFixed(5)}</td></tr>
      <tr><td>trace SNR</td><td>${fmt(scoreValue(roi, 'traceSnr', null), 2)}</td></tr>
      <tr><td>local correlation</td><td>${fmt(scoreValue(roi, 'localCorrelationMean', null), 3)}</td></tr>
      <tr><td>background corr.</td><td>${fmt(scoreValue(roi, 'backgroundCorrelation', null), 3)}</td></tr>
      <tr><td>event support</td><td>${fmt(scoreValue(roi, 'eventSupport', null), 3)}</td></tr>
      <tr><td>artifact risk</td><td>${fmt(scoreValue(roi, 'artifactScore', null), 3)}</td></tr>
      <tr><td>events</td><td>${events.length}</td></tr>
      ${warningHtml}
    </table>`;
  if(!strip) return;
  const center = selectedEventFrame || events[0]?.frame || currentFrame;
  const b = roiCropBounds(roi, 24);
  const thumb = 52;
  const scale = thumb / Math.max(b.w, b.h);
  strip.innerHTML = '';
  for(let frame = Math.max(1, center - 5); frame <= Math.min(data.video.frames, center + 10); frame++){
    const cell = document.createElement('button');
    cell.type = 'button';
    cell.className = 'filmFrame' + (frame === currentFrame ? ' active' : '');
    cell.setAttribute('aria-label', `Show frame ${frame} near ROI ${roi.id}`);
    if(frame === currentFrame) cell.setAttribute('aria-current', 'true');
    cell.style.backgroundImage = `url("${framePath(frame)}")`;
    cell.style.backgroundSize = `${data.video.width * scale}px ${data.video.height * scale}px`;
    cell.style.backgroundPosition = `${-b.x0 * scale}px ${-b.y0 * scale}px`;
    cell.innerHTML = `<span>${frame}</span>`;
    cell.onclick = () => setFrame(frame);
    strip.appendChild(cell);
  }
}

function setFrame(frame){
  currentFrame = Math.max(1, Math.min(data.video.frames, frame));
  slider.value = currentFrame;
  frameLabel.textContent = currentFrame;
  img.src = framePath(currentFrame);
  statusEl.textContent = `Frame ${currentFrame} / ${data.video.frames}`;
  const roi = selectedRoi();
  selectionText.textContent = roi ? `ROI ${roi.id}${selectedEventFrame ? `, event f${selectedEventFrame}` : ''}` : '';
  drawTrace();
  renderRoiContext();
}

function selectRoi(id, additive=false){
  selectedId = id;
  if(additive) {
    const key = String(id);
    if(selectedRoiIds.has(key)) selectedRoiIds.delete(key);
    else selectedRoiIds.add(key);
    if(!selectedRoiIds.size) selectedRoiIds.add(key);
  } else {
    selectedRoiIds = new Set([String(id)]);
  }
  const roi = selectedRoi();
  selectedEventFrame = eventsForRoi(roi)[0]?.frame || null;
  roiNotes.value = roiAnn(id).notes || '';
  eventNotes.value = selectedEventFrame ? eventAnn(id, selectedEventFrame).notes || '' : '';
  setFrame(selectedEventFrame || currentFrame);
  renderAll();
}

function selectSuggestion(id){
  selectedSuggestionId = id;
  const s = selectedSuggestion();
  document.getElementById('suggestionNotes').value = s ? suggestionAnn(s.id).notes || '' : '';
  document.getElementById('artifactClass').value = s ? suggestionAnn(s.id).artifact_class || suggestionAnn(s.id).artifactClass || '' : '';
  if(s) {
    selectedEventFrame = null;
    currentFrame = Math.max(1, Math.min(data.video.frames, currentFrame));
    selectionText.textContent = `Suggestion ${s.id}`;
  }
  renderAll();
}

function renderRoiList(){
  const root = document.getElementById('roiList');
  root.innerHTML = '';
  const rows = visibleRois();
  document.getElementById('visibleCount').textContent = rows.length;
  const multiCount = document.getElementById('multiSelectCount');
  if(multiCount) multiCount.textContent = String(selectedRoiIds.size);
  for(const roi of rows){
    const ann = roiAnn(roi.id);
    const row = document.createElement('div');
    row.className = 'roiRow' + (roi.id === selectedId ? ' sel' : '') + (selectedRoiIds.has(String(roi.id)) ? ' multiSel' : '') + (ann.deleted ? ' deleted' : '');
    const state = ann.deleted ? 'deleted' : ann.state || 'new';
    const triage = roiTriageCategory(roi).replace(/_/g, ' ');
    row.innerHTML = `<b>#${roi.id}</b><span>${eventsForRoi(roi).length} events, area ${roi.area}, priority ${fmt(scoreValue(roi, 'priorityScore', null), 2)} <i class="triageChip">${triage}</i></span><span class="badge ${ann.state || ''}">${state}</span>`;
    row.onclick = e => selectRoi(roi.id, e.shiftKey || e.ctrlKey || e.metaKey);
    root.appendChild(row);
  }
}

function renderEventList(){
  const roi = selectedRoi();
  const root = document.getElementById('eventList');
  root.innerHTML = '';
  if(!roi) return;
  for(const ev of eventsForRoi(roi)){
    const ann = eventAnn(roi.id, ev.frame);
    const row = document.createElement('div');
    row.className = 'eventRow' + (ev.frame === selectedEventFrame ? ' sel' : '');
    row.innerHTML = `<b>f${ev.frame}</b><span>z ${ev.z.toFixed(2)}, amp ${ev.amplitude.toFixed(4)}</span><span class="badge ${ann.state || ''}">${ann.state || 'new'}</span>`;
    row.onclick = () => { selectedEventFrame = ev.frame; eventNotes.value = eventAnn(roi.id, ev.frame).notes || ''; setFrame(ev.frame); renderAll(); };
    root.appendChild(row);
  }
}

function renderSuggestionList(){
  const root = document.getElementById('suggestionList');
  if(!root) return;
  root.innerHTML = '';
  const rows = visibleSuggestions();
  document.getElementById('suggestionVisibleCount').textContent = rows.length;
  for(const s of rows){
    const ann = suggestionAnn(s.id);
    const row = document.createElement('div');
    row.className = 'suggestionRow' + (s.id === selectedSuggestionId ? ' sel' : '');
    const state = annotations.promotedRois[s.id] ? 'promoted' : ann.state || 'new';
    const cue = s.artifactCue && s.artifactCue !== 'none' ? `, ${s.artifactCue}` : '';
    row.innerHTML = `<b>${s.id}</b><span>priority ${fmt(scoreValue(s, 'priorityScore', s.discoveryScore), 3)}, area ${s.area}${cue}</span><span class="badge ${ann.state || ''}">${state}</span>`;
    row.onclick = () => selectSuggestion(s.id);
    root.appendChild(row);
  }
}

function updateCounts(){
  const allEvents = data.rois.reduce((sum, r) => sum + eventsForRoi(r).length, 0);
  let acc = 0, rej = 0, unsure = 0, eventAccepted = 0;
  let promoted = 0, missed = 0, artifacts = 0;
  for(const r of data.rois){
    const st = roiAnn(r.id).state;
    if(st === 'accept') acc++;
    if(st === 'reject') rej++;
    if(st === 'unsure') unsure++;
    for(const ev of eventsForRoi(r)) if(eventAnn(r.id, ev.frame).state === 'accept') eventAccepted++;
  }
  for(const s of data.discovery?.suggestions || []){
    const ann = suggestionAnn(s.id);
    if(annotations.promotedRois[s.id] || ann.state === 'promoted') promoted++;
    if(ann.state === 'missed') missed++;
    if(ann.state === 'artifact') artifacts++;
  }
  document.getElementById('roiCount').textContent = data.rois.length;
  document.getElementById('eventCount').textContent = allEvents;
  document.getElementById('acceptedCount').textContent = acc;
  document.getElementById('rejectedCount').textContent = rej;
  document.getElementById('unsureCount').textContent = unsure;
  document.getElementById('eventAcceptedCount').textContent = eventAccepted;
  document.getElementById('suggestionCount').textContent = data.discovery?.suggestions?.length || 0;
  document.getElementById('promotedCount').textContent = promoted;
  document.getElementById('missedCount').textContent = missed;
  document.getElementById('artifactCount').textContent = artifacts;
}

function setRoiState(state){
  const roi = selectedRoi(); if(!roi) return;
  const cellState = state === 'accept' ? 'accepted' : state === 'reject' ? 'rejected' : state === 'unsure' ? 'unsure' : '';
  annotations.rois[roi.id] = Object.assign(roiAnn(roi.id), {state, cell_state: cellState});
  recordAction(`roi_${state || 'clear'}`);
  queueSave();
  renderAll();
}

function applyToSelectedRois(fields, actionName){
  const ids = selectedRoiIdList();
  if(!ids.length) return;
  for(const id of ids){
    annotations.rois[id] = Object.assign(roiAnn(id), fields);
  }
  recordAction(actionName || 'roi_bulk_edit');
  queueSave();
  renderAll();
}

function assignSelectedIdentity(){
  const ids = selectedRoiIdList();
  if(ids.length < 2) return;
  const value = document.getElementById('bulkIdentityGroup').value.trim() || `group_${ids.join('_')}`;
  applyToSelectedRois({identity_group: value, needs_action: 'merge_needed'}, 'roi_bulk_identity_group');
}

function markSelectedAction(){
  const value = document.getElementById('bulkNeedsAction').value;
  if(!value) return;
  applyToSelectedRois({needs_action: value}, 'roi_bulk_needs_action');
}

function createVirtualMerge(){
  const rois = selectedRois();
  if(rois.length < 2) return;
  const ids = rois.map(r => r.id);
  const pixels = new Map();
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity, sumX = 0, sumY = 0;
  for(const roi of rois){
    for(const p of roi.points || []){
      const key = `${p[0]},${p[1]}`;
      if(!pixels.has(key)) {
        pixels.set(key, p);
        sumX += p[0];
        sumY += p[1];
        minX = Math.min(minX, p[0]);
        minY = Math.min(minY, p[1]);
        maxX = Math.max(maxX, p[0]);
        maxY = Math.max(maxY, p[1]);
      }
    }
  }
  const points = [...pixels.values()];
  const id = `VM_${ids.join('_')}`;
  annotations.virtualRois[id] = {
    id,
    roi_kind: 'virtual_merge',
    source_roi_ids: ids,
    identity_group: document.getElementById('bulkIdentityGroup').value.trim() || `group_${ids.join('_')}`,
    centroidX: points.length ? Number((sumX / points.length).toFixed(1)) : null,
    centroidY: points.length ? Number((sumY / points.length).toFixed(1)) : null,
    area: points.length,
    bbox: [minX, minY, maxX, maxY],
    points,
    cell_state: 'unsure',
    trace_quality: '',
    control_ready: '',
    artifact_class: '',
    notes: ''
  };
  applyToSelectedRois({identity_group: annotations.virtualRois[id].identity_group, needs_action: 'merge_needed'}, 'roi_virtual_merge');
}

function clearMultiSelection(){
  if(selectedId) selectedRoiIds = new Set([String(selectedId)]);
  renderAll();
}

function toggleDeleted(){
  const roi = selectedRoi(); if(!roi) return;
  const ann = Object.assign(roiAnn(roi.id), {deleted: !roiAnn(roi.id).deleted});
  annotations.rois[roi.id] = ann;
  recordAction(ann.deleted ? 'roi_hide' : 'roi_restore');
  queueSave();
  renderAll();
}
function setEventState(state){
  const roi = selectedRoi(); if(!roi || !selectedEventFrame) return;
  const eventState = state === 'accept' ? 'accepted' : state === 'reject' ? 'rejected' : state === 'unsure' ? 'unsure' : '';
  annotations.events[eventKey(roi.id, selectedEventFrame)] = Object.assign(eventAnn(roi.id, selectedEventFrame), {state, event_state: eventState});
  recordAction(`event_${state || 'clear'}`);
  queueSave();
  renderAll();
}

function setSuggestionState(state){
  const s = selectedSuggestion(); if(!s) return;
  annotations.suggestions[s.id] = Object.assign(suggestionAnn(s.id), {state});
  recordAction(`suggestion_${state || 'clear'}`);
  queueSave();
  renderAll();
}
function promoteSuggestion(){
  const s = selectedSuggestion(); if(!s) return;
  annotations.suggestions[s.id] = Object.assign(suggestionAnn(s.id), {state:'promoted'});
  annotations.promotedRois[s.id] = {
    sourceSuggestion: s.id,
    provenance: s.provenance || 'discovery',
    centroidX: s.centroidX,
    centroidY: s.centroidY,
    area: s.area,
    bbox: s.bbox,
    points: s.points || [],
    promotedAt: new Date().toISOString()
  };
  recordAction('suggestion_promote');
  queueSave();
  renderAll();
}

function renderButtons(){
  const roi = selectedRoi();
  const ann = roi ? roiAnn(roi.id) : {};
  for (const [id, state] of [['acceptBtn','accept'],['rejectBtn','reject'],['unsureBtn','unsure']]) {
    document.getElementById(id).classList.toggle('active', ann.state === state);
  }
  document.getElementById('deleteBtn').textContent = ann.deleted ? 'Restore ROI' : 'Hide ROI';
  const eann = roi && selectedEventFrame ? eventAnn(roi.id, selectedEventFrame) : {};
  for (const [id, state] of [['eventAcceptBtn','accept'],['eventRejectBtn','reject'],['eventUnsureBtn','unsure']]) {
    document.getElementById(id).classList.toggle('active', eann.state === state);
  }
  for (const [id, field] of [['traceQuality','trace_quality'],['controlReady','control_ready'],['roiArtifactClass','artifact_class'],['needsAction','needs_action']]) {
    const el = document.getElementById(id);
    if(el) el.value = ann[field] || '';
  }
  const identity = document.getElementById('identityGroup');
  if(identity) identity.value = ann.identity_group || '';
  for (const [id, field] of [['eventType','event_type'],['timingQuality','timing_quality']]) {
    const el = document.getElementById(id);
    if(el) el.value = eann[field] || '';
  }
  const sann = selectedSuggestion() ? suggestionAnn(selectedSuggestion().id) : {};
  for (const [id, state] of [['suggestionMissedBtn','missed'],['suggestionArtifactBtn','artifact'],['suggestionUnsureBtn','unsure']]) {
    document.getElementById(id).classList.toggle('active', sann.state === state);
  }
}

function renderParams(){
  const rows = Object.entries(data.parameters).map(([k,v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');
  document.getElementById('paramTable').innerHTML = '<tr><th>Parameter</th><th>Value</th></tr>' + rows;
}

function renderAll(){
  updateCounts();
  renderButtons();
  renderRoiList();
  renderEventList();
  renderSuggestionList();
  drawOverlay();
  drawTrace();
  renderRoiContext();
}

function exportRows(type) {
  const newline = String.fromCharCode(10);
  let rows = [];
  if (type === 'roi') {
    rows.push('roi_id\troi_kind\tsource_roi_ids\tstate\tcell_state\ttrace_quality\tcontrol_ready\tartifact_class\tidentity_group\tneeds_action\tdeleted\tnotes\tcentroid_x\tcentroid_y\tarea\tpeak_score\tevent_count\tnoise_sigma\tpriority_score\tlocal_correlation_mean\tbackground_correlation\ttrace_snr\tevent_support\tartifact_score');
    for(const roi of data.rois){
      const ann = roiAnn(roi.id);
      const notes = (ann.notes || '').split(String.fromCharCode(9)).join(' ').split(newline).join(' ');
      rows.push([roi.id, 'source', '', ann.state || '', ann.cell_state || '', ann.trace_quality || '', ann.control_ready || '', ann.artifact_class || '', ann.identity_group || '', ann.needs_action || '', ann.deleted ? 1 : 0, notes, roi.centroidX, roi.centroidY, roi.area, roi.peakScore, eventsForRoi(roi).length, roi.noiseSigma, roi.priorityScore || '', roi.localCorrelationMean || '', roi.backgroundCorrelation || '', roi.traceSnr || '', roi.eventSupport || '', roi.artifactScore || ''].join('\t'));
    }
    for(const virtual of Object.values(annotations.virtualRois || {})){
      const notes = (virtual.notes || '').split(String.fromCharCode(9)).join(' ').split(newline).join(' ');
      rows.push([virtual.id, virtual.roi_kind || 'virtual', (virtual.source_roi_ids || []).join(','), '', virtual.cell_state || '', virtual.trace_quality || '', virtual.control_ready || '', virtual.artifact_class || '', virtual.identity_group || '', 'merge_needed', 0, notes, virtual.centroidX || '', virtual.centroidY || '', virtual.area || '', '', '', '', '', '', '', '', '', ''].join('\t'));
    }
  } else if (type === 'event') {
    rows.push('roi_id\tframe\tstate\tevent_state\tevent_type\ttiming_quality\tnotes\tz\tamplitude\troi_state');
    for(const roi of data.rois){
      for(const ev of eventsForRoi(roi)){
        const ann = eventAnn(roi.id, ev.frame);
        const notes = (ann.notes || '').split(String.fromCharCode(9)).join(' ').split(newline).join(' ');
        rows.push([roi.id, ev.frame, ann.state || '', ann.event_state || '', ann.event_type || '', ann.timing_quality || '', notes, ev.z.toFixed(4), ev.amplitude.toFixed(6), roiAnn(roi.id).state || ''].join('\t'));
      }
    }
  } else {
    rows.push('suggestion_id\tstate\tartifact_class\tnotes\tpromoted\tcentroid_x\tcentroid_y\tarea\tdiscovery_score\tpriority_score\tlocal_correlation_mean\tevent_support\tartifact_score\tmax_z\tactive_frames\tartifact_cue\tprovenance');
    for(const s of data.discovery?.suggestions || []){
      const ann = suggestionAnn(s.id);
      const notes = (ann.notes || '').split(String.fromCharCode(9)).join(' ').split(newline).join(' ');
      rows.push([s.id, ann.state || '', ann.artifact_class || ann.artifactClass || '', notes, annotations.promotedRois[s.id] ? 1 : 0, s.centroidX, s.centroidY, s.area, s.discoveryScore, s.priorityScore || '', s.localCorrelationMean || '', s.eventSupport || '', s.artifactScore || '', s.maxZ, s.activeFrames, s.artifactCue || '', s.provenance || ''].join('\t'));
    }
  }
  const blob = new Blob([rows.join(newline) + newline], {type:'text/tab-separated-values'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = type === 'roi' ? 'neuron_roi_annotations.tsv' : type === 'event' ? 'neuron_event_annotations.tsv' : 'neuron_discovery_suggestions.tsv';
  a.click();
  URL.revokeObjectURL(a.href);
}

function exportJson() {
  annotations.updatedAt = new Date().toISOString();
  const blob = new Blob([JSON.stringify(annotations, null, 2) + String.fromCharCode(10)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'annotations_v3.json';
  a.click();
  URL.revokeObjectURL(a.href);
}

function nextRoi(delta){
  const rows = visibleRois();
  if(!rows.length) return;
  const idx = Math.max(0, rows.findIndex(r => r.id === selectedId));
  const next = rows[(idx + delta + rows.length) % rows.length];
  selectRoi(next.id);
}
function nextEvent(delta){
  const roi = selectedRoi();
  if(!roi) return;
  const events = eventsForRoi(roi);
  if(!events.length) return;
  const idx = Math.max(0, events.findIndex(e => e.frame === selectedEventFrame));
  selectedEventFrame = events[(idx + delta + events.length) % events.length].frame;
  eventNotes.value = eventAnn(roi.id, selectedEventFrame).notes || '';
  setFrame(selectedEventFrame);
  renderAll();
}
function togglePlay(){
  playing = !playing;
  document.getElementById('playBtn').textContent = playing ? 'Pause' : 'Play';
  if(playing) timer = setInterval(() => setFrame(currentFrame >= data.video.frames ? 1 : currentFrame + 1), 120);
  else clearInterval(timer);
}
function fitWidth(){
  const width = Math.max(1, viewerScroll.clientWidth - 34);
  setSetting('zoom', Math.max(0.5, width / data.video.width));
  applySettingsToControls();
}

function initControls(){
  slider.max = data.video.frames;
  slider.oninput = () => setFrame(Number(slider.value));
  document.getElementById('playBtn').onclick = togglePlay;
  document.getElementById('fitBtn').onclick = fitWidth;
  document.getElementById('fullscreenBtn').onclick = () => viewerScroll.requestFullscreen?.();
  document.getElementById('eventWindowPrevBtn').onclick = () => nextEvent(-1);
  document.getElementById('eventWindowNextBtn').onclick = () => nextEvent(1);
  document.getElementById('archRunA').onchange = renderRunComparison;
  document.getElementById('archRunB').onchange = renderRunComparison;
  document.getElementById('archCompareModeBtn').onclick = () => setArchitectureMode('compare');
  document.getElementById('archBuildModeBtn').onclick = () => setArchitectureMode('build');
  document.getElementById('pipelineNewBtn').onclick = () => {
    pipelineDraft = makePresetPipeline(document.getElementById('pipelinePresetSelect').value);
    selectedPipelineStageId = pipelineDraft.pipeline[0]?.id || null;
    renderPipelineBuilder();
  };
  document.getElementById('pipelineCloneRunBtn').onclick = () => {
    const runs = data.architectureRuns?.runs || [];
    const selected = runs.find(r => r.run_id === document.getElementById('archRunA').value) || runs[0];
    if(selected) {
      pipelineDraft = normalizePipelineDraft(JSON.parse(JSON.stringify(Object.assign({}, selected, {execution:{status:'planned'}}))));
      pipelineDraft.run_id = `planned_clone_${Date.now().toString(36)}`;
      pipelineDraft.label = `Planned clone of ${selected.label || selected.run_id}`;
      selectedPipelineStageId = pipelineDraft.pipeline?.[0]?.id || null;
      renderPipelineBuilder();
    }
  };
  document.getElementById('pipelineSaveBtn').onclick = savePlannedRun;
  document.getElementById('pipelineDownloadBtn').onclick = () => downloadJson('planned_architecture_run.json', plannedManifest());
  for(const id of ['showRois','showLabels','showEvents']) document.getElementById(id).onchange = drawOverlay;
  document.getElementById('showSuggestions').onchange = e => { setSetting('showSuggestions', e.target.checked); drawOverlay(); };
  document.getElementById('showEvidence').onchange = e => { setSetting('showEvidence', e.target.checked); applyDisplaySettings(); };
  document.getElementById('evidenceSelect').onchange = e => { setSetting('evidenceMap', e.target.value); applyDisplaySettings(); };
  for(const id of ['eventThreshold','kalmanGain','spikeGain','zoom','brightness','contrast','overlayOpacity','minArea','minEvents']) {
    document.getElementById(id).oninput = e => {
      const value = Number(e.target.value);
      setSetting(id, value);
      if(id === 'kalmanGain' || id === 'spikeGain') traceCache.clear();
      applySettingsToControls();
      renderAll();
    };
  }
  document.getElementById('queueSelect').onchange = e => { setSetting('queue', e.target.value); renderAll(); };
  document.getElementById('bulkIdentityBtn').onclick = assignSelectedIdentity;
  document.getElementById('bulkNeedsActionBtn').onclick = markSelectedAction;
  document.getElementById('virtualMergeBtn').onclick = createVirtualMerge;
  document.getElementById('clearMultiSelectBtn').onclick = clearMultiSelection;
  document.getElementById('acceptBtn').onclick = () => setRoiState('accept');
  document.getElementById('rejectBtn').onclick = () => setRoiState('reject');
  document.getElementById('unsureBtn').onclick = () => setRoiState('unsure');
  document.getElementById('clearBtn').onclick = () => setRoiState('');
  document.getElementById('deleteBtn').onclick = toggleDeleted;
  document.getElementById('eventAcceptBtn').onclick = () => setEventState('accept');
  document.getElementById('eventRejectBtn').onclick = () => setEventState('reject');
  document.getElementById('eventUnsureBtn').onclick = () => setEventState('unsure');
  document.getElementById('eventClearBtn').onclick = () => setEventState('');
  document.getElementById('suggestionPromoteBtn').onclick = promoteSuggestion;
  document.getElementById('suggestionMissedBtn').onclick = () => setSuggestionState('missed');
  document.getElementById('suggestionArtifactBtn').onclick = () => setSuggestionState('artifact');
  document.getElementById('suggestionUnsureBtn').onclick = () => setSuggestionState('unsure');
  document.getElementById('suggestionClearBtn').onclick = () => setSuggestionState('');
  document.getElementById('artifactClass').onchange = e => {
    const s = selectedSuggestion(); if(!s) return;
    annotations.suggestions[s.id] = Object.assign(suggestionAnn(s.id), {artifactClass:e.target.value, artifact_class:e.target.value});
    queueSave();
    renderAll();
  };
  document.getElementById('discoveryQueueSelect').onchange = e => { setSetting('discoveryQueue', e.target.value); renderAll(); };
  document.getElementById('exportRoiBtn').onclick = () => exportRows('roi');
  document.getElementById('exportEventBtn').onclick = () => exportRows('event');
  document.getElementById('exportSuggestionBtn').onclick = () => exportRows('suggestion');
  document.getElementById('exportJsonBtn').onclick = exportJson;
  for (const [id, field] of [['traceQuality','trace_quality'],['controlReady','control_ready'],['roiArtifactClass','artifact_class'],['needsAction','needs_action']]) {
    document.getElementById(id).onchange = e => {
      const roi = selectedRoi(); if(!roi) return;
      annotations.rois[roi.id] = Object.assign(roiAnn(roi.id), {[field]: e.target.value});
      recordAction(`roi_${field}`);
      queueSave();
      renderAll();
    };
  }
  document.getElementById('identityGroup').oninput = e => {
    const roi = selectedRoi(); if(!roi) return;
    annotations.rois[roi.id] = Object.assign(roiAnn(roi.id), {identity_group:e.target.value});
    recordAction('roi_identity_group');
    queueSave();
  };
  for (const [id, field] of [['eventType','event_type'],['timingQuality','timing_quality']]) {
    document.getElementById(id).onchange = e => {
      const roi = selectedRoi(); if(!roi || !selectedEventFrame) return;
      annotations.events[eventKey(roi.id, selectedEventFrame)] = Object.assign(eventAnn(roi.id, selectedEventFrame), {[field]: e.target.value});
      recordAction(`event_${field}`);
      queueSave();
      renderAll();
    };
  }
  roiNotes.oninput = e => {
    const roi = selectedRoi(); if(!roi) return;
    annotations.rois[roi.id] = Object.assign(roiAnn(roi.id), {notes:e.target.value});
    queueSave();
  };
  eventNotes.oninput = e => {
    const roi = selectedRoi(); if(!roi || !selectedEventFrame) return;
    annotations.events[eventKey(roi.id, selectedEventFrame)] = Object.assign(eventAnn(roi.id, selectedEventFrame), {notes:e.target.value});
    queueSave();
  };
  document.getElementById('suggestionNotes').oninput = e => {
    const s = selectedSuggestion(); if(!s) return;
    annotations.suggestions[s.id] = Object.assign(suggestionAnn(s.id), {notes:e.target.value});
    queueSave();
  };
  overlay.onclick = e => {
    const rect = overlay.getBoundingClientRect();
    const x = (e.clientX - rect.left) * data.video.width / rect.width;
    const y = (e.clientY - rect.top) * data.video.height / rect.height;
    let best = null, bestD = Infinity, bestType = 'roi';
    for(const roi of visibleRois()){
      const dx = x - roi.centroidX, dy = y - roi.centroidY, d = dx*dx + dy*dy;
      if(d < bestD){ bestD = d; best = roi; bestType = 'roi'; }
    }
    if(document.getElementById('showSuggestions').checked) for(const s of visibleSuggestions()){
      const dx = x - s.centroidX, dy = y - s.centroidY, d = dx*dx + dy*dy;
      if(d < bestD){ bestD = d; best = s; bestType = 'suggestion'; }
    }
    if(bestType === 'suggestion') selectSuggestion(best.id);
    else if(best) selectRoi(best.id, e.shiftKey || e.ctrlKey || e.metaKey);
  };
  document.addEventListener('keydown', e => {
    if(e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;
    if(e.code === 'Space'){ e.preventDefault(); togglePlay(); }
    else if(e.key === 'ArrowRight') setFrame(currentFrame + 1);
    else if(e.key === 'ArrowLeft') setFrame(currentFrame - 1);
    else if(e.key === 'j') nextRoi(1);
    else if(e.key === 'k') nextRoi(-1);
    else if(e.key === 'n') nextEvent(1);
    else if(e.key === 'p') nextEvent(-1);
    else if(e.key === 'a') setRoiState('accept');
    else if(e.key === 'r') setRoiState('reject');
    else if(e.key === 'u') setRoiState('unsure');
    else if(e.key === 'e') setEventState('accept');
    else if(e.key === 'x') setEventState('reject');
    else if(e.key === 'f') viewerScroll.requestFullscreen?.();
    else if(e.key === 'm') setSuggestionState('missed');
    else if(e.key === 'g') promoteSuggestion();
  });
  img.onload = () => { resizeOverlay(); drawCrop(); };
  window.onresize = resizeOverlay;
  window.addEventListener('hashchange', routePage);
}

function renderArchitectureLab(){
  const root = document.getElementById('architectureRuns');
  if(!root) return;
  const runs = data.architectureRuns?.runs || [];
  populateRunSelectors(runs);
  renderRunComparison();
  renderPipelineBuilder();
  root.innerHTML = '';
  if(!runs.length){
    root.innerHTML = '<p class="hint">No architecture runs are attached yet. Use tools/build_architecture_run.py to create architecture_runs.json.</p>';
    return;
  }
  for(const run of runs){
    const card = document.createElement('div');
    const status = run.execution?.status || 'completed';
    card.className = `archCard runStatus-${status}`;
    const evidence = (run.artifacts?.evidence_maps || []).map(m => `<span>${m.label || m.id || 'map'}</span>`).join('');
    const pipeline = (run.pipeline || []).map(stage => {
      const def = stageDef(stage);
      return `<span title="${escapeHtml(paramSummary(stage).replace(/<[^>]+>/g, ' '))}">${escapeHtml(def?.label || stage.label || stage.name || stageOp(stage) || stage.id || 'stage')}</span>`;
    }).join('');
    const sweep = run.sweep?.parameters ? run.sweep.parameters.map(item => `<span>${escapeHtml((item.stage || item.stage_id) + '.' + item.param)}=${escapeHtml(item.value ?? (item.values || []).join(','))}</span>`).join('') : '';
    const ann = run.annotation_summary || {};
    card.innerHTML = `
      <div class="runCardHeader"><h3>${run.label || run.run_id}</h3><span class="runStatus">${escapeHtml(status)}</span></div>
      <p class="hint">${run.run_id} | ${run.dataset_id}${run.sweep?.total_runs ? ` | sweep ${Number(run.sweep.index || 0) + 1}/${run.sweep.total_runs}` : ''}</p>
      <div class="archMeta">
        <div><b>${run.summary?.roi_count ?? 'n/a'}</b><span>ROIs</span></div>
        <div><b>${run.summary?.event_count ?? 'n/a'}</b><span>events</span></div>
        <div><b>${run.summary?.suggestion_count ?? 'n/a'}</b><span>suggestions</span></div>
        <div><b>${run.summary?.frame_count ?? data.video.frames}</b><span>frames</span></div>
        <div><b>${ann.roi_states?.accepted ?? 'n/a'}</b><span>accepted ROIs</span></div>
        <div><b>${ann.control_ready?.yes ?? 'n/a'}</b><span>control-ready</span></div>
      </div>
      <table class="smallTable"><tr><th>Artifact</th><th>Path</th></tr>
        <tr><td>review data</td><td>${run.artifacts?.review_data || ''}</td></tr>
        <tr><td>ROI summary</td><td>${run.artifacts?.roi_summary_tsv || ''}</td></tr>
      </table>
      <div class="archEvidence">${pipeline}</div>
      <div class="archEvidence">${sweep}</div>
      <div class="archEvidence">${evidence}</div>`;
    root.appendChild(card);
  }
}

function runLabel(run){
  return run ? `${run.label || run.run_id}` : '';
}

function runMetric(run, path, fallback=0){
  let cur = run;
  for(const part of path.split('.')){
    if(cur === undefined || cur === null) return fallback;
    cur = cur[part];
  }
  return cur === undefined || cur === null ? fallback : cur;
}

const FALLBACK_STAGE_CATALOG = [
  {type:'temporal_smoothing', op:'temporal_highpass_gaussian', label:'Temporal high-pass Gaussian', input:'raw_video', output:'highpass_video', params:{sigma_frames:{type:'number', min:1, max:20, step:1, default:6}}},
  {type:'spatial_smoothing', op:'spatial_gaussian', label:'Spatial Gaussian smoothing', input:'highpass_video', output:'smoothed_video', params:{sigma_px:{type:'number', min:0, max:4, step:0.1, default:0.8}}},
  {type:'background_correction', op:'local_background_ring', label:'Local background ring', input:'roi_candidates', output:'roi_traces', params:{outer_radius_px:{type:'number', min:4, max:40, step:1, default:15}, neuropil_weight:{type:'number', min:0, max:1.5, step:0.05, default:0.7}}},
  {type:'motion_correction', op:'rigid_shift_estimate', label:'Rigid drift estimate', input:'raw_video', output:'registered_video', params:{max_shift_px:{type:'number', min:1, max:12, step:1, default:4}}},
  {type:'filtering', op:'robust_positive_local_z', label:'Robust positive local-z', input:'highpass_video', output:'z_stack', params:{local_radius_px:{type:'number', min:3, max:31, step:2, default:11}, epsilon:{type:'number', min:0, max:10, step:0.5, default:1}}},
  {type:'filtering', op:'gamma_cfar', label:'Gamma CFAR', input:'smoothed_video', output:'candidate_mask', params:{pfa:{type:'number', min:0.000001, max:0.1, step:0.0001, default:0.001}, guard_px:{type:'number', min:0, max:12, step:1, default:2}}},
  {type:'trace_extraction', op:'component_filter', label:'Component extraction', input:'z_stack', output:'roi_candidates', params:{seed_z:{type:'number', min:0.5, max:8, step:0.1, default:2.0}, grow_z:{type:'number', min:0.2, max:5, step:0.1, default:1.1}, min_area_px:{type:'number', min:1, max:100, step:1, default:8}, max_area_px:{type:'number', min:20, max:800, step:10, default:260}}},
  {type:'event_model', op:'robust_kalman_positive_innovation', label:'Kalman positive innovation events', input:'roi_traces', output:'candidate_events', params:{event_threshold_z:{type:'number', min:0.5, max:8, step:0.1, default:2.4}, kalman_gain:{type:'number', min:0.001, max:0.3, step:0.005, default:0.06}, spike_gain:{type:'number', min:0, max:0.08, step:0.002, default:0.008}}},
  {type:'event_model', op:'oasis_deconvolution_import', label:'OASIS trace import', input:'roi_traces', output:'deconvolved_events', params:{array_key:{type:'text', default:'spikes'}}},
  {type:'candidate_ranking', op:'heuristic_priority_v1', label:'Heuristic priority ranking', input:'roi_candidates', output:'ranked_candidates', params:{local_correlation_weight:{type:'number', min:-1, max:1, step:0.05, default:0.2}, event_support_weight:{type:'number', min:-1, max:1, step:0.05, default:0.2}, artifact_weight:{type:'number', min:-1, max:1, step:0.05, default:-0.15}}},
  {type:'import', op:'pmd_denoised_video_import', label:'PMD denoised video import', input:'raw_video', output:'highpass_video', params:{denoised_video:{type:'text', default:''}}},
  {type:'import', op:'suite2p_import', label:'Suite2p import', input:'raw_video', output:'roi_candidates', params:{suite2p_dir:{type:'text', default:''}}}
];

function paramStep(name, spec){
  if(name === 'pfa') return 0.0001;
  if(name.includes('weight') || name.includes('gain')) return 0.01;
  if(name.includes('threshold') || name.endsWith('_z') || name.includes('sigma')) return 0.1;
  return 1;
}

function catalogParamSpec(name, stage){
  const docs = stage.parameter_docs?.[name] || {};
  const ranges = stage.param_ranges?.[name] || docs.range || {};
  const defaultValue = Object.prototype.hasOwnProperty.call(stage.default_params || {}, name) ? stage.default_params[name] : '';
  const isNumber = ranges.minimum !== undefined || ranges.maximum !== undefined || typeof defaultValue === 'number';
  return {
    type: isNumber ? 'number' : 'text',
    min: ranges.minimum,
    max: ranges.maximum,
    step: isNumber ? paramStep(name, docs) : undefined,
    default: defaultValue ?? '',
    doc: docs.meaning || '',
    why: docs.why || '',
    required: Boolean(docs.required || (stage.required_params || []).includes(name))
  };
}

function buildStageCatalog(rawCatalog){
  if(!rawCatalog || typeof rawCatalog !== 'object') return FALLBACK_STAGE_CATALOG;
  return Object.values(rawCatalog).sort((a,b) => (a.order || 0) - (b.order || 0)).map(stage => {
    const names = new Set([...(stage.required_params || []), ...Object.keys(stage.default_params || {}), ...Object.keys(stage.param_ranges || {}), ...Object.keys(stage.parameter_docs || {})]);
    const params = {};
    for(const name of names) params[name] = catalogParamSpec(name, stage);
    return {
      type: stage.type || 'stage',
      op: stage.stage_id,
      label: stage.label || stage.stage_id,
      input: stage.input || '',
      output: stage.output || '',
      params,
      description: stage.description || '',
      why_use_it: stage.why_use_it || '',
      real_time_profile: stage.real_time_profile || {},
      parameter_docs: stage.parameter_docs || {}
    };
  });
}

const STAGE_CATALOG = buildStageCatalog(data.pipelineCatalog);

let pipelineDraft = makePresetPipeline('current_review_pipeline');
let selectedPipelineStageId = pipelineDraft.pipeline[0]?.id || null;

function escapeHtml(value){
  return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}

function stageOp(stageOrOp){
  if(typeof stageOrOp === 'string') return stageOrOp;
  return stageOrOp?.stage_id || stageOrOp?.stage || stageOrOp?.op || stageOrOp?.name || '';
}

function stageDef(stageOrOp){ return STAGE_CATALOG.find(s => s.op === stageOp(stageOrOp)); }

function datasetFrameRateHz(){
  return Number(data.dataset?.online?.target_frame_rate_hz || data.dataset?.frame_rate_hz || data.video?.frameRateHz || data.video?.frame_rate_hz || 5);
}

function frameBudgetMs(){
  const rate = datasetFrameRateHz();
  return Number.isFinite(rate) && rate > 0 ? 1000 / rate : null;
}

function realtimeBadges(def){
  const rt = def?.real_time_profile || {};
  const badges = [];
  if(rt.mode) badges.push(`<span class="rtBadge ${escapeHtml(rt.mode)}">${escapeHtml(rt.mode)}</span>`);
  if(rt.adaptive) badges.push('<span class="rtBadge adaptive">adaptive</span>');
  if(rt.stateful) badges.push('<span class="rtBadge stateful">stateful</span>');
  if(rt.requires_gpu) badges.push('<span class="rtBadge gpu">GPU</span>');
  if(rt.closed_loop_candidate) badges.push('<span class="rtBadge loop">closed-loop candidate</span>');
  return badges.join('');
}

function pipelineRealtimeSummary(run){
  const budget = frameBudgetMs();
  let total = 0;
  const offline = [];
  const unknown = [];
  const gpu = [];
  for(const stage of run.pipeline || []){
    if(stage.enabled === false) continue;
    const def = stageDef(stage);
    const rt = def?.real_time_profile || {};
    if(rt.mode === 'offline' || rt.mode === 'batch') offline.push(def?.label || stage.id);
    if(rt.mode === 'unknown') unknown.push(def?.label || stage.id);
    if(rt.requires_gpu) gpu.push(def?.label || stage.id);
    if(Number.isFinite(Number(rt.latency_budget_ms))) total += Number(rt.latency_budget_ms);
  }
  const warnings = [];
  if(offline.length) warnings.push(`${offline.length} offline/batch stage${offline.length === 1 ? '' : 's'} in a plan intended for streaming.`);
  if(unknown.length) warnings.push(`${unknown.length} stage${unknown.length === 1 ? '' : 's'} have unknown latency metadata.`);
  if(budget !== null && total > budget) warnings.push(`Estimated ${total.toFixed(1)} ms/frame exceeds ${budget.toFixed(1)} ms/frame at ${datasetFrameRateHz().toFixed(1)} Hz.`);
  return {frame_rate_hz: datasetFrameRateHz(), frame_budget_ms: budget, estimated_ms: total, offline, unknown, gpu, warnings};
}

function defaultParams(def){
  const params = {};
  for(const [name, spec] of Object.entries(def?.params || {})) params[name] = spec.default ?? '';
  return params;
}

function makeStage(op, index=0){
  const def = stageDef(op) || STAGE_CATALOG[0];
  const base = def.op.replace(/[^a-z0-9]+/gi, '_').replace(/^_|_$/g, '').toLowerCase();
  return {
    id: `${base}_${index + 1}`,
    stage_id: def.op,
    type: def.type,
    op: def.op,
    enabled: true,
    input: def.input,
    output: def.output,
    params: defaultParams(def)
  };
}

function normalizeStageForBuilder(stage, index=0){
  const def = stageDef(stage) || STAGE_CATALOG[0];
  const normalized = Object.assign(makeStage(def.op, index), stage || {});
  normalized.stage_id = def.op;
  normalized.op = def.op;
  normalized.type = normalized.type || def.type;
  normalized.input = normalized.input || def.input;
  normalized.output = normalized.output || def.output;
  normalized.params = Object.assign(defaultParams(def), normalized.params || {});
  if(!normalized.id) normalized.id = makeStage(def.op, index).id;
  return normalized;
}

function normalizePipelineDraft(run){
  const draft = Object.assign(makePresetPipeline('current_review_pipeline'), run || {});
  draft.pipeline = (draft.pipeline || []).map((stage, index) => normalizeStageForBuilder(stage, index));
  if(draft.sweep && Array.isArray(draft.sweep.parameters)) {
    draft.sweep = Object.assign({}, draft.sweep, {parameters: draft.sweep.parameters.map(axis => normalizeSweepAxis(axis, draft.pipeline)).filter(Boolean)});
  } else if(Array.isArray(draft.sweep_axes) && draft.sweep_axes.length) {
    draft.sweep = {id: `${draft.run_id || 'planned'}_sweep`, label: 'Dashboard sweep', parameters: draft.sweep_axes.map(axis => normalizeSweepAxis(axis, draft.pipeline)).filter(Boolean)};
  } else {
    delete draft.sweep;
  }
  delete draft.sweep_axes;
  return draft;
}

function makePresetPipeline(name){
  const ops = name === 'pmd_import' ? ['pmd_denoised_video_import', 'robust_positive_local_z', 'component_filter', 'robust_kalman_positive_innovation', 'heuristic_priority_v1'] :
    name === 'suite2p_import' ? ['suite2p_import', 'heuristic_priority_v1'] :
    name === 'oasis_import' ? ['temporal_highpass_gaussian', 'robust_positive_local_z', 'component_filter', 'local_background_ring', 'oasis_deconvolution_import', 'heuristic_priority_v1'] :
    ['temporal_highpass_gaussian', 'robust_positive_local_z', 'component_filter', 'local_background_ring', 'robust_kalman_positive_innovation', 'heuristic_priority_v1'];
  const pipeline = ops.map((op, i) => makeStage(op, i));
  const runId = `planned_${name}_${Date.now().toString(36)}`;
  return {
    schema_version: 1,
    run_id: runId,
    dataset_id: datasetId,
    label: name === 'current_review_pipeline' ? 'Planned current-style pipeline' : `Planned ${name.replace(/_/g, ' ')}`,
    method_family: 'architecture_lab_pipeline',
    purpose: 'candidate_proposal',
    pipeline,
    summary: {roi_count: 0, event_count: 0, suggestion_count: 0, frame_count: data.video.frames},
    artifacts: {source_video: data.dataset?.paths?.raw_video || data.video?.name || '', intermediates: []},
    provenance: {source: 'architecture_lab_builder', source_script: null, git_commit: null, software_versions: {}},
    execution: {status: 'planned'},
    validation: {status: 'unchecked', errors: [], warnings: []}
  };
}

function sweepFactors(run=pipelineDraft){
  return Array.isArray(run.sweep?.parameters) ? run.sweep.parameters : [];
}

function setSweepFactors(factors){
  const cleaned = factors.filter(Boolean);
  if(cleaned.length) {
    pipelineDraft.sweep = Object.assign({
      id: `${pipelineDraft.run_id || 'planned'}_sweep`,
      label: `${pipelineDraft.label || pipelineDraft.run_id || 'Planned'} sweep`
    }, pipelineDraft.sweep || {}, {parameters: cleaned});
  } else {
    delete pipelineDraft.sweep;
  }
}

function normalizeSweepAxis(axis, pipeline=pipelineDraft.pipeline || []){
  const stageKey = axis?.stage || axis?.step_id || axis?.stage_id;
  const stage = pipeline.find(s => s.id === stageKey) || pipeline.find(s => stageOp(s) === stageKey);
  if(!stage || !axis?.param) return null;
  return {
    stage: stage.id,
    stage_id: stageOp(stage),
    param: axis.param,
    values: Array.isArray(axis.values) ? axis.values : [],
    label: axis.label || `${stage.id}.${axis.param}`
  };
}

function validatePipeline(run){
  const errors = [], warnings = [], stageIssues = {};
  const addIssue = (stageId, kind, message) => {
    (kind === 'error' ? errors : warnings).push(message);
    if(stageId) {
      stageIssues[stageId] = stageIssues[stageId] || {errors: [], warnings: []};
      stageIssues[stageId][kind === 'error' ? 'errors' : 'warnings'].push(message);
    }
  };
  const seenIds = new Set();
  const available = new Set(['raw_video']);
  for(const [index, stage] of (run.pipeline || []).entries()){
    const op = stageOp(stage);
    const stageId = stage.id || `stage_${index + 1}`;
    if(!stage.id) addIssue(stageId, 'error', `Stage ${index + 1} is missing an id.`);
    if(seenIds.has(stage.id)) addIssue(stage.id, 'error', `Duplicate stage id: ${stage.id}`);
    seenIds.add(stage.id);
    const def = stageDef(op);
    if(!def) {
      addIssue(stageId, 'error', `Unknown operation: ${op || '(blank)'}`);
      continue;
    }
    if(stage.enabled === false) continue;
    if(stage.input && !available.has(stage.input)) addIssue(stageId, 'error', `${stageId} needs input ${stage.input}, but no earlier enabled stage produces it.`);
    for(const [param, spec] of Object.entries(def.params || {})){
      const value = stage.params?.[param];
      if(value === undefined || value === '') addIssue(stageId, 'error', `${stageId} is missing ${param}.`);
      if(spec.type === 'number' && value !== undefined && value !== ''){
        const numeric = Number(value);
        if(!Number.isFinite(numeric)) addIssue(stageId, 'error', `${stageId}.${param} must be numeric.`);
        else {
          if(spec.min !== undefined && numeric < spec.min) addIssue(stageId, 'error', `${stageId}.${param} is below ${spec.min}.`);
          if(spec.max !== undefined && numeric > spec.max) addIssue(stageId, 'error', `${stageId}.${param} is above ${spec.max}.`);
        }
      }
    }
    if(stage.output) available.add(stage.output);
  }
  for(const axis of sweepFactors(run)){
    const stage = (run.pipeline || []).find(s => s.id === axis.stage);
    if(!stage) {
      addIssue(axis.stage, 'error', `Sweep axis references unknown stage ${axis.stage}.`);
      continue;
    }
    const def = stageDef(stage);
    const spec = def?.params?.[axis.param];
    if(!spec) {
      addIssue(axis.stage, 'error', `Sweep axis references unknown parameter ${axis.stage}.${axis.param}.`);
      continue;
    }
    const values = Array.isArray(axis.values) ? axis.values : [];
    if(!values.length) addIssue(axis.stage, 'error', `Sweep axis ${axis.stage}.${axis.param} has no values.`);
    for(const value of values){
      if(spec.type === 'number'){
        const numeric = Number(value);
        if(!Number.isFinite(numeric)) addIssue(axis.stage, 'error', `Sweep value ${axis.stage}.${axis.param}=${value} must be numeric.`);
        else {
          if(spec.min !== undefined && numeric < spec.min) addIssue(axis.stage, 'error', `Sweep value ${axis.stage}.${axis.param}=${value} is below ${spec.min}.`);
          if(spec.max !== undefined && numeric > spec.max) addIssue(axis.stage, 'error', `Sweep value ${axis.stage}.${axis.param}=${value} is above ${spec.max}.`);
        }
      }
    }
  }
  if(!(run.pipeline || []).some(s => s.enabled !== false && s.type === 'candidate_ranking')) warnings.push('No candidate-ranking stage is enabled.');
  if(!(run.pipeline || []).some(s => s.enabled !== false && s.type === 'event_model')) warnings.push('No event model is enabled; Architecture Lab will compare ROI candidates only.');
  for(const warning of pipelineRealtimeSummary(run).warnings) warnings.push(warning);
  return {status: errors.length ? 'invalid' : 'valid', errors, warnings, stageIssues};
}

function plannedRun(){
  const validation = validatePipeline(pipelineDraft);
  const run = Object.assign({}, pipelineDraft, {validation});
  if(!sweepFactors(run).length) delete run.sweep;
  return run;
}

function sweepAxisLabel(axis){
  return `${axis.stage || axis.stage_id}.${axis.param}`;
}

function parseSweepValues(raw, spec){
  return String(raw || '').split(',').map(v => v.trim()).filter(Boolean).map(v => spec?.type === 'number' ? Number(v) : v);
}

function axisCombinations(axes){
  const active = (axes || []).filter(axis => Array.isArray(axis.values) && axis.values.length);
  if(!active.length) return [[]];
  return active.reduce((combos, axis) => {
    const next = [];
    for(const combo of combos) for(const value of axis.values) next.push([...combo, {axis, value}]);
    return next;
  }, [[]]);
}

function expandPlannedRuns(run){
  const axes = sweepFactors(run);
  const combos = axisCombinations(axes);
  if(combos.length === 1 && combos[0].length === 0) return [run];
  const totalRuns = combos.length;
  const sweepBase = Object.assign({}, run.sweep || {}, {parameters: axes});
  return combos.map((combo, index) => {
    const child = JSON.parse(JSON.stringify(run));
    child.run_id = `${run.run_id}__sweep_${String(index + 1).padStart(3, '0')}`;
    child.label = `${run.label || run.run_id} sweep ${index + 1}`;
    child.sweep = Object.assign({}, sweepBase, {index, total_runs: totalRuns, parameters: []});
    for(const item of combo){
      const stage = child.pipeline.find(s => s.id === item.axis.stage);
      if(stage) {
        stage.params = stage.params || {};
        stage.params[item.axis.param] = item.value;
      }
      child.sweep.parameters.push({stage: item.axis.stage, stage_id: item.axis.stage_id, param: item.axis.param, value: item.value});
    }
    return child;
  });
}

function plannedManifest(){
  const run = plannedRun();
  const manifest = {schema_version: 1, dataset_id: datasetId, runs: expandPlannedRuns(run)};
  const axes = sweepFactors(run);
  if(axes.length) manifest.sweep = Object.assign({}, run.sweep || {}, {parameters: axes, total_runs: manifest.runs.length});
  return manifest;
}

function paramSummary(stage){
  const def = stageDef(stage);
  const entries = Object.entries(def?.params || {}).slice(0, 4);
  if(!entries.length) return '<span class="pipelineParam muted">no params</span>';
  return entries.map(([name]) => `<span class="pipelineParam">${escapeHtml(name)}=${escapeHtml(stage.params?.[name] ?? '')}</span>`).join('');
}

function parameterHelp(name, spec){
  const parts = [];
  if(spec.doc) parts.push(escapeHtml(spec.doc));
  const bounds = [];
  if(spec.min !== undefined) bounds.push(`min ${spec.min}`);
  if(spec.max !== undefined) bounds.push(`max ${spec.max}`);
  if(bounds.length) parts.push(`Range: ${bounds.join(', ')}.`);
  if(spec.why) parts.push(escapeHtml(spec.why));
  return parts.join(' ');
}

function stageIssueBadge(stage, validation){
  const issues = validation.stageIssues?.[stage.id] || {errors: [], warnings: []};
  if(stage.enabled === false) return '<span class="stageStatus off">off</span>';
  if(issues.errors?.length) return `<span class="stageStatus bad">${issues.errors.length} issue${issues.errors.length === 1 ? '' : 's'}</span>`;
  if(issues.warnings?.length) return `<span class="stageStatus warn">${issues.warnings.length} warning${issues.warnings.length === 1 ? '' : 's'}</span>`;
  return '<span class="stageStatus ok">valid</span>';
}

function downloadJson(name, payload){
  const blob = new Blob([JSON.stringify(payload, null, 2) + '\n'], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}

function renderPipelineBuilder(){
  const palette = document.getElementById('pipelineStagePalette');
  const stack = document.getElementById('pipelineStack');
  const inspector = document.getElementById('pipelineInspector');
  const validationRoot = document.getElementById('pipelineValidation');
  const preview = document.getElementById('pipelineJsonPreview');
  if(!palette || !stack || !inspector || !validationRoot || !preview) return;
  const groups = {};
  for(const def of STAGE_CATALOG) (groups[def.type] = groups[def.type] || []).push(def);
  palette.innerHTML = Object.entries(groups).map(([type, defs]) => `
    <details open><summary>${escapeHtml(type.replace(/_/g, ' '))}</summary>
      <div class="stagePaletteGroup">${defs.map(def => `<button type="button" data-stage-op="${escapeHtml(def.op)}">${escapeHtml(def.label)}</button>`).join('')}</div>
    </details>`).join('');
  for(const btn of palette.querySelectorAll('[data-stage-op]')) btn.onclick = () => {
    pipelineDraft.pipeline.push(makeStage(btn.dataset.stageOp, pipelineDraft.pipeline.length));
    selectedPipelineStageId = pipelineDraft.pipeline[pipelineDraft.pipeline.length - 1].id;
    renderPipelineBuilder();
  };
  const validation = validatePipeline(pipelineDraft);
  stack.innerHTML = pipelineDraft.pipeline.map((stage, index) => {
    const def = stageDef(stage);
    return `
    <div class="pipelineStage ${stage.id === selectedPipelineStageId ? 'sel' : ''} ${stage.enabled === false ? 'disabled' : ''}">
      <button type="button" class="pipelineStageMain" data-select-stage="${escapeHtml(stage.id)}">
        <span class="stageIndex">${index + 1}</span>
        <span class="stageBody">
          <b>${escapeHtml(def?.label || stageOp(stage) || stage.id)}</b>
          <span class="stageMeta"><span class="stageTypeChip">${escapeHtml((def?.type || stage.type || 'stage').replace(/_/g, ' '))}</span>${stageIssueBadge(stage, validation)}${realtimeBadges(def)}</span>
          <span class="stageDescription">${escapeHtml(def?.description || '')}</span>
          <span class="artifactFlow"><i>${escapeHtml(stage.input || 'input')}</i><strong>-></strong><i>${escapeHtml(stage.output || 'output')}</i></span>
          <span class="pipelineParamRow">${paramSummary(stage)}</span>
        </span>
      </button>
      <div class="buttonRow">
        <button type="button" data-move-stage="${escapeHtml(stage.id)}" data-dir="-1">Up</button>
        <button type="button" data-move-stage="${escapeHtml(stage.id)}" data-dir="1">Down</button>
        <button type="button" data-duplicate-stage="${escapeHtml(stage.id)}">Duplicate</button>
        <button type="button" data-toggle-stage="${escapeHtml(stage.id)}">${stage.enabled === false ? 'Enable' : 'Disable'}</button>
        <button type="button" data-delete-stage="${escapeHtml(stage.id)}">Delete</button>
      </div>
    </div>`;
  }).join('');
  for(const btn of stack.querySelectorAll('[data-select-stage]')) btn.onclick = () => { selectedPipelineStageId = btn.dataset.selectStage; renderPipelineBuilder(); };
  for(const btn of stack.querySelectorAll('[data-toggle-stage]')) btn.onclick = () => {
    const stage = pipelineDraft.pipeline.find(s => s.id === btn.dataset.toggleStage);
    if(stage) stage.enabled = stage.enabled === false;
    renderPipelineBuilder();
  };
  for(const btn of stack.querySelectorAll('[data-delete-stage]')) btn.onclick = () => {
    pipelineDraft.pipeline = pipelineDraft.pipeline.filter(s => s.id !== btn.dataset.deleteStage);
    setSweepFactors(sweepFactors().filter(axis => axis.stage !== btn.dataset.deleteStage));
    selectedPipelineStageId = pipelineDraft.pipeline[0]?.id || null;
    renderPipelineBuilder();
  };
  for(const btn of stack.querySelectorAll('[data-duplicate-stage]')) btn.onclick = () => {
    const idx = pipelineDraft.pipeline.findIndex(s => s.id === btn.dataset.duplicateStage);
    if(idx >= 0){
      const stage = JSON.parse(JSON.stringify(pipelineDraft.pipeline[idx]));
      stage.id = `${stage.id}_copy`;
      pipelineDraft.pipeline.splice(idx + 1, 0, stage);
      selectedPipelineStageId = stage.id;
    }
    renderPipelineBuilder();
  };
  for(const btn of stack.querySelectorAll('[data-move-stage]')) btn.onclick = () => {
    const idx = pipelineDraft.pipeline.findIndex(s => s.id === btn.dataset.moveStage);
    const next = idx + Number(btn.dataset.dir);
    if(idx >= 0 && next >= 0 && next < pipelineDraft.pipeline.length){
      const [stage] = pipelineDraft.pipeline.splice(idx, 1);
      pipelineDraft.pipeline.splice(next, 0, stage);
    }
    renderPipelineBuilder();
  };
  const selected = pipelineDraft.pipeline.find(s => s.id === selectedPipelineStageId) || pipelineDraft.pipeline[0];
  if(selected) {
    const def = stageDef(selected);
    const numericParams = Object.entries(def?.params || {}).filter(([, spec]) => spec.type === 'number');
    const sweepParamOptions = numericParams.map(([name]) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join('');
    inspector.innerHTML = `
      <label>Run label <input id="pipelineLabelInput" value="${escapeHtml(pipelineDraft.label)}"></label>
      <label>Run ID <input id="pipelineRunIdInput" value="${escapeHtml(pipelineDraft.run_id)}"></label>
      <h3>${escapeHtml(def?.label || selected.op)}</h3>
      <div class="stageExplain">
        <p>${escapeHtml(def?.description || '')}</p>
        <p><b>Why:</b> ${escapeHtml(def?.why_use_it || '')}</p>
        <div class="stageMeta">${realtimeBadges(def)}</div>
      </div>
      <label>Stage ID <input id="stageIdInput" value="${escapeHtml(selected.id)}"></label>
      ${(Object.entries(def?.params || {}).map(([name, spec]) => `
        <label>${escapeHtml(name)}
          <input data-stage-param="${escapeHtml(name)}" inputmode="${spec.type === 'number' ? 'decimal' : 'text'}" type="text" value="${escapeHtml(selected.params?.[name] ?? spec.default ?? '')}" ${spec.type === 'number' ? `data-min="${spec.min}" data-max="${spec.max}"` : ''}>
          <span class="paramHelp">${parameterHelp(name, spec)}</span>
        </label>`).join(''))}`;
    inspector.innerHTML += `
      <section class="sweepEditor">
        <h3>Parameter sweep</h3>
        <p class="hint">Comma-separated values create planned runs only; no browser-side execution happens.</p>
        <label>Sweep parameter <select id="sweepParamSelect">${sweepParamOptions}</select></label>
        <label>Values <input id="sweepValuesInput" placeholder="1.8, 2.2, 2.6"></label>
        <button type="button" id="addSweepAxisBtn" ${numericParams.length ? '' : 'disabled'}>Add sweep axis</button>
      </section>`;
    document.getElementById('pipelineLabelInput').onchange = e => { pipelineDraft.label = e.target.value; renderPipelineBuilder(); };
    document.getElementById('pipelineRunIdInput').onchange = e => { pipelineDraft.run_id = e.target.value; renderPipelineBuilder(); };
    document.getElementById('stageIdInput').onchange = e => { selected.id = e.target.value.trim(); selectedPipelineStageId = selected.id; renderPipelineBuilder(); };
    for(const input of inspector.querySelectorAll('[data-stage-param]')) input.oninput = e => {
      const spec = def.params[e.target.dataset.stageParam];
      selected.params[e.target.dataset.stageParam] = spec.type === 'number' && e.target.value !== '' && Number.isFinite(Number(e.target.value)) ? Number(e.target.value) : e.target.value;
    };
    for(const input of inspector.querySelectorAll('[data-stage-param]')) input.onchange = () => renderPipelineBuilder();
    const addSweepBtn = document.getElementById('addSweepAxisBtn');
    if(addSweepBtn) addSweepBtn.onclick = () => {
      const param = document.getElementById('sweepParamSelect').value;
      const spec = def.params[param];
      const values = parseSweepValues(document.getElementById('sweepValuesInput').value, spec);
      if(param && values.length) {
        setSweepFactors([...sweepFactors().filter(axis => !(axis.stage === selected.id && axis.param === param)), {stage: selected.id, stage_id: stageOp(selected), param, values, label: `${selected.id}.${param}`}]);
      }
      renderPipelineBuilder();
    };
  } else {
    inspector.innerHTML = '<p class="hint">Add a stage to configure parameters.</p>';
  }
  const run = plannedRun();
  const manifest = plannedManifest();
  const realtime = pipelineRealtimeSummary(run);
  validationRoot.innerHTML = `
    <div class="validationState ${run.validation.status}">${run.validation.status}</div>
    <div class="realtimeSummary">
      <b>100 Hz readiness</b>
      <span>${fmt(realtime.estimated_ms, 1)} ms estimated / ${realtime.frame_budget_ms ? fmt(realtime.frame_budget_ms, 1) : 'n/a'} ms budget at ${fmt(realtime.frame_rate_hz, 1)} Hz</span>
      <span>${realtime.offline.length} offline, ${realtime.unknown.length} unknown-latency, ${realtime.gpu.length} GPU-sensitive stages</span>
    </div>
    <div class="sweepAxisList">
      ${sweepFactors(run).map((axis, index) => `<div class="sweepAxis"><b>${escapeHtml(sweepAxisLabel(axis))}</b><span>${escapeHtml((axis.values || []).join(', '))}</span><button type="button" data-remove-sweep="${index}">Remove</button></div>`).join('') || '<p class="hint">No sweep axes configured.</p>'}
    </div>
    <div class="pipelineWarning">${manifest.runs.length} planned run${manifest.runs.length === 1 ? '' : 's'} will be saved/exported.</div>
    ${run.validation.errors.map(e => `<div class="qcWarning">${escapeHtml(e)}</div>`).join('')}
    ${run.validation.warnings.map(w => `<div class="pipelineWarning">${escapeHtml(w)}</div>`).join('')}`;
  for(const btn of validationRoot.querySelectorAll('[data-remove-sweep]')) btn.onclick = () => {
    const factors = sweepFactors();
    factors.splice(Number(btn.dataset.removeSweep), 1);
    setSweepFactors(factors);
    renderPipelineBuilder();
  };
  preview.textContent = JSON.stringify(manifest, null, 2);
}

async function savePlannedRun(){
  const planned = plannedManifest();
  const manifest = Object.assign({}, data.architectureRuns || {schema_version: 1, dataset_id: datasetId, runs: []});
  const plannedIds = new Set(planned.runs.map(r => r.run_id));
  manifest.runs = [...(manifest.runs || []).filter(r => !plannedIds.has(r.run_id)), ...planned.runs];
  data.architectureRuns = manifest;
  if(serverBacked){
    try {
      const res = await fetch('architecture_runs.json', {method:'PUT', headers:{'Content-Type':'application/json'}, body:JSON.stringify(manifest, null, 2)});
      if(!res.ok) throw new Error(await res.text());
      setSaveState('saved planned run', 'ok');
    } catch (_) {
      downloadJson('planned_architecture_run.json', manifest);
      setSaveState('downloaded planned run', 'ok');
    }
  } else {
    downloadJson('planned_architecture_run.json', manifest);
    setSaveState('downloaded planned run', 'ok');
  }
  renderArchitectureLab();
}

function setArchitectureMode(mode){
  const build = mode === 'build';
  document.getElementById('architectureComparePanel')?.classList.toggle('hidden', build);
  document.getElementById('architectureBuildPanel')?.classList.toggle('hidden', !build);
  document.getElementById('archCompareModeBtn')?.classList.toggle('active', !build);
  document.getElementById('archBuildModeBtn')?.classList.toggle('active', build);
  if(build) renderPipelineBuilder();
}

function populateRunSelectors(runs){
  for(const [id, defaultIndex] of [['archRunA', 0], ['archRunB', Math.min(1, Math.max(0, runs.length - 1))]]){
    const select = document.getElementById(id);
    if(!select) continue;
    const previous = select.value;
    select.innerHTML = '';
    for(const run of runs){
      const opt = document.createElement('option');
      opt.value = run.run_id;
      opt.textContent = runLabel(run);
      select.appendChild(opt);
    }
    if(runs.some(r => r.run_id === previous)) select.value = previous;
    else if(runs[defaultIndex]) select.value = runs[defaultIndex].run_id;
  }
}

function renderRunComparison(){
  const root = document.getElementById('runComparison');
  if(!root) return;
  const runs = data.architectureRuns?.runs || [];
  if(runs.length < 2){
    root.innerHTML = '<p class="hint">Add a second architecture run manifest to compare methods side-by-side. The current run is still shown below.</p>';
    return;
  }
  const a = runs.find(r => r.run_id === document.getElementById('archRunA').value) || runs[0];
  const b = runs.find(r => r.run_id === document.getElementById('archRunB').value) || runs[1];
  const rows = [
    ['Candidate ROIs', 'summary.roi_count', false],
    ['Candidate events', 'summary.event_count', false],
    ['Discovery suggestions', 'summary.suggestion_count', false],
    ['Accepted ROIs', 'annotation_summary.roi_states.accepted', true],
    ['Rejected ROIs', 'annotation_summary.roi_states.rejected', false],
    ['Control-ready ROIs', 'annotation_summary.control_ready.yes', true],
    ['Accepted events', 'annotation_summary.event_states.accepted', true],
    ['Candidates per accepted ROI', 'annotation_summary.review_burden.candidate_rois_per_accepted_roi', false],
    ['Events per accepted event', 'annotation_summary.review_burden.candidate_events_per_accepted_event', false]
  ];
  let html = `<table class="smallTable compareTable"><tr><th>Metric</th><th>${runLabel(a)}</th><th>${runLabel(b)}</th><th>Delta B-A</th></tr>`;
  for(const [label, path, higherGood] of rows){
    const av = Number(runMetric(a, path, 0));
    const bv = Number(runMetric(b, path, 0));
    const delta = bv - av;
    const cls = Math.abs(delta) < 1e-9 ? 'deltaNeutral' : (higherGood ? delta > 0 : delta < 0) ? 'deltaGood' : 'deltaBad';
    html += `<tr><td>${label}</td><td>${fmt(av, Number.isInteger(av) ? 0 : 2)}</td><td>${fmt(bv, Number.isInteger(bv) ? 0 : 2)}</td><td class="${cls}">${delta >= 0 ? '+' : ''}${fmt(delta, Number.isInteger(delta) ? 0 : 2)}</td></tr>`;
  }
  root.innerHTML = html + '</table>';
}

function annotationSummary(){
  const roiStates = {accepted:0, rejected:0, unsure:0, unlabeled:0};
  const eventStates = {accepted:0, rejected:0, unsure:0, unlabeled:0};
  const suggestionStates = {promoted:0, missed:0, artifact:0, unsure:0, unlabeled:0};
  const traceQuality = {good:0, weak:0, noisy:0, unusable:0, unlabeled:0};
  const controlReady = {yes:0, maybe:0, no:0, unlabeled:0};
  const triageQueues = {strong_neuron:0, possible_missed_neuron:0, artifact_like:0, merged_cluster:0, weak_trace:0, needs_event_review:0, standard_review:0};
  for(const roi of data.rois){
    const ann = roiAnn(roi.id);
    const rs = ann.cell_state || (ann.state === 'accept' ? 'accepted' : ann.state === 'reject' ? 'rejected' : ann.state === 'unsure' ? 'unsure' : 'unlabeled');
    roiStates[roiStates[rs] === undefined ? 'unlabeled' : rs]++;
    const tq = ann.trace_quality || 'unlabeled';
    traceQuality[traceQuality[tq] === undefined ? 'unlabeled' : tq]++;
    const cr = ann.control_ready || 'unlabeled';
    controlReady[controlReady[cr] === undefined ? 'unlabeled' : cr]++;
    triageQueues[roiTriageCategory(roi)]++;
    for(const ev of eventsForRoi(roi)){
      const eann = eventAnn(roi.id, ev.frame);
      const es = eann.event_state || (eann.state === 'accept' ? 'accepted' : eann.state === 'reject' ? 'rejected' : eann.state === 'unsure' ? 'unsure' : 'unlabeled');
      eventStates[eventStates[es] === undefined ? 'unlabeled' : es]++;
    }
  }
  for(const s of data.discovery?.suggestions || []){
    const ann = suggestionAnn(s.id);
    const ss = annotations.promotedRois[s.id] ? 'promoted' : ann.state || 'unlabeled';
    suggestionStates[suggestionStates[ss] === undefined ? 'unlabeled' : ss]++;
    if(ss === 'promoted' || ss === 'missed') triageQueues.possible_missed_neuron++;
    if(ss === 'artifact' || (ann.artifact_class || ann.artifactClass) || (s.artifactCue && s.artifactCue !== 'none') || scoreValue(s, 'artifactScore') >= 0.4) triageQueues.artifact_like++;
  }
  const eventCount = Object.values(eventStates).reduce((a,b) => a+b, 0);
  return {
    roi_count: data.rois.length,
    event_count: eventCount,
    suggestion_count: data.discovery?.suggestions?.length || 0,
    roi_states: roiStates,
    event_states: eventStates,
    suggestion_states: suggestionStates,
    trace_quality: traceQuality,
    control_ready: controlReady,
    triage_categories: triageQueues,
    triage_queue_counts: triageQueues,
    review_burden: {
      candidate_rois_per_accepted_roi: data.rois.length / Math.max(1, roiStates.accepted),
      candidate_events_per_accepted_event: eventCount / Math.max(1, eventStates.accepted)
    }
  };
}

function auditRows(title, counts){
  const total = Object.values(counts).reduce((a,b) => a+b, 0) || 1;
  let html = `<h2>${title}</h2><div class="auditBars">`;
  for(const [name, count] of Object.entries(counts)){
    const pct = Math.round(100 * count / total);
    html += `<div class="auditRow"><span>${name}</span><div class="auditBar"><div class="auditFill" style="width:${pct}%"></div></div><b>${count}</b></div>`;
  }
  return html + '</div>';
}

function renderMetricsAudit(){
  const root = document.getElementById('metricsAudit');
  if(!root) return;
  const s = annotationSummary();
  const actionCount = Object.values(annotations.reviewStats?.actions || {}).reduce((a,b) => a + b, 0);
  root.innerHTML = `
    <div class="metricGrid">
      <div class="metric"><b>${s.roi_count}</b><span>candidate ROIs</span></div>
      <div class="metric"><b>${s.roi_states.accepted}</b><span>accepted ROIs</span></div>
      <div class="metric"><b>${s.event_count}</b><span>candidate events</span></div>
      <div class="metric"><b>${s.event_states.accepted}</b><span>accepted events</span></div>
      <div class="metric"><b>${s.suggestion_count}</b><span>discovery suggestions</span></div>
      <div class="metric"><b>${s.suggestion_states.promoted}</b><span>promoted suggestions</span></div>
      <div class="metric"><b>${s.review_burden.candidate_rois_per_accepted_roi.toFixed(1)}</b><span>ROIs per accepted ROI</span></div>
      <div class="metric"><b>${s.review_burden.candidate_events_per_accepted_event.toFixed(1)}</b><span>events per accepted event</span></div>
      <div class="metric"><b>${actionCount}</b><span>review actions</span></div>
      <div class="metric"><b>${annotations.reviewStats?.lastActionAt ? 'yes' : 'no'}</b><span>active session</span></div>
    </div>
    <div class="auditSplit">
      <div class="archCard">${auditRows('ROI states', s.roi_states)}</div>
      <div class="archCard">${auditRows('Event states', s.event_states)}</div>
      <div class="archCard">${auditRows('Trace quality', s.trace_quality)}</div>
      <div class="archCard">${auditRows('Control readiness', s.control_ready)}</div>
      <div class="archCard">${auditRows('Triage queues', s.triage_queue_counts)}</div>
      <div class="archCard">${auditRows('Discovery suggestions', s.suggestion_states)}</div>
    </div>`;
}

function quantile(values, q){
  const arr = values.filter(v => Number.isFinite(v)).sort((a,b) => a-b);
  if(!arr.length) return null;
  const idx = Math.max(0, Math.min(arr.length - 1, Math.round((arr.length - 1) * q)));
  return arr[idx];
}

function fmt(v, digits=2){
  return v === null || v === undefined || Number.isNaN(v) ? 'n/a' : Number(v).toFixed(digits);
}

function renderDatasetQc(){
  const root = document.getElementById('datasetQc');
  if(!root) return;
  const areas = data.rois.map(r => Number(r.area));
  const diamPx = areas.map(a => 2 * Math.sqrt(a / Math.PI));
  const pixelSize = Number(data.dataset?.pixel_size_microns);
  const diamUm = Number.isFinite(pixelSize) ? diamPx.map(v => v * pixelSize) : [];
  const noise = data.rois.map(r => Number(r.noiseSigma));
  const eventCounts = data.rois.map(r => eventsForRoi(r).length);
  const peakScores = data.rois.map(r => Number(r.peakScore));
  const priorityScores = data.rois.map(r => Number(r.priorityScore));
  const suggestions = data.discovery?.suggestions || [];
  const artifactCueCount = suggestions.filter(s => s.artifactCue && s.artifactCue !== 'none').length;
  const driftMax = Number(data.qc?.driftStats?.maxMagnitudePx);
  const satMax = Number(data.qc?.saturationStats?.maxFraction);
  const warnings = [];
  if(data.rois.length && quantile(diamPx, 0.5) < 8) warnings.push('Median ROI footprint is small in pixels; the detector may be capturing active cores or fragments rather than full somata.');
  if(Number.isFinite(pixelSize) && quantile(diamUm, 0.5) < 5) warnings.push('Median equivalent ROI diameter is below 5 microns with the configured pixel size.');
  if(suggestions.length > data.rois.length) warnings.push('Discovery suggestions outnumber current ROIs; review missed-neuron coverage before tightening thresholds.');
  if(artifactCueCount > suggestions.length * 0.25) warnings.push('Many discovery suggestions have artifact cues; inspect evidence maps for vessels, borders, or bright static structures.');
  if(Number.isFinite(driftMax) && driftMax >= 2) warnings.push('Estimated rigid drift exceeds 2 px; compare raw candidates against motion-sensitive evidence before accepting weak traces.');
  if(Number.isFinite(satMax) && satMax > 0.001) warnings.push('Saturation-like bright pixels appear in the frame stack; inspect raw max and artifact-risk candidates.');
  if(!Number.isFinite(pixelSize)) warnings.push('Pixel size is not set in the dataset manifest, so physical-size QC is disabled.');
  const qcWarnings = warnings.map(w => `<div class="qcWarning">${w}</div>`).join('') || '<div class="qcWarning">No QC warnings from the current lightweight checks.</div>';
  const maps = (data.discovery?.evidenceMaps || []).map(m => `
    <div class="qcMap">
      <img src="${m.file}" alt="${m.label}">
      <p class="hint">${m.label}</p>
    </div>`).join('');
  root.innerHTML = `
    <div class="metricGrid">
      <div class="metric"><b>${data.video.width} x ${data.video.height}</b><span>frame size</span></div>
      <div class="metric"><b>${data.video.frames}</b><span>frames</span></div>
      <div class="metric"><b>${data.rois.length}</b><span>candidate ROIs</span></div>
      <div class="metric"><b>${suggestions.length}</b><span>discovery suggestions</span></div>
      <div class="metric"><b>${fmt(quantile(areas, 0.5), 0)}</b><span>median ROI area px</span></div>
      <div class="metric"><b>${fmt(quantile(diamPx, 0.5), 1)}</b><span>median ROI diameter px</span></div>
      <div class="metric"><b>${diamUm.length ? fmt(quantile(diamUm, 0.5), 1) : 'n/a'}</b><span>median ROI diameter microns</span></div>
      <div class="metric"><b>${fmt(quantile(noise, 0.5), 4)}</b><span>median trace noise sigma</span></div>
      <div class="metric"><b>${fmt(quantile(eventCounts, 0.5), 0)}</b><span>median events per ROI</span></div>
      <div class="metric"><b>${fmt(quantile(peakScores, 0.5), 2)}</b><span>median peak score</span></div>
      <div class="metric"><b>${fmt(quantile(priorityScores, 0.5), 2)}</b><span>median priority score</span></div>
      <div class="metric"><b>${Number.isFinite(driftMax) ? fmt(driftMax, 2) : 'n/a'}</b><span>max drift px</span></div>
      <div class="metric"><b>${Number.isFinite(satMax) ? fmt(100 * satMax, 3) + '%' : 'n/a'}</b><span>max saturated fraction</span></div>
    </div>
    <div class="qcWarnings">${qcWarnings}</div>
    <div class="auditSplit">
      <div class="archCard">${auditRows('ROI area px', {min: Math.min(...areas), median: quantile(areas, 0.5), max: Math.max(...areas)})}</div>
      <div class="archCard">${auditRows('Events per ROI', {zero: eventCounts.filter(v => v === 0).length, one_to_three: eventCounts.filter(v => v >= 1 && v <= 3).length, four_plus: eventCounts.filter(v => v >= 4).length})}</div>
      <div class="archCard">${auditRows('Discovery artifact cues', {with_cue: artifactCueCount, no_cue: Math.max(0, suggestions.length - artifactCueCount)})}</div>
    </div>
    <h2>Evidence Maps</h2>
    <div class="qcMapGrid">${maps}</div>`;
}

function routePage(){
  const hash = (location.hash || '#review').replace(/^#\/?/, '');
  const page = hash === 'architecture' || hash === 'architecture-lab' ? 'architecture' : hash === 'metrics' || hash === 'audit' ? 'metrics' : hash === 'qc' || hash === 'dataset-qc' ? 'qc' : 'review';
  for(const id of ['reviewTab','reviewTabArch','reviewTabMetrics','reviewTabQc']) document.getElementById(id)?.classList.toggle('active', page === 'review');
  for(const id of ['architectureTab','architectureTabArch','architectureTabMetrics','architectureTabQc']) document.getElementById(id)?.classList.toggle('active', page === 'architecture');
  for(const id of ['metricsTab','metricsTabArch','metricsTabMetrics','metricsTabQc']) document.getElementById(id)?.classList.toggle('active', page === 'metrics');
  for(const id of ['qcTab','qcTabArch','qcTabMetrics','qcTabQc']) document.getElementById(id)?.classList.toggle('active', page === 'qc');
  document.getElementById('architecturePage').classList.toggle('hidden', page !== 'architecture');
  document.getElementById('metricsPage').classList.toggle('hidden', page !== 'metrics');
  document.getElementById('qcPage').classList.toggle('hidden', page !== 'qc');
  appRoot.classList.toggle('arch-mode', page === 'architecture');
  appRoot.classList.toggle('lab-mode', page === 'metrics');
  appRoot.classList.toggle('qc-mode', page === 'qc');
  if(page === 'architecture') renderArchitectureLab();
  else if(page === 'metrics') renderMetricsAudit();
  else if(page === 'qc') renderDatasetQc();
  else resizeOverlay();
}

async function boot(){
  populateEvidenceSelect();
  await loadAnnotations();
  initControls();
  renderParams();
  const first = visibleRois()[0] || data.rois[0];
  selectedId = first?.id || null;
  selectedRoiIds = new Set(selectedId ? [String(selectedId)] : []);
  if(selectedId) {
    selectedEventFrame = eventsForRoi(selectedRoi())[0]?.frame || null;
    roiNotes.value = roiAnn(selectedId).notes || '';
    eventNotes.value = selectedEventFrame ? eventAnn(selectedId, selectedEventFrame).notes || '' : '';
  }
  if(selectedSuggestionId) {
    document.getElementById('suggestionNotes').value = suggestionAnn(selectedSuggestionId).notes || '';
    document.getElementById('artifactClass').value = suggestionAnn(selectedSuggestionId).artifact_class || suggestionAnn(selectedSuggestionId).artifactClass || '';
  }
  setFrame(1);
  routePage();
  renderAll();
}
boot();
