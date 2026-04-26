"""
send_test_scale.py — Replay a C-Major test scale for demo rehearsal without a piano.

Loads note data from a recorded fixture (data/test_fixtures/c_major_recording.json)
and replays it through the full pipeline: Splunk HEC, animated demo dashboard,
optional coaching, optional Reaper MIDI playback.

Usage:
    # Replay with real coaching + Webex card:
    op run --env-file=.env.tpl -- .venv\\Scripts\\python.exe tools/send_test_scale.py

    # Replay with simulated coaching (no API call, quick UI test):
    op run --env-file=.env.tpl -- .venv\\Scripts\\python.exe tools/send_test_scale.py --no-coach

    # Replay with Reaper/VST audio (requires loopMIDI "TestScale" port):
    op run --env-file=.env.tpl -- .venv\\Scripts\\python.exe tools/send_test_scale.py --reaper

    # Use synthetic notes instead of a recording:
    op run --env-file=.env.tpl -- .venv\\Scripts\\python.exe tools/send_test_scale.py --fixture synthetic

Reaper setup (one-time):
    1. Install loopMIDI (https://www.tobias-erichsen.de/software/loopmidi.html)
    2. Create a virtual port named "TestScale"
    3. In Reaper: track → input → MIDI → TestScale (all channels)
    4. Arm the track and press Record or Monitor
"""

import argparse
import json
import os
import pathlib
import sys
import threading
import time

import rtmidi

sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / 'src'))
from hec_publisher  import HECPublisher
from mqtt_publisher import MQTTPublisher
from demo_emitter   import emit

FIXTURE_PATH = pathlib.Path(__file__).parent.parent / "data" / "test_fixtures" / "c_major_recording.json"

# Fallback synthetic C major — used if no fixture file found and --fixture not given
RH_MIDI    = [60, 62, 64, 65, 67, 69, 71, 72, 74, 76, 77, 79, 81, 83, 84]
LH_MIDI    = [48, 50, 52, 53, 55, 57, 59, 60, 62, 64, 65, 67, 69, 71, 72]
RH_FINGERS = [1, 2, 3, 1, 2, 3, 4, 1, 2, 3, 1, 2, 3, 4, 5]
LH_FINGERS = [5, 4, 3, 2, 1, 3, 2, 1, 4, 3, 2, 1, 3, 2, 1]
NOTE_NAMES = {
    48:'C3', 50:'D3', 52:'E3', 53:'F3', 55:'G3', 57:'A3', 59:'B3',
    60:'C4', 62:'D4', 64:'E4', 65:'F4', 67:'G4', 69:'A4', 71:'B4',
    72:'C5', 74:'D5', 76:'E5', 77:'F5', 79:'G5', 81:'A5', 83:'B5', 84:'C6',
}
SYNTHETIC_IOI_MS = 130.0


def _synthetic_notes():
    rh = [
        {"midi": m, "name": NOTE_NAMES[m], "velocity": 72, "finger": f,
         "time_ms": round(i * SYNTHETIC_IOI_MS, 1)}
        for i, (m, f) in enumerate(zip(RH_MIDI, RH_FINGERS))
    ]
    lh = [
        {"midi": m, "name": NOTE_NAMES[m], "velocity": 68, "finger": f,
         "time_ms": round(i * SYNTHETIC_IOI_MS, 1)}
        for i, (m, f) in enumerate(zip(LH_MIDI, LH_FINGERS))
    ]
    return rh, lh


def _load_fixture(path):
    data = json.loads(pathlib.Path(path).read_text())
    return data["rh"], data["lh"]


def _list_midi_ports():
    midi_out = rtmidi.MidiOut()
    ports = midi_out.get_ports()
    print("Available MIDI output ports:")
    for i, name in enumerate(ports):
        print(f"  [{i}] {name}")
    if not ports:
        print("  (none)")


def _open_reaper_port(port_name):
    midi_out = rtmidi.MidiOut()
    ports = midi_out.get_ports()
    for i, name in enumerate(ports):
        if port_name.lower() in name.lower():
            midi_out.open_port(i)
            print(f"  [reaper] MIDI out -> {name}")
            return midi_out
    print(f"  [reaper] Warning: no port matching '{port_name}' found — skipping MIDI playback.")
    print(f"  [reaper] Available ports: {ports or ['(none)']}")
    print(f"  [reaper] Use --list-ports to see options, --midi-port NAME to specify one.")
    return None


def _play_notes(notes, hand, scale, session_id, pub, midi_out):
    """Publish and optionally replay a list of notes with real timing."""
    NOTE_DURATION_S = 0.08  # note held 80ms; fired async so IOI timing is unaffected

    prev_time_ms = notes[0]["time_ms"] if notes else 0.0
    for i, note in enumerate(notes):
        if i > 0:
            gap = (note["time_ms"] - prev_time_ms) / 1000.0
            if gap > 0:
                time.sleep(gap)
        prev_time_ms = note["time_ms"]

        pub.publish_note(note, hand, scale, session_id)
        emit("note_played", note=note["name"], hand=hand)
        print(f"  {'RH' if hand == 'right' else 'LH'} {note['name']:4s}  finger={note['finger']}  vel={note['velocity']}")

        if midi_out:
            midi_out.send_message([0x90, note["midi"], note["velocity"]])
            def _off(out=midi_out, pitch=note["midi"]):
                time.sleep(NOTE_DURATION_S)
                out.send_message([0x80, pitch, 0])
            threading.Thread(target=_off, daemon=True).start()


def _build_segment_doc(rh_notes, lh_notes, session_id):
    def ioi(notes):
        if len(notes) < 2:
            return SYNTHETIC_IOI_MS
        diffs = [notes[i+1]["time_ms"] - notes[i]["time_ms"] for i in range(len(notes)-1)]
        return sum(diffs) / len(diffs)

    avg_ioi = (ioi(rh_notes) + ioi(lh_notes)) / 2
    speed_bpm = round(60000 / avg_ioi, 1)
    hand_metrics = {
        "speed_bpm":          speed_bpm,
        "evenness_stddev_ms": 5.0,
        "evenness_cv_pct":    3.8,
        "per_finger":         {},
    }
    return {
        "timestamp":     time.strftime("%Y-%m-%dT%H:%M:%S"),
        "scale":         "c_major",
        "scale_display": "C Major",
        "segment_index": 1,
        "metrics":       {"right": hand_metrics, "left": {**hand_metrics}},
        "notes":         {"right": rh_notes, "left": lh_notes},
        "session_id":    session_id,
    }


def _simulated_coaching():
    """Emit demo UI events to simulate the coaching pipeline without real API calls."""
    print("  [coach] Simulating coaching pipeline...")
    time.sleep(1.0)
    emit("coach_started", scale="c_major")
    print("  [coach] coach_started")
    time.sleep(1.5)
    emit("mcp_query", scale="c_major")
    print("  [coach] mcp_query #1")
    time.sleep(0.6)
    emit("mcp_query", scale="c_major")
    print("  [coach] mcp_query #2")
    time.sleep(0.6)
    emit("mcp_query", scale="c_major")
    print("  [coach] mcp_query #3")
    time.sleep(0.8)
    emit("chart_generated", scale="c_major")
    print("  [coach] chart_generated")
    time.sleep(0.5)
    emit("webex_sent", scale="c_major")
    print("  [coach] webex_sent")
    time.sleep(2.0)  # let daemon emit threads finish


def _real_coaching(session_id):
    """Run the actual coaching pipeline: Claude + MCP + charts + Webex."""
    try:
        from coach_agent    import run_coach_summary
        from mcp_server     import _dispatch as _mcp_dispatch
        from charts         import render_summary_panel
        from webex_delivery import post_card
    except ImportError as e:
        print(f"  [coach] Import error — {e}. Run with --no-coach to skip.")
        return

    scale = "c_major"
    emit("coach_started", scale=scale)
    print(f"  [coach] Analyzing {scale} (sleeping 3s for Splunk indexing)...")
    time.sleep(3)

    try:
        report = run_coach_summary(session_id, scale)
    except Exception as e:
        print(f"  [coach] Coaching error: {e}")
        return

    panel_path = None
    try:
        history   = _mcp_dispatch("get_scale_history", {"scale": scale})
        emit("mcp_query", scale=scale)
        rh_trends = _mcp_dispatch("get_finger_trends", {"scale": scale, "hand": "right"})
        lh_trends = _mcp_dispatch("get_finger_trends", {"scale": scale, "hand": "left"})
        panel_path = render_summary_panel(scale, history, rh_trends, lh_trends, session_id)
        emit("chart_generated", scale=scale)
    except Exception as e:
        print(f"  [coach] Chart error: {e}")

    if os.environ.get("WEBEX_ROOM_ID"):
        post_card(report, attachment=panel_path)
        emit("webex_sent", scale=scale)
    else:
        print("  [coach] WEBEX_ROOM_ID not set — skipping card.")

    time.sleep(2)  # let daemon emit threads finish


def main():
    parser = argparse.ArgumentParser(description="Replay a C-Major test scale through the demo pipeline.")
    parser.add_argument("--fixture", metavar="PATH",
                        help="JSON fixture to load (default: data/test_fixtures/c_major_recording.json)."
                             " Pass 'synthetic' to use hardcoded notes.")
    parser.add_argument("--reaper", action="store_true",
                        help="Send MIDI to a virtual MIDI port for Reaper/VST playback.")
    parser.add_argument("--midi-port", dest="midi_port", default="TestScale",
                        metavar="NAME",
                        help="Name (or substring) of MIDI output port to use with --reaper."
                             " Default: 'TestScale'. Try 'REAPER Loopback' for Reaper's built-in loopback.")
    parser.add_argument("--list-ports", dest="list_ports", action="store_true",
                        help="List available MIDI output ports and exit.")
    parser.add_argument("--no-coach", dest="no_coach", action="store_true",
                        help="Skip real coaching; emit simulated pipeline events instead.")
    args = parser.parse_args()

    if args.list_ports:
        _list_midi_ports()
        sys.exit(0)

    # ── Load notes ────────────────────────────────────────────────────────────
    use_synthetic = args.fixture == "synthetic"
    fixture_path  = pathlib.Path(args.fixture) if args.fixture and not use_synthetic else FIXTURE_PATH

    if use_synthetic:
        rh_notes, lh_notes = _synthetic_notes()
        print("Using synthetic C-Major notes.")
    elif fixture_path.exists():
        rh_notes, lh_notes = _load_fixture(fixture_path)
        print(f"Loaded fixture: {fixture_path}  ({len(rh_notes)} RH + {len(lh_notes)} LH notes)")
    else:
        rh_notes, lh_notes = _synthetic_notes()
        print(f"Fixture not found ({fixture_path}) — falling back to synthetic notes.")
        print("  Run tools/record_test_scale.py to capture a real recording.")

    # ── Publisher ─────────────────────────────────────────────────────────────
    publisher_type = os.environ.get("PUBLISHER_TYPE", "hec").lower()
    if publisher_type == "hec":
        pub = HECPublisher()
    else:
        pub = MQTTPublisher()
        time.sleep(1.0)
        if not pub.connected:
            print("Could not connect to MQTT broker — check MQTT_HOST/MQTT_PORT.")
            sys.exit(1)

    # ── Reaper MIDI out ───────────────────────────────────────────────────────
    midi_out = _open_reaper_port(args.midi_port) if args.reaper else None

    # ── Session ───────────────────────────────────────────────────────────────
    session_id = time.strftime("TEST_%Y%m%d_%H%M%S")
    print(f"\nTest session: {session_id}  |  coach={'simulated' if args.no_coach else 'real'}"
          f"  |  reaper={'yes' if midi_out else 'no'}\n")

    emit("session_started", session_id=session_id)

    print("Publishing RH notes...")
    _play_notes(rh_notes, "right", "c_major", session_id, pub, midi_out)

    print("Publishing LH notes...")
    _play_notes(lh_notes, "left", "c_major", session_id, pub, midi_out)

    print("\nPublishing segment summary...")
    doc = _build_segment_doc(rh_notes, lh_notes, session_id)
    pub.publish_segment(doc, session_id)
    emit("segment_complete", scale="c_major")
    print(f"  Segment sent — {doc['metrics']['right']['speed_bpm']} BPM")

    if midi_out:
        midi_out.close_port()
        del midi_out

    pub.disconnect()

    # ── Coaching ──────────────────────────────────────────────────────────────
    print()
    if args.no_coach:
        _simulated_coaching()
    else:
        _real_coaching(session_id)

    emit("listening")
    print("\nDone — dashboard reset to listening.")


if __name__ == "__main__":
    main()
