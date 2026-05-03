// ── App state ──────────────────────────────────────────────────────────────
let phase = 'idle';   // 'idle' | 'running' | 'done'
let digestText = '';
let traceOpen = false;
let eventCount = 0;
let currentRunId = null;
let currentRunDate = '';
let currentDuration = 0;
let pastRuns = JSON.parse(localStorage.getItem('ra_past_runs') || '[]');

// ── Insights state ─────────────────────────────────────────────────────
let runStartedAt = 0;
let elapsedTimer = null;
const seenSubagents = new Set();
const stats = { events: 0, subagents: 0, arxiv: 0, web: 0, sources: 0 };
let tocObserver = null;

// ── DOM helpers ──────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

// ── Boot ───────────────────────────────────────────────────────────────────
window.addEventListener('DOMContentLoaded', () => {
  renderHistoryList();
  initViewSwitching();
  initModelSelects();

  $('query-input').addEventListener('input', updateRunBtn);
  $('query-input').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleRun(); }
  });
  $('run-btn').addEventListener('click', handleRun);
  $('settings-btn').addEventListener('click', highlightSettings);
  $('digest-export-btn').addEventListener('click', exportDigest);
  $('trace-toggle-btn').addEventListener('click', toggleTrace);

  $('set-agents').addEventListener('input', (e) => {
    $('agents-label').textContent = 'Max concurrent agents: ' + e.target.value;
  });
  $('set-iter').addEventListener('input', (e) => {
    $('iter-label').textContent = 'Max iterations: ' + e.target.value;
  });
});

// ── View switching (sidebar nav) ────────────────────────────────────────
function initViewSwitching() {
  const navItems = document.querySelectorAll('.nav-item[data-view]');
  const views = document.querySelectorAll('.view');

  function switchView(viewId) {
    navItems.forEach((n) => n.classList.toggle('active', n.dataset.view === viewId));
    views.forEach((v) => v.classList.toggle('active', v.id === `view-${viewId}`));
  }

  navItems.forEach((n) => n.addEventListener('click', () => switchView(n.dataset.view)));
}

// ── Generic custom select ───────────────────────────────────────────────
function initCustomSelect(wrap) {
  const trigger = wrap.querySelector('.custom-select-trigger');
  const menu    = wrap.querySelector('.custom-select-menu');

  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    const open = wrap.classList.toggle('open');
    trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
  });

  menu.addEventListener('click', (e) => {
    const opt = e.target.closest('.custom-select-option');
    if (!opt) return;
    setCustomSelectValue(wrap, opt.dataset.value);
    wrap.classList.remove('open');
    trigger.setAttribute('aria-expanded', 'false');
    wrap.dispatchEvent(new Event('change'));
  });

  document.addEventListener('click', (e) => {
    if (!wrap.contains(e.target)) {
      wrap.classList.remove('open');
      trigger.setAttribute('aria-expanded', 'false');
    }
  });
}

function setCustomSelectValue(wrap, value) {
  const valueEl = wrap.querySelector('.custom-select-value');
  const hidden  = wrap.querySelector('input[type="hidden"]');
  const options = wrap.querySelectorAll('.custom-select-option');
  hidden.value       = value;
  valueEl.textContent = value;
  options.forEach((o) => o.classList.toggle('selected', o.dataset.value === value));
}

function populateCustomSelect(wrapId, options, defaultValue) {
  const wrap    = $(wrapId);
  const menu    = wrap.querySelector('.custom-select-menu');
  const current = wrap.querySelector('input[type="hidden"]').value;
  const selected = options.includes(current) ? current : (defaultValue ?? options[0]);
  menu.innerHTML = options
    .map((o) => `<li class="custom-select-option${o === selected ? ' selected' : ''}" role="option" data-value="${o}">${o}</li>`)
    .join('');
  setCustomSelectValue(wrap, selected);
}

function getCustomSelectValue(wrapId) {
  return $(wrapId).querySelector('input[type="hidden"]').value;
}

// ── Model selects (provider → model cascade) ────────────────────────────
let modelsData = {};

async function initModelSelects() {
  try {
    const resp = await fetch('/api/models');
    modelsData = await resp.json();
  } catch (_) {
    modelsData = {
      ollama: ['gemma4:e2b', 'phi4-mini:3.8b'],
      openai: ['gpt-5-nano', 'gpt-4o-mini', 'gpt-5.1'],
    };
  }

  ['set-orch-provider', 'set-orch-model', 'set-res-provider', 'set-res-model'].forEach((id) =>
    initCustomSelect($(id))
  );

  const providers = Object.keys(modelsData);
  populateCustomSelect('set-orch-provider', providers, providers[0]);
  populateCustomSelect('set-res-provider', providers, providers[1] ?? providers[0]);
  updateModelOptions('orch');
  updateModelOptions('res');

  $('set-orch-provider').addEventListener('change', () => updateModelOptions('orch'));
  $('set-res-provider').addEventListener('change', () => updateModelOptions('res'));
}

function updateModelOptions(prefix) {
  const provider = getCustomSelectValue(`set-${prefix}-provider`);
  const models   = modelsData[provider] || [];
  populateCustomSelect(`set-${prefix}-model`, models);
}

// ── Settings highlight (scroll sidebar into view + pulse) ───────────────
function highlightSettings() {
  const el = $('sidebar-settings');
  el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  el.classList.remove('highlight');
  void el.offsetWidth;
  el.classList.add('highlight');
  el.addEventListener('animationend', () => el.classList.remove('highlight'), { once: true });
}

// ── Run button state ───────────────────────────────────────────────────────
function updateRunBtn() {
  const btn = $('run-btn');
  const hasText = $('query-input').value.trim().length > 0;
  const active = hasText && phase !== 'running';
  btn.disabled = !active;
  btn.classList.toggle('active', active);
}

// ── Trace panel toggle ─────────────────────────────────────────────────────
function toggleTrace() {
  traceOpen = !traceOpen;
  $('trace-body').style.display     = traceOpen ? 'block' : 'none';
  $('trace-chevron').style.transform = traceOpen ? 'rotate(180deg)' : 'none';
}

// ── Transition to running state ────────────────────────────────────────────
function setRunning() {
  phase = 'running';
  digestText = '';
  eventCount = 0;

  const qc = $('query-card');
  qc.style.borderColor = 'oklch(0.78 0.08 252)';
  qc.style.boxShadow   = '0 0 0 3px oklch(0.52 0.16 252 / 0.08)';

  const btn = $('run-btn');
  btn.disabled = true;
  btn.classList.remove('active');
  btn.innerHTML = '<span style="display:inline-block;width:12px;height:12px;border:2px solid oklch(0.55 0.01 240);border-top-color:transparent;border-radius:50%;animation:spin 0.7s linear infinite;"></span>Running…';

  $('header-progress').classList.add('running');

  // Reset insights
  resetInsights();
  $('rail-idle').style.display = 'none';
  $('insights-card').classList.remove('done');
  $('insights-eyebrow').textContent = 'LIVE';
  $('insights-card').style.display = 'block';
  $('toc-card').style.display = 'none';
  runStartedAt = performance.now();
  if (elapsedTimer) clearInterval(elapsedTimer);
  elapsedTimer = setInterval(updateElapsed, 100);
  setInsightsStatus('Initializing run…');

  $('trace-rows').innerHTML = '';
  $('trace-panel').style.display = 'block';
  $('trace-label').textContent = 'Agent running…';
  $('trace-label').style.color = 'oklch(0.42 0.14 252)';
  $('trace-dot').style.display = 'inline-block';
  $('event-count').textContent  = '0 events';
  traceOpen = false;
  $('trace-body').style.display     = 'none';
  $('trace-chevron').style.transform = 'none';

  $('digest-panel').style.display       = 'none';
  $('digest-stream').textContent        = '';
  $('digest-stream').style.display      = 'block';
  $('digest-md').style.display          = 'none';
  $('digest-md').innerHTML              = '';
  $('digest-status').style.display      = 'inline';
  $('digest-export-btn').style.display  = 'none';
  $('sources-section').style.display    = 'none';
  $('sources-grid').innerHTML           = '';
  $('run-complete').style.display       = 'none';
  $('idle-hint').style.display          = 'none';
}

// ── Transition to done state ───────────────────────────────────────────────
function setDone(durationS, runDate) {
  phase = 'done';
  currentDuration = durationS;
  currentRunDate  = runDate;

  const qc = $('query-card');
  qc.style.borderColor = 'oklch(0.9 0.006 240)';
  qc.style.boxShadow   = '0 1px 4px oklch(0.1 0.01 240 / 0.05)';

  $('run-btn').innerHTML = '<span class="run-btn-icon">&#9654;</span> Run Research';
  updateRunBtn();

  $('header-progress').classList.remove('running');

  if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null; }
  $('insights-card').classList.add('done');
  $('insights-eyebrow').textContent = 'SUMMARY';
  setInsightsStatus('Run complete · ' + durationS.toFixed(1) + 's');

  $('trace-label').textContent = 'Agent Trace';
  $('trace-label').style.color = 'oklch(0.55 0.01 240)';
  $('trace-dot').style.display = 'none';

  $('digest-status').style.display     = 'none';
  $('digest-stream').style.display     = 'none';
  $('digest-export-btn').style.display = 'flex';
  const mdEl = $('digest-md');
  mdEl.innerHTML   = marked.parse(digestText);
  mdEl.style.display = 'block';
  buildToc(mdEl);

  const sourceCount = $('sources-grid').children.length;
  $('run-meta').textContent =
    `${sourceCount} sources · ${durationS.toFixed(1)}s · ${runDate}`;
  $('run-complete').style.display = 'flex';
}

// ── Append a trace row ─────────────────────────────────────────────────────
const TRACE_COLORS = {
  agent:    { bg: 'oklch(0.96 0.008 240)', text: 'oklch(0.35 0.01 240)', dot: 'oklch(0.55 0.01 240)' },
  tool:     { bg: 'oklch(0.97 0.05 252)',  text: 'oklch(0.42 0.12 252)', dot: 'oklch(0.52 0.16 252)' },
  subagent: { bg: 'oklch(0.97 0.05 145)',  text: 'oklch(0.38 0.12 145)', dot: 'oklch(0.55 0.15 145)' },
};

const AGENT_LANE_COLORS = [
  'oklch(0.52 0.16 252)',
  'oklch(0.52 0.15 145)',
  'oklch(0.55 0.14 30)',
  'oklch(0.50 0.14 300)',
  'oklch(0.50 0.12 60)',
  'oklch(0.45 0.14 200)',
];

let parallelContainer = null;
let activeLanes = {};

function getOrCreateParallelContainer() {
  if (!parallelContainer || !parallelContainer.parentNode) {
    parallelContainer = document.createElement('div');
    parallelContainer.className = 'trace-parallel-container';
    $('trace-rows').appendChild(parallelContainer);
  }
  return parallelContainer;
}

function getOrCreateLane(agentId) {
  const container = getOrCreateParallelContainer();
  if (!activeLanes[agentId]) {
    const lane = document.createElement('div');
    lane.className = 'trace-lane';
    const colorIdx = (agentId - 1) % AGENT_LANE_COLORS.length;
    lane.style.borderTopColor = AGENT_LANE_COLORS[colorIdx];
    const header = document.createElement('div');
    header.className = 'trace-lane-header';
    header.style.color = AGENT_LANE_COLORS[colorIdx];
    header.textContent = `Agent #${agentId}`;
    lane.appendChild(header);
    container.appendChild(lane);
    activeLanes[agentId] = lane;
  }
  return activeLanes[agentId];
}

function endParallelContainer() {
  parallelContainer = null;
  activeLanes = {};
}

function appendTraceRow(ev) {
  eventCount++;
  $('event-count').textContent = `${eventCount} events`;

  const c = TRACE_COLORS[ev.event_type] || TRACE_COLORS.agent;
  const agentId = ev.agent_id;

  // If this event belongs to a sub-agent, render in a lane
  if (agentId) {
    const lane = getOrCreateLane(agentId);
    const row = buildTraceRowEl(ev, c);
    lane.appendChild(row);
  } else {
    // Root-level event — end any parallel container and append normally
    if (parallelContainer) endParallelContainer();
    const row = buildTraceRowEl(ev, c);
    $('trace-rows').appendChild(row);
  }

  const body = $('trace-body');
  body.scrollTop = body.scrollHeight;
}

function buildTraceRowEl(ev, c) {
  const row = document.createElement('div');
  row.className = 'trace-row-enter';
  row.style.cssText = 'display:flex;gap:10px;align-items:flex-start;margin-bottom:6px;';

  const detailId = `detail-${eventCount}`;
  const hasDetail = ev.detail && ev.detail.trim().length > 0;
  const detailHtml = hasDetail
    ? `<button class="trace-detail-toggle" data-detail-id="${detailId}">▶ show detail</button><pre id="${detailId}" class="trace-detail-pre">${escapeHtml(ev.detail)}</pre>`
    : '';

  row.innerHTML = `
    <div style="flex-shrink:0;padding-top:4px;">
      <div style="width:7px;height:7px;border-radius:50%;background:${c.dot};"></div>
    </div>
    <div style="flex:1;min-width:0;">
      <div style="display:flex;align-items:center;gap:6px;margin-bottom:2px;">
        <span style="font-family:'DM Mono',monospace;font-size:0.68rem;color:oklch(0.65 0.01 240);">${ev.ts}</span>
        <span style="font-size:0.7rem;font-weight:600;padding:1px 5px;border-radius:4px;background:${c.bg};color:${c.text};">${ev.label}</span>
      </div>
      <div style="font-size:0.82rem;color:oklch(0.28 0.01 240);line-height:1.4;">${ev.message}</div>
      ${detailHtml}
    </div>
  `;

  const toggleBtn = row.querySelector('.trace-detail-toggle');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      toggleDetail(detailId, toggleBtn);
    });
  }

  return row;
}

function toggleDetail(id, btn) {
  const el = $(id);
  if (!el) return;
  const showing = el.style.display === 'block';
  el.style.display = showing ? 'none' : 'block';
  btn.textContent = showing ? '▶ show detail' : '▼ hide detail';
}

function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

// ── Append a source card ───────────────────────────────────────────────────
function appendSourceCard(source, rank) {
  const isArxiv   = source.source_type === 'arxiv';
  const badgeBg   = isArxiv ? 'oklch(0.95 0.06 252)'  : 'oklch(0.95 0.06 145)';
  const badgeText = isArxiv ? 'oklch(0.42 0.14 252)'  : 'oklch(0.38 0.12 145)';
  const barColor  = isArxiv ? 'oklch(0.52 0.16 252)'  : 'oklch(0.52 0.15 145)';
  const label     = isArxiv ? 'arXiv' : 'web';
  const scorePct  = Math.round((source.score || 0) * 100);

  const card = document.createElement('a');
  card.href   = source.url || '#';
  card.target = '_blank';
  card.rel    = 'noreferrer';
  card.className = 'source-card';
  card.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;">
      <div style="display:flex;align-items:center;gap:6px;">
        <span class="source-rank">${rank}</span>
        <span style="font-size:0.67rem;font-weight:600;padding:2px 7px;border-radius:4px;background:${badgeBg};color:${badgeText};font-family:'DM Mono',monospace;letter-spacing:0.03em;">${label}</span>
      </div>
      <span style="font-size:0.72rem;font-weight:600;padding:2px 8px;border-radius:5px;background:${badgeBg};color:${badgeText};font-family:'DM Mono',monospace;">${(source.score||0).toFixed(2)}</span>
    </div>
    <div class="source-title">${source.title || ''}</div>
    <div class="source-snippet">${source.snippet || ''}</div>
    <div style="display:flex;align-items:center;justify-content:space-between;margin-top:2px;">
      <span class="source-meta">${source.domain || ''} · ${source.date || ''}</span>
      <div class="source-bar-bg">
        <div style="width:${scorePct}%;height:100%;background:${barColor};border-radius:2px;"></div>
      </div>
    </div>
  `;
  $('sources-grid').appendChild(card);
}

// ── Main run handler ───────────────────────────────────────────────────────
async function handleRun() {
  const query = $('query-input').value.trim();
  if (!query || phase === 'running') return;

  setRunning();

  const orchProvider = getCustomSelectValue('set-orch-provider');
  const orchModel    = getCustomSelectValue('set-orch-model');
  const resProvider  = getCustomSelectValue('set-res-provider');
  const resModel     = getCustomSelectValue('set-res-model');
  const maxAgents    = parseInt($('set-agents').value);
  const maxIter      = parseInt($('set-iter').value);

  let runId;
  try {
    const resp = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        orchestrator_provider: orchProvider,
        orchestrator_model_name: orchModel,
        researcher_provider: resProvider,
        researcher_model_name: resModel,
        max_agents: maxAgents,
        max_iter: maxIter,
      }),
    });
    ({ run_id: runId } = await resp.json());
  } catch (err) {
    showToast('Failed to start run: ' + err.message);
    phase = 'idle';
    updateRunBtn();
    return;
  }
  currentRunId = runId;

  const es = new EventSource(`/api/stream/${runId}`);

  es.onmessage = (e) => {
    const ev = JSON.parse(e.data);

    if (ev.type === 'trace') {
      appendTraceRow(ev);
      updateInsightsFromTrace(ev);

    } else if (ev.type === 'digest') {
      setInsightsStatus('Writing digest…');
      if (!digestText) {
        $('digest-panel').style.display = 'block';
      }
      digestText += ev.token;
      const streamEl = $('digest-stream');
      streamEl.textContent = digestText;
      const cursor = document.createElement('span');
      cursor.className = 'cursor-blink';
      streamEl.appendChild(cursor);

    } else if (ev.type === 'sources') {
      $('sources-section').style.display = 'block';
      const arr = ev.sources || [];
      arr.forEach((s, i) => appendSourceCard(s, i + 1));
      stats.sources += arr.length;
      bumpStat('stat-sources', stats.sources);

    } else if (ev.type === 'done') {
      es.close();
      setDone(ev.duration_s || 0, ev.run_date || '');
      savePastRun(query, ev);

    } else if (ev.type === 'error') {
      es.close();
      phase = 'idle';
      $('run-btn').innerHTML = '<span class="run-btn-icon">&#9654;</span> Run Research';
      updateRunBtn();
      $('header-progress').classList.remove('running');
      if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null; }
      $('insights-card').style.display = 'none';
      $('rail-idle').style.display = 'flex';
      const qc = $('query-card');
      qc.style.borderColor = 'oklch(0.9 0.006 240)';
      qc.style.boxShadow = '0 1px 4px oklch(0.1 0.01 240 / 0.05)';
      showToast('Agent error: ' + ev.message);
    }
  };

  es.onerror = () => {
    es.close();
    if (phase === 'running') {
      phase = 'idle';
      $('run-btn').innerHTML = '<span class="run-btn-icon">&#9654;</span> Run Research';
      updateRunBtn();
      $('header-progress').classList.remove('running');
      if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null; }
      $('insights-card').style.display = 'none';
      $('rail-idle').style.display = 'flex';
    }
  };
}

// ── Past runs ──────────────────────────────────────────────────────────────
function savePastRun(query, doneEv) {
  const run = {
    id: currentRunId,
    label: query.slice(0, 50),
    date: doneEv.run_date || '',
    query,
    digest: digestText,
    duration_s: doneEv.duration_s || 0,
  };
  pastRuns.unshift(run);
  if (pastRuns.length > 10) pastRuns = pastRuns.slice(0, 10);
  localStorage.setItem('ra_past_runs', JSON.stringify(pastRuns));
  renderHistoryList();
}

function renderHistoryList() {
  const list = $('history-list');
  const empty = $('history-empty');
  if (!list) return;

  list.innerHTML = '';
  if (pastRuns.length === 0) {
    if (empty) empty.style.display = 'block';
    return;
  }

  if (empty) empty.style.display = 'none';
  pastRuns.forEach((r) => {
    const card = document.createElement('div');
    card.className = 'history-card';
    card.innerHTML = `
      <div class="history-card-query">${escapeHtml(r.query)}</div>
      <div class="history-card-meta">
        <span>${r.date}</span>
        <span>·</span>
        <span>${(r.duration_s || 0).toFixed(1)}s</span>
      </div>
    `;
    card.addEventListener('click', () => {
      onSelectPastRun(r.id);
      document.querySelector('.nav-item[data-view="research"]')?.click();
    });
    list.appendChild(card);
  });
}

function onSelectPastRun(runId) {
  const run = pastRuns.find((r) => r.id === runId);
  if (!run) return;

  phase      = 'done';
  digestText = run.digest;
  currentRunDate  = run.date;
  currentDuration = run.duration_s;
  currentRunId    = run.id;

  $('idle-hint').style.display          = 'none';
  $('trace-panel').style.display        = 'none';
  $('digest-panel').style.display       = 'block';
  $('digest-stream').style.display      = 'none';
  $('digest-status').style.display      = 'none';
  $('digest-export-btn').style.display  = 'flex';
  const mdEl = $('digest-md');
  mdEl.innerHTML   = marked.parse(run.digest);
  mdEl.style.display = 'block';
  buildToc(mdEl);
  $('insights-card').style.display = 'none';
  $('rail-idle').style.display = 'none';
  $('sources-section').style.display    = 'none';
  $('sources-grid').innerHTML           = '';
  $('run-meta').textContent = `${(run.duration_s||0).toFixed(1)}s · ${run.date}`;
  $('run-complete').style.display = 'flex';
  $('query-input').value = run.query;
  updateRunBtn();
}

// ── Toast notifications ───────────────────────────────────────────────────
function showToast(message, type = 'error', durationMs = 5000) {
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = message;
  document.body.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; el.style.transition = 'opacity 0.3s'; }, durationMs - 300);
  setTimeout(() => el.remove(), durationMs);
}

// ── Export ─────────────────────────────────────────────────────────────────
function exportDigest() {
  if (!digestText) return;
  const query   = $('query-input').value.trim();
  const content = `# Research Digest — ${currentRunDate}\n\n**Query:** ${query}\n\n---\n\n${digestText}`;
  const blob    = new Blob([content], { type: 'text/markdown;charset=utf-8' });
  const url     = URL.createObjectURL(blob);
  const a       = document.createElement('a');
  a.href     = url;
  a.download = `digest-${currentRunId || 'export'}.md`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// ── Insights helpers ────────────────────────────────────────────────────
function resetInsights() {
  stats.events = 0; stats.subagents = 0; stats.arxiv = 0; stats.web = 0; stats.sources = 0;
  seenSubagents.clear();
  ['stat-events', 'stat-subagents', 'stat-arxiv', 'stat-web', 'stat-sources'].forEach((id) => {
    const el = $(id); if (el) el.textContent = '0';
  });
  $('insights-elapsed').textContent = '0.0s';
}

function updateElapsed() {
  const s = (performance.now() - runStartedAt) / 1000;
  $('insights-elapsed').textContent = s.toFixed(1) + 's';
}

function setInsightsStatus(text) {
  const el = $('insights-status');
  if (el) el.textContent = text;
}

function bumpStat(id, value) {
  const el = $(id);
  if (!el) return;
  el.textContent = String(value);
  const card = el.closest('.insights-stat');
  if (!card) return;
  card.classList.remove('bumped');
  void card.offsetWidth;
  card.classList.add('bumped');
}

function updateInsightsFromTrace(ev) {
  stats.events++;
  bumpStat('stat-events', stats.events);

  if (ev.event_type === 'subagent') {
    setInsightsStatus(ev.label + ' • ' + ev.message);
  } else if (ev.event_type === 'tool') {
    const label = (ev.label || '').toLowerCase();
    if (label === 'task') {
      setInsightsStatus('Sub-agent finished…');
    } else if (label.includes('arxiv')) {
      stats.arxiv++;
      bumpStat('stat-arxiv', stats.arxiv);
      setInsightsStatus('Querying arXiv…');
    } else if (label.includes('tavily') || label.includes('web')) {
      stats.web++;
      bumpStat('stat-web', stats.web);
      setInsightsStatus('Searching the web…');
    } else if (label.includes('think')) {
      setInsightsStatus('Reflecting…');
    } else {
      setInsightsStatus('Tool: ' + ev.label);
    }
  } else if (ev.event_type === 'agent') {
    const msg = ev.message || '';
    const m = msg.match(/Dispatching:\s*(.+)/i);
    if (m) {
      const taskCount = m[1].split(',').filter((n) => n.trim().toLowerCase() === 'task').length;
      if (taskCount > 0) {
        stats.subagents += taskCount;
        bumpStat('stat-subagents', stats.subagents);
      }
    }
    setInsightsStatus('Orchestrator: ' + msg);
  }
}

// ── Table of contents ──────────────────────────────────────────────────
function buildToc(mdEl) {
  const list = $('toc-list');
  const card = $('toc-card');
  if (!list || !card) return;
  list.innerHTML = '';
  if (tocObserver) { tocObserver.disconnect(); tocObserver = null; }

  const headings = mdEl.querySelectorAll('h1, h2, h3');
  if (headings.length < 2) {
    card.style.display = 'none';
    return;
  }

  const links = [];
  headings.forEach((h, i) => {
    if (!h.id) {
      const slug = (h.textContent || `s-${i}`)
        .toLowerCase().trim()
        .replace(/[^\w\s-]/g, '').replace(/\s+/g, '-').slice(0, 60) || `s-${i}`;
      h.id = `toc-${i}-${slug}`;
    }
    const li = document.createElement('li');
    const a = document.createElement('a');
    a.href = '#' + h.id;
    a.textContent = h.textContent;
    a.className = 'toc-link toc-' + h.tagName.toLowerCase();
    a.addEventListener('click', (e) => {
      e.preventDefault();
      h.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    li.appendChild(a);
    list.appendChild(li);
    links.push({ a, h });
  });

  card.style.display = 'block';

  // Active highlighting via scroll listener (scroll happens inside .view-scroll, not window)
  const scrollEl = mdEl.closest('.view-scroll');
  if (!scrollEl) return;
  const updateActive = () => {
    const scTop = scrollEl.getBoundingClientRect().top;
    let current = links[0];
    for (const item of links) {
      const top = item.h.getBoundingClientRect().top - scTop;
      if (top - 80 <= 0) current = item; else break;
    }
    links.forEach(({ a }) => a.classList.toggle('active', a === current.a));
  };
  scrollEl.addEventListener('scroll', updateActive, { passive: true });
  updateActive();
}
