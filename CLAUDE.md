# AI Music Project — Claude Context

## Purpose

Piano practice as a sensor network and AI coaching lab. The project captures live MIDI from a piano, computes session metrics (speed, evenness, per-finger timing), ships them to Splunk, and triggers an AI coach (Claude) that returns structured feedback via Webex Adaptive Cards.

**Two presentations this serves:**
1. AI music / hobby-as-AI-lab demo — "I used my piano as a sensor network. Same patterns I use at work."
2. Cisco Workflows standalone demo (stretch goal — Webex bot freeform queries routed via Workflows)

---

## Architecture (Phase 1 — Current Target)

```
🎹 Piano (USB MIDI)
  ↓
practice_session.py  ──→  HEC POST  ──→  Splunk (index=edge_hub_mqtt)
  ↓ (session end)                           ↑
coach_agent.py  ←──── MCP tool calls ──── mcp_server.py
  ↓
webex_delivery.py  ──→  Webex Adaptive Card
```

No tunnels. No Workflows in the session trigger path. Everything runs on the workstation.

**Stretch goal (Phase 1.5):** Webex bot freeform queries → Workflows webhook → ngrok → local `/coach` service → Webex card reply.

---

## Source Files

| File | Purpose |
|------|---------|
| `src/practice_session.py` | MIDI capture, hand splitting, scale detection, scoring, session-end coach trigger. Starts in listening mode; C8 (MIDI 108) starts a session, A0 (MIDI 21) ends it. |
| `src/hec_publisher.py` | Posts events directly to Splunk HEC (bypasses Node-RED) |
| `src/mqtt_publisher.py` | Legacy MQTT publisher (fallback; set `PUBLISHER_TYPE=mqtt`) |
| `src/mcp_server.py` | MCP server — 5 tools exposing Splunk practice data to Claude |
| `src/coach_agent.py` | Agentic Claude loop (claude-opus-4-7); calls MCP tools, returns coaching JSON |
| `src/webex_delivery.py` | Posts coaching report as Webex Adaptive Card v1.2 |
| `src/cloud_run_app.py` | PARKED — Flask `/coach` endpoint (Cloud Run target, not in use) |
| `src/piano_roll.py` | Record MIDI → save .mid → render piano roll PNG |
| `src/midi_test.py` | Debug listener — prints NOTE_ON/OFF events with A0 marker |
| `src/demo_server.py` | Flask SSE server — animated pipeline dashboard at localhost:5000 |
| `src/demo_emitter.py` | Fire-and-forget HTTP emitter; called by practice_session.py to push events to demo_server |
| `tools/send_test_scale.py` | Simulates a C major scale via HEC/MQTT (no piano needed) |
| `tools/test_mcp_tools.py` | Smoke-tests MCP server Splunk connectivity |

---

## Environment Setup

All secrets are injected at runtime via 1Password CLI. Nothing sensitive is ever on disk.

**Always use `.venv\Scripts\python.exe` explicitly with `op run`** — `op run` spawns a subprocess that may not resolve `python` to the venv even when the venv is activated in the shell.

```powershell
op run --env-file=.env.tpl -- .venv\Scripts\python.exe src/practice_session.py
op run --env-file=.env.tpl -- .venv\Scripts\python.exe src/coach_agent.py
op run --env-file=.env.tpl -- .venv\Scripts\python.exe tools/send_test_scale.py
```

Scripts with no secrets (e.g. `demo_server.py`) can be run directly without `op run`:

```powershell
python src/demo_server.py
```

### Environment Variables

| Variable | Purpose | Direction |
|----------|---------|-----------|
| `SPLUNK_HEC_URL` | Splunk HEC ingest endpoint | workstation → Splunk |
| `SPLUNK_HEC_TOKEN` | HEC auth token | — |
| `SPLUNK_URL` | Splunk REST API (port 8089) | workstation → Splunk |
| `SPLUNK_TOKEN` | REST API token | — |
| `SPLUNK_INDEX` | Splunk index name (default: `edge_hub_mqtt`) | — |
| `PUBLISHER_TYPE` | `hec` (default) or `mqtt` | — |
| `AUTO_COACH` | `true` (default) — set to `false` to skip coaching after each segment | — |
| `ANTHROPIC_API_KEY` | Claude API key | — |
| `WEBEX_BOT_TOKEN` | Webex bot token | — |
| `WEBEX_ROOM_ID` | Webex space to post cards to | — |
| `DEMO_SERVER_URL` | `http://localhost:5000` to enable dashboard; blank = disabled | — |

**Current dCloud addresses (ephemeral — rotate weekly):**
- `SPLUNK_HEC_URL=http://198.18.135.50:8088/services/collector/event`
- `SPLUNK_URL=https://198.18.135.50:8089`

**When cloud Splunk arrives:** update `SPLUNK_HEC_URL`, `SPLUNK_URL`, and their tokens. Everything else unchanged.

---

## Data Flow Details

- MIDI events land in `index=edge_hub_mqtt` with `source=piano/notes` or `source=piano/sessions`
- JSON payload stored in the `event` field; use `spath input=event` in SPL to flatten
- Local copies always saved to `data/sessions/{timestamp}_seg{N}_{scale}.json`
- MCP tools query Splunk REST API on port 8089 (not HEC)

---

## Dev Conventions

- `.env.tpl` uses 1Password secret references (`op://Private/...`). Never put real values in it.
- Run secrets-needing scripts via `op run --env-file=.env.tpl -- .venv\Scripts\python.exe src/<script>.py`
- `tools/` contains test utilities that don't require a piano
- `config/fingerings.md` defines 12 major scales with finger mappings — parsed by `practice_session.py`
- Python 3.13 + `reapy-next` requires manual patches; see `notes/Reapy_Patch_Notes.md` and `patch_reapy.bat`

---

## Key Files for Reference

- `plan/implementation_plan.md` — current roadmap (Phase 1 / 1.5 / 2)
- `notes/splunk_spl_cheat_sheet.md` — SPL queries for practice data
- `notes/mqtt_setup.md` — MQTT broker details and env var reference
- `notes/2026-04-25 - To do when connecting to a new dCloud session.md` — dCloud setup checklist

---

## dCloud Session Setup (required each rotation)

Run in an **admin PowerShell** before testing anything that hits 198.18.x.x:

```powershell
route add 198.18.0.0 mask 255.255.0.0 100.127.43.1
```

Add `-p` to make it persistent across reboots. Note: the gateway IP (`100.127.43.1`) may change between dCloud rotations — verify it if connectivity fails.

After each rotation also check:
- `SPLUNK_URL` and `SPLUNK_HEC_URL` in `.env.tpl` (IPs usually stay the same but confirm)
- `SPLUNK_HEC_TOKEN` in 1Password — the HEC token may rotate with the lab

Full detail: `notes/2026-04-25 - To do when connecting to a new dCloud session.md`

---

*Prompt Claude to update this file when: addresses change, new source files are added, architecture decisions are made, or env vars are added/removed.*
