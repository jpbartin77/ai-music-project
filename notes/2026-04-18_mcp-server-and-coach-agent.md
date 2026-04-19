# MCP Server & Coach Agent (April 18, 2026)

## Summary

`src/mcp_server.py` exposes Splunk practice data as MCP tools that Claude can call.
`src/coach_agent.py` runs Claude as an autonomous agent that uses those tools to write
a personalized coaching report after each practice session.

Single command to run a full session:
```bash
op run --env-file=.env.tpl -- python src/coach_agent.py [session_id]
```

If `session_id` is omitted, the agent fetches the most recent non-test session automatically.

---

## Architecture

```
coach_agent.py
  → Anthropic API (claude-opus-4-7)
    → tool_use calls → mcp_server._dispatch()
      → Splunk REST API (port 8089, token auth)
        → index: edge_hub_mqtt
  → stop_reason == end_turn → JSON coaching report
    → webex_delivery.post_card()
```

---

## MCP Server (`src/mcp_server.py`)

Five tools, all backed by SPL queries via Splunk's blocking search REST endpoint
(`POST /services/search/jobs` with `exec_mode=blocking`).

| Tool | What it returns | Key SPL detail |
|------|----------------|----------------|
| `get_recent_sessions` | Last N session summaries (both hands, speed, evenness) | `spath input=event` to unpack nested JSON; `sort -_time` |
| `get_session_detail` | Full note-level data for one session | `source="piano/notes"`, 500-result cap |
| `compare_hands` | LH vs RH speed/evenness side-by-side for a session | Same query as `get_recent_sessions` filtered by `session_id` |
| `get_scale_history` | Speed and evenness trend across all sessions for a scale | `sort _time` (ascending) for trend analysis |
| `get_finger_trends` | Per-finger average timing deviation | `eventstats avg(time_ms) as session_mean_ms by session_id` then `eval deviation_ms=...` |

### Critical implementation details

**Auth header:** `"Authorization": f"Splunk {SPLUNK_TOKEN}"` — not `Bearer`. Splunk REST API
requires the `Splunk` prefix; `Bearer` returns 401.

**SSL:** Lab Splunk uses a self-signed cert. SSL context is set to `CERT_NONE`:
```python
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE
```

**Nested field extraction:** Piano HEC events store metrics inside a nested `event` JSON blob.
Top-level Splunk fields auto-extract, but `metrics.right.speed_bpm` etc. require:
```spl
| spath input=event
| table _time session_id scale "metrics.right.speed_bpm" ...
```
`json_extract()` is not valid SPL — `spath` is the correct function.

**`_dispatch()` vs MCP transport:** The server exposes `_dispatch(name, args)` as a plain
synchronous function so `coach_agent.py` can call it directly without starting the stdio
MCP server. The MCP `@server.call_tool()` handler also calls `_dispatch()`. Both paths work.

### Known issue: `get_finger_trends`

Current SPL computes each note's deviation from `session_mean_ms` — the average of the
`time_ms` field across the session. But `time_ms` is cumulative elapsed time since session
start, not an inter-onset interval (IOI). Fingers appearing later in the scale (4, 5) will
always have positive deviation from a mid-session mean, not because of timing weakness but
because they play late in the scale. The tool returns data and Claude uses it, but the values
are not meaningful for identifying weak fingers.

**Correct fix (deferred):** Compute IOI between consecutive notes within each segment, then
measure per-finger deviation from the expected IOI. Requires window functions or a multi-pass
SPL approach. Deferred until core pipeline is stable.

---

## Coach Agent (`src/coach_agent.py`)

### Model

`claude-opus-4-7` — used for reasoning quality and multi-step tool orchestration.

### System prompt design

The prompt emphasizes longitudinal analysis over single-session feedback:

> "The most important thing to communicate is progress over time — not just how today went,
> but whether the student is measurably improving. Concrete comparisons ('your evenness improved
> 18% over the last 5 sessions') are far more valuable than generic encouragement."

Claude is instructed to make 3–5 tool calls before writing its report, in roughly this order:
1. `get_recent_sessions` — establish trend baseline
2. `compare_hands` — check left/right balance for current session
3. `get_scale_history` — per-scale trend for the scale just practiced
4. `get_finger_trends` — optional, if finger-level detail is wanted

### Output schema

Claude returns a JSON object only — no markdown, no surrounding text:
```json
{
  "summary": "2-3 sentence overall assessment including trend context",
  "strengths": ["specific strength with data reference"],
  "focus_areas": ["specific area with finger numbers or hand if relevant"],
  "suggested_next_session": "one concrete, actionable practice instruction",
  "trend": "improving | stable | needs_attention",
  "trend_detail": "1-2 sentences on the metric driving the trend assessment",
  "milestone": "personal best callout if set this session, else empty string"
}
```

### Agentic loop

```python
while iteration < max_iterations:          # cap at 10
    response = client.messages.create(...)
    if response.stop_reason == "end_turn":
        # parse JSON from response text
        return json.loads(...)
    if response.stop_reason == "tool_use":
        # call _dispatch() for each tool block
        # append tool_results to messages
        # continue loop
```

### JSON parsing robustness

Claude occasionally wraps JSON in markdown fences or adds a sentence before the object.
The parser:
1. Strips ` ```json ... ``` ` fences if present
2. Finds the outermost `{...}` using `text.find("{")` / `text.rfind("}")`
3. Parses only that substring

### Real-world performance

In testing with live session data, Claude autonomously:
- Made 6 tool calls before writing the report
- Identified a segment 13 anomaly (sudden evenness drop — likely fatigue)
- Flagged a 286 BPM right-hand milestone
- Generated actionable next-session instruction focused on left-hand evenness

---

## Smoke Test (`tools/test_mcp_tools.py`)

Calls `_dispatch()` directly for all 5 tools without starting the MCP server.
Run with:
```bash
op run --env-file=.env.tpl -- python tools/test_mcp_tools.py
```

All 5 tools confirmed working against live Splunk data as of April 18, 2026.

---

## What's next

- Cloud Run endpoint to trigger `run_coach()` via HTTP POST (Phase 3.4.6)
- Splunk alert to POST to Cloud Run URL when a new session is indexed (Phase 3.4.1)
- `src/hec_publisher.py` — bypass Node-RED by posting directly to HEC from practice_session.py
- Fix `get_finger_trends` to use IOI-based deviation
