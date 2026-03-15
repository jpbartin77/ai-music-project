## piano_roll.py — Script Summary
**File:** `src/piano_roll.py`
**Date:** March 15, 2026

### Overview
A two-part script that records live MIDI input from a digital piano and
renders it as a piano roll visualisation. Captures note name, timing,
duration, and velocity — turning a musical performance into a visual
data representation. This is the foundation for building training
datasets for AI models.

---

### Modules used

| Module | Purpose |
|---|---|
| `rtmidi` | Opens USB-MIDI connection to piano; captures live note events via callback |
| `mido` | Constructs and saves MIDI file from captured events; handles tick timing |
| `pretty_midi` | Loads saved MIDI file; parses notes into structured objects with timing and velocity |
| `matplotlib` | Renders the piano roll as a styled figure; handles axes, colors, and layout |
| `matplotlib.patches` | Draws individual note rectangles (`FancyBboxPatch`) with rounded corners |
| `numpy` | Imported for potential numerical operations (tick/time calculations) |
| `time` | Controls recording duration countdown and timestamp calculation |
| `os` | Creates the `data/` output directory if it doesn't exist |

---

### Functions defined

**`record_midi(output_file, duration)`**
Records live MIDI input from the piano for a specified duration (default
15 seconds). Opens the first available MIDI port, registers a real-time
callback that captures note-on/note-off events with timestamps, prints
note names and velocities to the terminal as you play, then saves
everything as a `.mid` file to the `data/` folder.

**`midi_callback(message, data)`**
Internal callback registered with `rtmidi`. Fires on every incoming MIDI
message. Calculates elapsed time since the last event, converts to ticks,
stores the message for later saving, and prints a human-readable note
name to the terminal in real time.

**`render_piano_roll(midi_file)`**
Loads a saved MIDI file using `pretty_midi` and renders it as a dark-
themed piano roll. Each note is drawn as a rounded rectangle — blue for
white keys, pink for black keys. Note brightness reflects velocity (louder
= brighter). The y-axis shows note names (e.g. C4, D#3); the x-axis shows
time in seconds. Saves the output as a `.png` file alongside the `.mid`
file and opens it in a matplotlib window.

---

### Output files
Both saved to `data/` folder (excluded from Git via `.gitignore`):
- `recording.mid` — raw MIDI file of the performance
- `recording_roll.png` — piano roll visualisation image

---

### Visual design
- Background: dark navy (`#1a1a2e`)
- White key notes: blue (`#4a9eff`)
- Black key notes: pink (`#ff6b9d`)
- Note opacity scales with velocity — harder hits = brighter bars
- Horizontal grid lines at every C note for pitch orientation
- Title shows total note count

---

### First result
24 notes captured in ~9 seconds. Visualisation clearly shows note
duration, pitch range, and two black-key notes (pink bars) among the
blue white-key notes. Velocity variation visible in brightness differences
across notes.

---

### Next steps
This script establishes the data pipeline. Future extensions:
- Add chord detection using `music21`
- Label notes with chord names on the visualisation
- Save multiple recordings to build a training dataset
- Analyse velocity patterns for dynamics modeling