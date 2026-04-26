# Session Notes — 2026-04-26 (session 2)

## What we built / fixed

### Demo rehearsal path — completed and verified
Full end-to-end test without piano confirmed working:
- Dashboard animates correctly
- Notes play through Reaper VST via loopMIDI TestScale port
- Webex coaching card arrives with chart

### send_test_scale.py fixes
- **Note interleaving** — RH and LH notes now merged and sorted by `time_ms` before
  replay, so playback matches the original recording's chronological order
- **Legato** — `NOTE_DURATION_S` raised from 80ms → 180ms; note_off is async so
  IOI timing is unaffected; notes now connect rather than sound staccato
- **Finger display** — sidebar was showing `f:?` because `finger` was missing from
  the `note_played` emit; added `finger=note.get("finger")`
- **MIDI bookends** — C8 (MIDI 108) fired 400ms before first note, A0 (MIDI 21)
  fired 400ms after last note; simulates real session start/stop in Reaper

### MIDI port auto-detection
Both `record_test_scale.py` and `practice_session.py` were hardcoded to port 0.
After loopMIDI + REAPER Loopback were added, the piano shifted to a different index.
Fixed both to search for "USB-MIDI" by name and fall back to port 0.
`record_test_scale.py` also now prints all available input ports at startup.

### Reaper / loopMIDI setup (confirmed working on Windows 11)
- loopMIDI installs and runs on Windows 11 despite website listing Win7/Win10
- TestScale virtual port created; requires Windows MIDI service restart to appear
- Reaper track: Input: MIDI → TestScale (or All MIDI Inputs); track armed
- Piano plays through VST when send_test_scale.py runs with --reaper flag

---

## Known limitation — test fixture hand-splitting
`record_test_scale.py` splits hands by MIDI pitch (>= 60 → RH). This fails for
2-octave scales because LH upper octave (C4–C5, MIDI 60–72) overlaps with RH
lower octave. Multiple re-recordings attempted. Decision: set this aside — the
live piano path works perfectly and is the right tool for the demo. The test
script remains useful for dashboard UI smoke tests (--no-coach) and HEC
connectivity checks, not for generating realistic coaching data.

---

## Next session priorities (see plan/ for detail)
1. Coaching Skill — formalize as Python class, implement realistic use case
2. Finger latency chart — taller, split ascending vs. descending
3. Content / narrative documentation
4. ThousandEyes or Workflows integration exploration
