# Progress Report — April 17, 2026

## Executive Summary

Completed the two foundational phases of the AI Practice Coach pipeline in a single session. The project now has a working MIDI capture and analysis engine (`practice_session.py`) and a fully wired MQTT publisher (`mqtt_publisher.py`). The pipeline is ready for end-to-end testing once the Splunk Edge Hub is reachable. The overall architecture was also finalised and documented in `plan/implementation_plan.md`.

---

## Project Orientation

Started the session by reconstructing context after a break since the February presentation. Key cleanup completed:

- **Deleted `harmonic_sandbox/`** — the Streamlit/Gemini/chord engine code from the Feb presentation was removed from the repo. Archived externally by the user. The bugs that existed in it (empty visualizer file, broken `st.image` width argument) were noted but became moot.
- **Cleared a stale git rebase** — the repo had been left mid-rebase. Resolved by removing the empty `.git/rebase-merge` directory and committing the pending deletions cleanly.
- **Written `plan/implementation_plan.md`** — full phased plan capturing the revised architecture, presentation goals, and all open questions.

---

## Architecture Decision — The Pivot to a Practice Coach

The original Phase 3 (live call-and-response via Reaper/Pianoteq) was deferred. The new direction builds a non-realtime AI practice coach for two reasons:

1. The user does not have a keyboard at the upcoming presentation — pre-recorded data makes for a more reliable demo.
2. The project now serves two presentations simultaneously: the AI music project and a **Cisco Workflows** standalone demo.

**Narrative:** *"I used my piano practice as a sensor network. Splunk is the observability platform. Claude is the AI analyst. Workflows is the automation layer. Same patterns I use at work — I just learned them at home first."*

**Target pipeline:**
```
Piano (USB MIDI)
  → Python (practice_session.py)
    → MQTT
      → Splunk Edge Hub
        → Splunk
          → Cisco Workflows
            → Claude AI (analysis + coaching)
              → Webex Bot / Web Dashboard
```

---

## Phase 3.1 — Scale Practice Capture (`src/practice_session.py`)

### What was built

A fully self-contained practice session recorder that:

- **Auto-detects the scale** being played — no upfront input required. Starts with all 12 major scales as candidates and eliminates them as notes arrive based on pitch class matching.
- **Splits MIDI into left/right hand streams** — first two notes establish LH (lower MIDI) and RH (higher MIDI). All subsequent notes are assigned to whichever hand's last note is within 2 semitones. Splitter state persists between segments.
- **Segments by 2-second silence** — a 2-second gap closes the current segment and starts a new one. Invalid segments (wrong step size, no matching scale, single hand only) are discarded with a clear message.
- **Validates scale steps** — each note must be ±1 or ±2 semitones from the previous note in the same hand stream (enforcing major scale step sizes). Larger jumps flag the segment as invalid.
- **Assigns fingers positionally** — uses a `HandScaleTracker` that tracks sequential position in the 2-octave scale and looks up the correct finger from the fingering table. Handles both ascending and descending (descending uses the reverse of the ascending fingering).
- **Scores each segment** — speed (BPM from mean inter-onset interval), evenness (std dev and coefficient of variation of IOIs), and per-finger timing breakdown with slow/fast flags (>20ms deviation from mean).
- **Saves JSON + MIDI** — each valid segment saved to `data/sessions/` with full metrics and note-level detail.

### Key design decisions

- **Always both-handed** — single-hand segments are silently discarded. Simplifies data structure and makes Splunk analysis cleaner.
- **No duration or scale input** — session runs until Ctrl+C or a configurable max time. Everything is auto-detected.
- **Fingerings loaded from file** — `config/fingerings.md` is the single source of truth. Adding a new scale never requires touching code.

### Supporting file — `config/fingerings.md`

Built from a reference image of standard 2-octave major scale fingerings. Contains all 12 major scales, each with 15 finger numbers for RH and LH ascending (root → 2 octaves up). Descending derived in code as the reverse. Format:

```
## C Major
**Root MIDI:** 60
**RH:** 1 2 3 1 2 3 4 1 2 3 1 2 3 4 5
**LH:** 5 4 3 2 1 3 2 1 4 3 2 1 3 2 1
```

---

## Phase 3.2 — MQTT Publisher (`src/mqtt_publisher.py`)

### What was built

A `MQTTPublisher` class (using `paho-mqtt`) that:

- Connects to the MQTT broker on init, warns and continues gracefully if unreachable.
- Publishes **one message per NOTE_ON** to `piano/notes` in real time during the session.
- Publishes **one message per valid segment** to `piano/sessions` at segment close.
- Adds `timestamp_epoch` (Unix time) to every message for Splunk time indexing.
- Controlled entirely by environment variables — no hardcoded config in session code.

### Topics and payload shapes

**`piano/notes`** (real-time, one per keypress):
```json
{
  "session_id": "20260417_143022",
  "scale": "c_major",
  "hand": "right",
  "midi": 60,
  "name": "C4",
  "velocity": 85,
  "finger": 1,
  "time_ms": 1234.5,
  "timestamp_epoch": 1745123456
}
```

**`piano/sessions`** (one per completed segment):
```json
{
  "timestamp": "2026-04-17T14:32:10",
  "scale": "c_major",
  "scale_display": "C Major",
  "segment_index": 1,
  "metrics": {
    "right": { "speed_bpm": 118.4, "evenness_stddev_ms": 12.1, "evenness_cv_pct": 7.3, "per_finger": {...} },
    "left":  { "speed_bpm": 116.9, "evenness_stddev_ms": 18.4, "evenness_cv_pct": 11.2, "per_finger": {...} }
  },
  "notes": { "right": [...], "left": [...] },
  "session_id": "20260417_143022",
  "timestamp_epoch": 1745123530
}
```

### Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `MQTT_HOST` | `100.127.43.4` | Splunk Edge Hub IP |
| `MQTT_PORT` | `1883` | MQTT port |
| `MQTT_USER` | *(empty)* | Auth username |
| `MQTT_PASS` | *(empty)* | Auth password |

Set per-session using `tools/set_mqtt_env.ps1` (dot-source it):
```powershell
. .\tools\set_mqtt_env.ps1
```

---

## Supporting Files Created

| File | Purpose |
|------|---------|
| `plan/implementation_plan.md` | Full phased plan with architecture, scope, and open questions |
| `config/fingerings.md` | 2-octave fingering tables for all 12 major scales |
| `notes/mqtt_setup.md` | MQTT env var instructions + Edge Hub configuration steps |
| `tools/set_mqtt_env.ps1` | PowerShell script to set MQTT env vars for current session |

---

## What Remains (Phase 3 continuation)

1. Configure Splunk Edge Hub MQTT input ← next
2. Write SPL queries for note/session analysis
3. Build Claude MCP server (AI coaching)
4. Configure Cisco Workflows
5. Output layer — Webex bot and/or web dashboard
6. Pre-record sessions for presentation demo data
