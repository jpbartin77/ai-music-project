
"""
record_test_scale.py — Record real C-Major playing from the piano and save as a test fixture.

Usage:
    .venv\\Scripts\\python.exe tools/record_test_scale.py

The fixture is saved to data/test_fixtures/c_major_recording.json and can be
replayed without the piano using:
    op run --env-file=.env.tpl -- .venv\\Scripts\\python.exe tools/send_test_scale.py
"""

import json
import pathlib
import sys
import threading
import time

import rtmidi

sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

# C major 2-octave ascending note sequence (MIDI numbers)
C_MAJOR_RH_MIDI = [60, 62, 64, 65, 67, 69, 71, 72, 74, 76, 77, 79, 81, 83, 84]
C_MAJOR_LH_MIDI = [48, 50, 52, 53, 55, 57, 59, 60, 62, 64, 65, 67, 69, 71, 72]

RH_FINGERS = [1, 2, 3, 1, 2, 3, 4, 1, 2, 3, 1, 2, 3, 4, 5]
LH_FINGERS = [5, 4, 3, 2, 1, 3, 2, 1, 4, 3, 2, 1, 3, 2, 1]

MIDI_NOTE_NAMES = {
    n: f"{['C','Db','D','Eb','E','F','Gb','G','Ab','A','Bb','B'][n % 12]}{n // 12 - 1}"
    for n in range(128)
}

FIXTURE_PATH = pathlib.Path(__file__).parent.parent / "data" / "test_fixtures" / "c_major_recording.json"


def main():
    midi_in = rtmidi.MidiIn()
    ports = midi_in.get_ports()
    if not ports:
        print("No MIDI devices found — connect the piano and try again.")
        sys.exit(1)

    print("Available MIDI input ports:")
    for i, name in enumerate(ports):
        print(f"  [{i}] {name}")

    # Prefer USB-MIDI (the piano); fall back to port 0
    port_index = 0
    for i, name in enumerate(ports):
        if "usb-midi" in name.lower() or "usb midi" in name.lower():
            port_index = i
            break

    print(f"\nUsing: [{port_index}] {ports[port_index]}")
    midi_in.open_port(port_index)

    print()
    print("  Play 2 full C-Major scales (RH + LH together, ascending and descending).")
    print("  Press Enter when ready to start, Enter again when done.")
    print()
    input("  >>> Press Enter to START recording...")
    print("  Recording... play now!")

    raw_notes = []
    start_time = None
    lock = threading.Lock()

    def _cb(message, _=None):
        nonlocal start_time
        msg, delta = message
        status = msg[0] & 0xF0
        midi_note = msg[1]
        velocity = msg[2]
        if status == 0x90 and velocity > 0:
            now = time.perf_counter()
            with lock:
                if start_time is None:
                    start_time = now
                time_ms = round((now - start_time) * 1000, 1)
            raw_notes.append({"midi": midi_note, "velocity": velocity, "time_ms": time_ms})
            print(f"  {MIDI_NOTE_NAMES.get(midi_note, f'?{midi_note}')}  vel={velocity}  t={time_ms:.0f}ms")

    midi_in.set_callback(_cb)

    input("\n  >>> Press Enter to STOP recording...")
    midi_in.cancel_callback()
    midi_in.close_port()

    if not raw_notes:
        print("No notes captured — nothing to save.")
        sys.exit(1)

    print(f"\n  Captured {len(raw_notes)} note(s).")

    # Split into RH (MIDI >= 60) and LH (MIDI < 60) and assign fingers
    rh_midi_set = set(C_MAJOR_RH_MIDI)
    lh_midi_set = set(C_MAJOR_LH_MIDI)

    rh_notes = []
    lh_notes = []

    for n in raw_notes:
        midi = n["midi"]
        name = MIDI_NOTE_NAMES.get(midi, f"?{midi}")
        if midi >= 60:
            idx = rh_notes
            finger_map = dict(zip(C_MAJOR_RH_MIDI, RH_FINGERS))
        else:
            idx = lh_notes
            finger_map = dict(zip(C_MAJOR_LH_MIDI, LH_FINGERS))
        idx.append({
            "midi": midi,
            "name": name,
            "velocity": n["velocity"],
            "finger": finger_map.get(midi, 0),
            "time_ms": n["time_ms"],
        })

    print(f"  RH notes: {len(rh_notes)}  |  LH notes: {len(lh_notes)}")

    if len(rh_notes) < 5 or len(lh_notes) < 5:
        print("  Warning: very few notes in one hand — fixture may be incomplete.")

    FIXTURE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fixture = {"scale": "c_major", "rh": rh_notes, "lh": lh_notes}
    FIXTURE_PATH.write_text(json.dumps(fixture, indent=2))
    print(f"\n  Saved to: {FIXTURE_PATH}")
    print("  Run send_test_scale.py to replay.")


if __name__ == "__main__":
    main()
