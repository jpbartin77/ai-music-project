# Session Notes — 2026-04-26

## What we built

### Animated demo dashboard (completed from previous session)
- `src/demo_server.py` — Flask SSE server, dark navy SVG pipeline diagram at localhost:5000
- `src/demo_emitter.py` — fire-and-forget HTTP emitter called by practice_session.py
- Nodes: Piano → practice_session → Splunk → Coach Agent → Coaching Skill (purple) → mcp_server / charts.py → webex_delivery → Webex Space
- Blue glow = active, green = done; dashboard resets to listening state between sessions
- C8 (MIDI 108) starts a session, A0 (MIDI 21) ends it; loops back to listening

### practice_session.py — listening mode
- Starts in listening mode waiting for C8, not a timed loop
- Outer `while True` keeps MIDI port open and reuses HECPublisher across sessions
- `time.sleep(2)` at end of coaching loop lets daemon emit threads finish before process exits

### tools/record_test_scale.py (new)
- Opens MIDI input, records note_on events with real wall-clock timing
- Splits RH (MIDI ≥ 60) / LH (MIDI < 60), assigns C-major fingers
- Saves to `data/test_fixtures/c_major_recording.json`
- Real C-major recording captured: 88 RH + 28 LH notes

### tools/send_test_scale.py (major upgrade)
- Loads fixture (real recording) or falls back to synthetic notes
- Emits full demo event sequence: session_started → note_played (per note, real IOI timing) → segment_complete → coach pipeline → listening
- `--no-coach`: simulated coaching events with realistic delays (no API call)
- `--reaper`: sends MIDI note_on/off to virtual port; note_off is async (daemon thread) so IOI timing is preserved
- `--midi-port NAME`: substring match against MIDI output ports (default "TestScale")
- `--list-ports`: print available MIDI output ports and exit
- `--fixture PATH`: load specific JSON fixture; `synthetic` uses hardcoded notes
- `sys.stdout.reconfigure(utf-8)` to handle cp1252 console encoding via op run

### Reaper / loopMIDI integration
- loopMIDI installs and runs on Windows 11 (despite website showing Win7/10)
- TestScale virtual port created in loopMIDI; appears as MIDI output to rtmidi after Windows MIDI service restart
- Reaper track set to "All MIDI Inputs" — notes flow from script → loopMIDI → Reaper → piano VST

---

## Known issues / next steps

- [ ] Confirm notes actually play through Reaper VST (TestScale port wired, not yet verified end-to-end)
- [ ] Run full demo rehearsal: demo_server + send_test_scale --reaper --no-coach
- [ ] Run with real coaching (drop --no-coach) to confirm Webex card arrives
- [ ] Write 5-minute demo script / narrative
- [ ] Record 5–10 real practice sessions to build coaching history
- [ ] Git tag `v0.3-demo-dashboard`

## Architecture note — Coaching Skill node
The purple "Coaching Skill" node in the diagram is not a separate code file.
It represents the logical role coach_agent.py plays: discrete input (session_id + scale),
discrete output (coaching report). Honest presentation framing:
"the coaching capability the AI exercises — the role is real even if the component
boundary is conceptual; a formal subagent would be the Phase 2 evolution."

## Run commands (for reference)
```powershell
# Demo server (no secrets needed)
python src/demo_server.py

# Full rehearsal without piano
$env:DEMO_SERVER_URL="http://localhost:5000"
op run --env-file=.env.tpl -- .venv\Scripts\python.exe tools/send_test_scale.py --reaper --midi-port "TestScale" --no-coach

# Real session
$env:DEMO_SERVER_URL="http://localhost:5000"
op run --env-file=.env.tpl -- .venv\Scripts\python.exe src/practice_session.py
```
