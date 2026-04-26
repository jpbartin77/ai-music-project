"""
demo_server.py — Animated pipeline dashboard for the AI Music Project demo.

Start this before practice_session.py, then open http://localhost:5000 in a browser.
Set DEMO_SERVER_URL=http://localhost:5000 in .env.tpl to enable event emission.

Usage:
    op run --env-file=.env.tpl -- python src/demo_server.py
"""

import json
import queue
import threading
import time
from flask import Flask, Response, request, render_template_string

app = Flask(__name__)
_clients: list[queue.Queue] = []
_clients_lock = threading.Lock()

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>AI Music Pipeline</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: #0a1628;
    color: #e0f0ff;
    font-family: 'Segoe UI', system-ui, sans-serif;
    height: 100vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  header {
    padding: 14px 28px;
    background: #0d1f38;
    border-bottom: 1px solid #1e3a5f;
    display: flex;
    align-items: center;
    gap: 14px;
  }
  header h1 { font-size: 1.15rem; font-weight: 600; color: #7dd3fc; letter-spacing: .02em; }
  header .subtitle { font-size: .8rem; color: #64748b; }

  .status-pill {
    margin-left: auto;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: .72rem;
    font-weight: 600;
    background: #1e3a5f;
    color: #7dd3fc;
    border: 1px solid #2d5a8e;
    transition: all .3s;
  }
  .status-pill.active { background: #065f46; color: #6ee7b7; border-color: #059669; }
  .status-pill.analyzing { background: #4c1d95; color: #c4b5fd; border-color: #7c3aed; }

  .main { display: flex; flex: 1; overflow: hidden; }

  /* ── Pipeline diagram ── */
  .diagram-wrap {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
  }

  svg#pipeline {
    width: 100%;
    max-width: 860px;
    height: auto;
  }

  /* Skill node — purple accent distinguishes AI-layer from infrastructure nodes */
  #node-skill rect { stroke: #7c3aed; fill: #1a0a38; }
  #node-skill text { fill: #c4b5fd; }
  #node-skill .sub  { fill: #7c5cbf; }
  #node-skill.active rect { fill: #2e1065; stroke: #a855f7; stroke-width: 2; filter: drop-shadow(0 0 8px #a855f780); }
  #node-skill.active text { fill: #e9d5ff; }
  #node-skill.done rect   { fill: #052e16; stroke: #22c55e; stroke-width: 1.8; filter: drop-shadow(0 0 6px #22c55e60); }
  #node-skill.done text   { fill: #bbf7d0; }

  .status-pill.done { background: #065f46; color: #6ee7b7; border-color: #059669; }

  /* Node base */
  .node rect, .node .cyl-body, .node ellipse {
    fill: #0f2744;
    stroke: #2d5a8e;
    stroke-width: 1.5;
    transition: fill .25s, stroke .25s, filter .25s;
  }
  .node text { fill: #a8c8f0; font-size: 12px; font-weight: 500; transition: fill .25s; }
  .node .sub  { fill: #5a7a9a; font-size: 10px; }
  .node .icon { font-size: 16px; }

  /* Active state */
  .node.active rect, .node.active .cyl-body, .node.active ellipse {
    fill: #0c3d6b;
    stroke: #38bdf8;
    stroke-width: 2;
    filter: drop-shadow(0 0 8px #38bdf880);
  }
  .node.active text { fill: #e0f2fe; }

  /* Done state */
  .node.done rect, .node.done .cyl-body, .node.done ellipse {
    fill: #052e16;
    stroke: #22c55e;
    stroke-width: 1.8;
    filter: drop-shadow(0 0 6px #22c55e60);
  }
  .node.done text { fill: #bbf7d0; }

  /* Pulse animation */
  @keyframes pulse-ring {
    0%   { stroke-opacity: .9; stroke-width: 2; }
    100% { stroke-opacity: 0;  stroke-width: 10; }
  }
  .pulse-ring {
    fill: none;
    stroke: #38bdf8;
    animation: pulse-ring 1s ease-out infinite;
    pointer-events: none;
  }

  /* Arrows */
  .arrow { stroke: #2d5a8e; stroke-width: 1.5; fill: none; marker-end: url(#arr); }
  .arrow.active { stroke: #38bdf8; stroke-width: 2; }
  .arrow.done   { stroke: #22c55e; stroke-width: 1.8; }

  /* Animated dot on active arrows */
  @keyframes travel {
    from { offset-distance: 0%; }
    to   { offset-distance: 100%; }
  }
  .travel-dot {
    width: 8px; height: 8px;
    background: #38bdf8;
    border-radius: 50%;
    position: absolute;
    offset-path: path('M0,0'); /* overridden per-arrow in JS */
    animation: travel 1s linear infinite;
    display: none;
  }

  /* Checkmark badge */
  .check { display: none; }
  .node.done .check { display: inline; }

  /* ── Right sidebar ── */
  .sidebar {
    width: 280px;
    background: #0d1f38;
    border-left: 1px solid #1e3a5f;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .sidebar-section {
    padding: 12px 14px 8px;
    border-bottom: 1px solid #1a2f4a;
    font-size: .72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: .06em;
    color: #4a6a8a;
  }

  #note-log {
    flex: 1;
    overflow-y: auto;
    padding: 8px 14px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: .75rem;
    line-height: 1.7;
    color: #7dd3fc;
  }
  #note-log .rh { color: #6ee7b7; }
  #note-log .lh { color: #a78bfa; }
  #note-log .seg { color: #fbbf24; border-top: 1px solid #1e3a5f; padding-top: 4px; margin-top: 4px; }
  #note-log .sys { color: #64748b; font-style: italic; }

  .stage-list {
    padding: 10px 14px;
    font-size: .78rem;
    line-height: 2;
  }
  .stage { color: #4a6a8a; display: flex; align-items: center; gap: 8px; }
  .stage .dot { width: 8px; height: 8px; border-radius: 50%; background: #1e3a5f; flex-shrink: 0; transition: background .3s; }
  .stage.active { color: #7dd3fc; }
  .stage.active .dot { background: #38bdf8; box-shadow: 0 0 6px #38bdf8; }
  .stage.done { color: #6ee7b7; }
  .stage.done .dot { background: #22c55e; }
</style>
</head>
<body>

<header>
  <span style="font-size:1.6rem">🎹</span>
  <div>
    <h1>AI Music Pipeline</h1>
    <div class="subtitle">Piano → Splunk → Claude → Webex</div>
  </div>
  <div class="status-pill" id="status-pill">Waiting for session</div>
</header>

<div class="main">

  <!-- Pipeline SVG -->
  <div class="diagram-wrap">
  <svg id="pipeline" viewBox="0 0 1020 590" xmlns="http://www.w3.org/2000/svg">
    <defs>
      <marker id="arr" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
        <path d="M0,0 L0,6 L8,3 z" fill="#2d5a8e"/>
      </marker>
      <marker id="arr-active" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
        <path d="M0,0 L0,6 L8,3 z" fill="#38bdf8"/>
      </marker>
      <marker id="arr-done" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">
        <path d="M0,0 L0,6 L8,3 z" fill="#22c55e"/>
      </marker>
    </defs>

    <!-- ── Arrows (behind nodes) ── -->
    <!-- Piano → practice_session -->
    <path id="arr-piano-session" class="arrow" d="M140,100 L140,162"/>
    <!-- practice_session → Splunk -->
    <path id="arr-session-splunk" class="arrow" d="M140,242 L140,422"/>
    <!-- practice_session → Coach -->
    <path id="arr-session-coach" class="arrow" d="M220,202 L430,202"/>
    <!-- Coach → Coaching Skill -->
    <path id="arr-coach-skill" class="arrow" d="M525,242 L505,302"/>
    <!-- Coaching Skill → mcp_server -->
    <path id="arr-skill-mcp" class="arrow" d="M450,357 L355,418"/>
    <!-- mcp_server → Splunk -->
    <path id="arr-mcp-splunk" class="arrow" d="M278,448 L220,462"/>
    <!-- Coaching Skill → charts -->
    <path id="arr-skill-charts" class="arrow" d="M560,357 L628,418"/>
    <!-- Coach → webex_delivery -->
    <path id="arr-coach-webex" class="arrow" d="M625,202 L775,202"/>
    <!-- webex_delivery → Webex Space -->
    <path id="arr-webex-space" class="arrow" d="M858,242 L858,422"/>

    <!-- ── Nodes ── -->

    <!-- Piano -->
    <g id="node-piano" class="node" transform="translate(40,40)">
      <rect width="200" height="60" rx="10"/>
      <text x="100" y="22" text-anchor="middle" class="icon">🎹</text>
      <text x="100" y="40" text-anchor="middle" font-weight="600">Piano (USB MIDI)</text>
      <text x="100" y="54" text-anchor="middle" class="sub">88-key keyboard</text>
      <text x="180" y="18" class="check" font-size="14">✅</text>
    </g>

    <!-- practice_session -->
    <g id="node-session" class="node" transform="translate(40,162)">
      <rect width="200" height="80" rx="10"/>
      <text x="100" y="22" text-anchor="middle" class="icon">🖥️</text>
      <text x="100" y="42" text-anchor="middle" font-weight="600">practice_session.py</text>
      <text x="100" y="57" text-anchor="middle" class="sub">MIDI capture</text>
      <text x="100" y="70" text-anchor="middle" class="sub">+ scoring</text>
      <text x="180" y="18" class="check" font-size="14">✅</text>
    </g>

    <!-- Splunk -->
    <g id="node-splunk" class="node" transform="translate(40,422)">
      <ellipse cx="100" cy="14" rx="100" ry="14"/>
      <rect class="cyl-body" x="0" y="12" width="200" height="72" rx="0"/>
      <ellipse cx="100" cy="84" rx="100" ry="14"/>
      <text x="100" y="54" text-anchor="middle" font-weight="600">Splunk</text>
      <text x="100" y="69" text-anchor="middle" class="sub">index=edge_hub_mqtt</text>
      <text x="178" y="30" class="check" font-size="14">✅</text>
    </g>

    <!-- Coach Agent -->
    <g id="node-coach" class="node" transform="translate(430,162)">
      <rect width="200" height="80" rx="10"/>
      <text x="100" y="22" text-anchor="middle" class="icon">🤖</text>
      <text x="100" y="42" text-anchor="middle" font-weight="600">Coach Agent</text>
      <text x="100" y="57" text-anchor="middle" class="sub">claude-opus-4-7</text>
      <text x="100" y="70" text-anchor="middle" class="sub">AI orchestrator</text>
      <text x="180" y="18" class="check" font-size="14">✅</text>
    </g>

    <!-- Coaching Skill (AI layer) -->
    <g id="node-skill" class="node" transform="translate(410,302)">
      <rect width="200" height="55" rx="8"/>
      <text x="100" y="20" text-anchor="middle" class="icon">💡</text>
      <text x="100" y="38" text-anchor="middle" font-weight="600">Coaching Skill</text>
      <text x="100" y="51" text-anchor="middle" class="sub">analyze · chart · report</text>
      <text x="180" y="16" class="check" font-size="14">✅</text>
    </g>

    <!-- mcp_server -->
    <g id="node-mcp" class="node" transform="translate(268,418)">
      <rect width="185" height="60" rx="10"/>
      <text x="92" y="22" text-anchor="middle" class="icon">🗄️</text>
      <text x="92" y="40" text-anchor="middle" font-weight="600">mcp_server.py</text>
      <text x="92" y="54" text-anchor="middle" class="sub">SPL → Splunk REST</text>
      <text x="165" y="18" class="check" font-size="14">✅</text>
    </g>

    <!-- charts -->
    <g id="node-charts" class="node" transform="translate(580,418)">
      <rect width="165" height="60" rx="10"/>
      <text x="82" y="22" text-anchor="middle" class="icon">📊</text>
      <text x="82" y="40" text-anchor="middle" font-weight="600">charts.py</text>
      <text x="82" y="54" text-anchor="middle" class="sub">PNG panel</text>
      <text x="145" y="18" class="check" font-size="14">✅</text>
    </g>

    <!-- webex_delivery -->
    <g id="node-webex-delivery" class="node" transform="translate(775,162)">
      <rect width="200" height="80" rx="10"/>
      <text x="100" y="22" text-anchor="middle" class="icon">🚚</text>
      <text x="100" y="42" text-anchor="middle" font-weight="600">webex_delivery</text>
      <text x="100" y="57" text-anchor="middle" class="sub">Adaptive Card</text>
      <text x="100" y="70" text-anchor="middle" class="sub">+ chart PNG</text>
      <text x="180" y="18" class="check" font-size="14">✅</text>
    </g>

    <!-- Webex Space -->
    <g id="node-webex-space" class="node" transform="translate(775,422)">
      <rect width="200" height="70" rx="10"/>
      <text x="100" y="24" text-anchor="middle" class="icon">💬</text>
      <text x="100" y="44" text-anchor="middle" font-weight="600">Webex Space</text>
      <text x="100" y="58" text-anchor="middle" class="sub">Coaching card</text>
      <text x="180" y="18" class="check" font-size="14">✅</text>
    </g>

    <!-- Arrow labels -->
    <text x="248" y="133" font-size="9" fill="#4a6a8a">MIDI events</text>
    <text x="248" y="352" font-size="9" fill="#4a6a8a">HEC POST</text>
    <text x="316" y="195" font-size="9" fill="#4a6a8a">session end</text>
    <text x="536" y="293" font-size="9" fill="#7c3aed">skill invoke</text>
    <text x="348" y="388" font-size="9" fill="#4a6a8a">tool calls</text>
    <text x="688" y="195" font-size="9" fill="#4a6a8a">coaching JSON</text>
    <text x="787" y="390" font-size="9" fill="#4a6a8a">Adaptive Card</text>
  </svg>
  </div>

  <!-- Sidebar -->
  <div class="sidebar">
    <div class="sidebar-section">Live Notes</div>
    <div id="note-log"><span class="sys">Waiting for session...</span></div>

    <div class="sidebar-section">Pipeline Stages</div>
    <div class="stage-list">
      <div class="stage" id="stage-capture"><span class="dot"></span>MIDI Capture</div>
      <div class="stage" id="stage-splunk"><span class="dot"></span>Splunk Publish</div>
      <div class="stage" id="stage-coach"><span class="dot"></span>Coach Analysis</div>
      <div class="stage" id="stage-mcp"><span class="dot"></span>MCP Queries</div>
      <div class="stage" id="stage-charts"><span class="dot"></span>Chart Generation</div>
      <div class="stage" id="stage-webex"><span class="dot"></span>Webex Delivery</div>
    </div>
  </div>

</div><!-- .main -->

<script>
const MAX_LOG_LINES = 80;
let noteCount = 0;
let logLines = [];

const ARROW_IDS = {
  'note_played':       ['arr-piano-session', 'arr-session-splunk'],
  'segment_complete':  ['arr-session-coach'],
  'session_ended':     ['arr-session-coach'],
  'coach_started':     ['arr-coach-skill'],
  'mcp_query':         ['arr-skill-mcp', 'arr-mcp-splunk'],
  'chart_generated':   ['arr-skill-charts'],
  'webex_sent':        ['arr-coach-webex', 'arr-webex-space'],
};

const NODE_ACTIVATE = {
  'note_played':       ['node-piano', 'node-session', 'node-splunk'],
  'segment_complete':  ['node-session'],
  'session_ended':     ['node-session', 'node-coach'],
  'coach_started':     ['node-coach', 'node-skill'],
  'mcp_query':         ['node-mcp', 'node-splunk'],
  'chart_generated':   ['node-charts'],
  'webex_sent':        ['node-webex-delivery', 'node-webex-space'],
};

const NODE_DONE = {
  'segment_complete':  ['node-session'],
  // webex_sent done-state is applied with a delay (see handleEvent)
};

const STAGE_ACTIVATE = {
  'note_played':       'stage-capture',
  'segment_complete':  'stage-splunk',
  'coach_started':     'stage-coach',
  'mcp_query':         'stage-mcp',
  'chart_generated':   'stage-charts',
  'webex_sent':        'stage-webex',
};

const STAGE_DONE = {
  'segment_complete':  'stage-splunk',
  // webex_sent stages are marked done inside the setTimeout in handleEvent
};

function activateNodes(ids) {
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.classList.add('active'); el.classList.remove('done'); }
  });
}
function doneNodes(ids) {
  if (!Array.isArray(ids)) ids = [ids];
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.classList.add('done'); el.classList.remove('active'); }
  });
}
function activateArrows(ids) {
  ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.add('active');
  });
  setTimeout(() => ids.forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('active');
  }), 800);
}
function setStage(id, state) {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove('active', 'done');
  if (state) el.classList.add(state);
}

function appendNote(html) {
  const log = document.getElementById('note-log');
  logLines.push(html);
  if (logLines.length > MAX_LOG_LINES) logLines.shift();
  log.innerHTML = logLines.join('<br>');
  log.scrollTop = log.scrollHeight;
}

function handleEvent(data) {
  const ev = data.event;
  const pill = document.getElementById('status-pill');

  // Activate arrows
  if (ARROW_IDS[ev]) activateArrows(ARROW_IDS[ev]);

  // Activate / done nodes
  if (NODE_ACTIVATE[ev]) activateNodes(NODE_ACTIVATE[ev]);
  if (NODE_DONE[ev])     doneNodes(Array.isArray(NODE_DONE[ev]) ? NODE_DONE[ev] : [NODE_DONE[ev]]);

  // Stage indicators
  if (STAGE_ACTIVATE[ev]) setStage(STAGE_ACTIVATE[ev], 'active');
  if (STAGE_DONE[ev]) {
    const ids = Array.isArray(STAGE_DONE[ev]) ? STAGE_DONE[ev] : [STAGE_DONE[ev]];
    ids.forEach(id => setStage(id, 'done'));
  }

  // Status pill + special state transitions
  if (ev === 'listening') {
    // Reset everything to idle between sessions
    ['node-piano','node-session','node-splunk','node-coach','node-mcp',
     'node-skill','node-charts','node-webex-delivery','node-webex-space']
      .forEach(id => { const el = document.getElementById(id); if (el) { el.classList.remove('active','done'); } });
    ['arr-piano-session','arr-session-splunk','arr-session-coach','arr-coach-skill',
     'arr-skill-mcp','arr-mcp-splunk','arr-skill-charts','arr-coach-webex','arr-webex-space']
      .forEach(id => { const el = document.getElementById(id); if (el) { el.classList.remove('active','done'); } });
    ['stage-capture','stage-splunk','stage-coach','stage-mcp','stage-charts','stage-webex']
      .forEach(id => setStage(id, null));
    logLines = []; document.getElementById('note-log').innerHTML = '<span class="sys">Waiting for session...</span>';
    pill.textContent = 'Waiting for session'; pill.className = 'status-pill';
  }
  if (ev === 'session_started') {
    pill.textContent = 'Session active'; pill.className = 'status-pill active';
    setStage('stage-capture', 'active'); activateNodes(['node-piano', 'node-session']);
  }
  if (ev === 'session_ended') {
    pill.textContent = 'Analyzing…'; pill.className = 'status-pill analyzing';
    setStage('stage-capture', 'done');
    // Splunk dims briefly — it fed the session, now coach takes over
    const splunkEl = document.getElementById('node-splunk');
    if (splunkEl) splunkEl.classList.remove('active');
  }
  if (ev === 'webex_sent') {
    // Show active glow on webex nodes first, then go green after a beat
    setTimeout(() => {
      doneNodes(['node-coach', 'node-mcp', 'node-skill', 'node-charts',
                 'node-webex-delivery', 'node-webex-space', 'node-splunk',
                 'node-piano', 'node-session']);
      ['stage-coach', 'stage-mcp', 'stage-charts', 'stage-webex'].forEach(id => setStage(id, 'done'));
      pill.textContent = 'Complete ✅'; pill.className = 'status-pill done';
    }, 1500);
  }

  // Note log
  if (ev === 'note_played') {
    noteCount++;
    const hand = data.hand === 'right' ? 'rh' : 'lh';
    const label = data.hand === 'right' ? 'RH' : 'LH';
    appendNote(`<span class="${hand}">♪ ${data.note || '?'} ${label} f:${data.finger || '?'}</span>`);
  }
  if (ev === 'segment_complete') {
    appendNote(`<span class="seg">── Seg ${data.index || ''} ${data.scale || ''} · ${data.rh_bpm || '?'} BPM ──</span>`);
  }
  if (ev === 'session_ended') {
    appendNote(`<span class="sys">Session ended — ${data.segments || 0} segment(s)</span>`);
  }
  if (ev === 'coach_started') {
    appendNote(`<span class="sys">Coach analyzing ${data.scale || ''}…</span>`);
  }
  if (ev === 'webex_sent') {
    appendNote(`<span class="sys">✅ Card posted to Webex</span>`);
  }
}

// SSE connection
const es = new EventSource('/events');
es.onmessage = e => {
  try { handleEvent(JSON.parse(e.data)); } catch(_) {}
};
es.onerror = () => {
  document.getElementById('status-pill').textContent = 'Server disconnected';
};
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/event", methods=["POST"])
def receive_event():
    data = request.get_json(silent=True) or {}
    payload = f"data: {json.dumps(data)}\n\n"
    with _clients_lock:
        dead = []
        for q in _clients:
            try:
                q.put_nowait(payload)
            except queue.Full:
                dead.append(q)
        for q in dead:
            _clients.remove(q)
    return "", 204


@app.route("/events")
def sse_stream():
    q: queue.Queue = queue.Queue(maxsize=50)
    with _clients_lock:
        _clients.append(q)

    def generate():
        try:
            yield "data: {\"event\": \"connected\"}\n\n"
            while True:
                try:
                    yield q.get(timeout=20)
                except queue.Empty:
                    yield ": keepalive\n\n"
        except GeneratorExit:
            with _clients_lock:
                try:
                    _clients.remove(q)
                except ValueError:
                    pass

    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


if __name__ == "__main__":
    import webbrowser
    print("=== AI Music Pipeline Dashboard ===")
    print("Open http://localhost:5000 in your browser")
    print("Set DEMO_SERVER_URL=http://localhost:5000 in .env.tpl to enable event emission\n")
    webbrowser.open("http://localhost:5000")
    app.run(host="0.0.0.0", port=5000, threaded=True)
