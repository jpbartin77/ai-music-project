"""
send_test_scale.py — Sends a simulated C major scale to MQTT without a piano.

Publishes exactly what practice_session.py would publish for one valid segment:
  - 15 piano/notes messages per hand (2-octave C major scale, RH then LH)
  - 1 piano/sessions summary message

Usage:
    python tools/send_test_scale.py

Uses the same env vars as the live session:
    MQTT_HOST  (default: 100.127.43.4)
    MQTT_PORT  (default: 1883)
"""

import json
import os
import sys
import time
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'src'))
from mqtt_publisher import MQTTPublisher

# C major 2-octave scale starting at C4 (MIDI 60) for RH, C3 (MIDI 48) for LH
RH_MIDI = [60, 62, 64, 65, 67, 69, 71, 72, 74, 76, 77, 79, 81, 83, 84]
LH_MIDI = [48, 50, 52, 53, 55, 57, 59, 60, 62, 64, 65, 67, 69, 71, 72]

NOTE_NAMES = {
    48:'C3', 50:'D3', 52:'E3', 53:'F3', 55:'G3', 57:'A3', 59:'B3',
    60:'C4', 62:'D4', 64:'E4', 65:'F4', 67:'G4', 69:'A4', 71:'B4',
    72:'C5', 74:'D5', 76:'E5', 77:'F5', 79:'G5', 81:'A5', 83:'B5', 84:'C6',
}

RH_FINGERS = [1, 2, 3, 1, 2, 3, 4, 1, 2, 3, 1, 2, 3, 4, 5]
LH_FINGERS = [5, 4, 3, 2, 1, 3, 2, 1, 4, 3, 2, 1, 3, 2, 1]

IOI_MS = 130.0  # inter-onset interval — roughly 115 BPM


def build_notes(midi_list, fingers):
    notes = []
    for i, (midi, finger) in enumerate(zip(midi_list, fingers)):
        notes.append({
            'midi':     midi,
            'name':     NOTE_NAMES[midi],
            'velocity': 72,
            'finger':   finger,
            'time_ms':  round(i * IOI_MS, 1),
        })
    return notes


def build_session_doc(rh_notes, lh_notes, session_id):
    speed_bpm = round(60000 / IOI_MS, 1)
    hand_metrics = {
        'speed_bpm':          speed_bpm,
        'evenness_stddev_ms': 4.2,
        'evenness_cv_pct':    3.2,
        'per_finger':         {},
    }
    return {
        'timestamp':     time.strftime('%Y-%m-%dT%H:%M:%S'),
        'scale':         'c_major',
        'scale_display': 'C Major',
        'segment_index': 1,
        'metrics':       {'right': hand_metrics, 'left': {**hand_metrics}},
        'notes':         {'right': rh_notes, 'left': lh_notes},
        'session_id':    session_id,
    }


def main():
    session_id = time.strftime('TEST_%Y%m%d_%H%M%S')
    print(f"Test session: {session_id}")

    pub = MQTTPublisher()
    time.sleep(1.0)  # allow connection to establish

    if not pub.connected:
        print("Could not connect to MQTT broker — check MQTT_HOST/MQTT_PORT env vars.")
        sys.exit(1)

    rh_notes = build_notes(RH_MIDI, RH_FINGERS)
    lh_notes = build_notes(LH_MIDI, LH_FINGERS)

    print("Publishing piano/notes ...")
    for note in rh_notes:
        pub.publish_note(note, 'right', 'c_major', session_id)
        print(f"  RH {note['name']} finger={note['finger']}")
        time.sleep(0.05)

    for note in lh_notes:
        pub.publish_note(note, 'left', 'c_major', session_id)
        print(f"  LH {note['name']} finger={note['finger']}")
        time.sleep(0.05)

    print("Publishing piano/sessions ...")
    doc = build_session_doc(rh_notes, lh_notes, session_id)
    pub.publish_segment(doc, session_id)
    print(f"  Segment summary sent — speed={doc['metrics']['right']['speed_bpm']} BPM")

    time.sleep(0.5)
    pub.disconnect()
    print("Done.")


if __name__ == '__main__':
    main()
