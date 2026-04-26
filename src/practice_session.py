"""
practice_session.py — Two-handed scale practice capture and scoring.

Auto-detects the scale being played from the fingering file, splits the
MIDI stream into left/right hand events, and scores each complete scale
run on speed, evenness, and per-finger timing.

Segments are separated by 2-second silences. Single-hand segments are
discarded. Output is one JSON file per valid segment in data/sessions/.
"""

import argparse
import queue
import rtmidi
import mido
import time
import json
import os
import re
import threading
import numpy as np
from datetime import datetime
import sys, pathlib

# Force UTF-8 and line-buffering so prints appear immediately even when stdout is piped via op run
sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from mqtt_publisher import MQTTPublisher
from hec_publisher import HECPublisher
from demo_emitter import emit as _emit

# Eagerly import the coach modules at startup. Their transitive imports (mcp → jsonschema →
# rfc3987_syntax → lark grammar compilation) take a few seconds the first time. Doing it here
# means the cost is paid before MIDI capture starts, not at session end where the user expects
# fast summary delivery.
_auto_coach   = os.environ.get('AUTO_COACH', 'true').lower() == 'true'
_summary_mode = os.environ.get('SUMMARY_MODE', 'true').lower() == 'true'
if _auto_coach or _summary_mode:
    print("Loading coaching modules...", flush=True)
    from coach_agent    import run_coach, run_coach_summary
    from webex_delivery import post_card, post_analyzing_notice
    from charts         import render_summary_panel
    from mcp_server     import _dispatch as _mcp_dispatch
else:
    run_coach = run_coach_summary = post_card = post_analyzing_notice = render_summary_panel = _mcp_dispatch = None

NOTE_NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B']
FINGER_NAMES = {1: "Thumb", 2: "Index", 3: "Middle", 4: "Ring", 5: "Pinky"}
GAP_SECONDS = 2.0
MIN_NOTES_PER_HAND = 4
FINGERINGS_PATH = "config/fingerings.md"


def note_name(midi):
    return f"{NOTE_NAMES[midi % 12]}{(midi // 12) - 1}"


# ── Fingering loader ──────────────────────────────────────────────────────────

def load_fingerings(path=FINGERINGS_PATH):
    """Parse fingerings.md → dict of scale data keyed by snake_case name."""
    with open(path, 'r') as f:
        content = f.read()

    # Semitone offsets from root for a 2-octave major scale (15 notes ascending)
    STEPS_2OCT = [0, 2, 4, 5, 7, 9, 11, 12, 14, 16, 17, 19, 21, 23, 24]
    # The 7 unique pitch-class offsets used for scale candidate detection
    SEMITONES_1OCT = [0, 2, 4, 5, 7, 9, 11]

    scales = {}
    for section in re.split(r'\n(?=## )', content):
        header = re.match(r'## (.+)', section)
        if not header:
            continue
        display = header.group(1).strip()
        key = display.lower().replace(' ', '_').replace('#', 's').replace('/', '_')

        root_m = re.search(r'\*\*Root MIDI:\*\*\s*(\d+)', section)
        rh_m   = re.search(r'\*\*RH:\*\*\s*([\d\s]+)', section)
        lh_m   = re.search(r'\*\*LH:\*\*\s*([\d\s]+)', section)
        if not (root_m and rh_m and lh_m):
            continue

        root_midi = int(root_m.group(1))
        rh = [int(x) for x in rh_m.group(1).split()]
        lh = [int(x) for x in lh_m.group(1).split()]

        pitch_classes = frozenset((root_midi % 12 + s) % 12 for s in SEMITONES_1OCT)
        scales[key] = {
            'display': display,
            'root_midi': root_midi,
            'steps_2oct': STEPS_2OCT,
            'pitch_classes': pitch_classes,
            'fingering': {'right': rh, 'left': lh},
        }
    return scales


# ── Scale position tracker ────────────────────────────────────────────────────

class HandScaleTracker:
    """
    Tracks sequential position within a 2-octave scale for one hand and
    returns the correct finger for each incoming note.

    Uses the delta from the first (root) note to determine scale position,
    so the player can start in any octave. Handles ascending and descending.
    """

    def __init__(self, fingers_asc):
        self.fingers_asc  = fingers_asc            # 15 fingers, ascending
        self.fingers_desc = list(reversed(fingers_asc))   # descending
        self.base_midi = None
        self.pos = 0

    def get_finger(self, midi):
        if self.base_midi is None:
            self.base_midi = midi
            self.pos = 0
            return self.fingers_asc[0]

        delta = midi - self.base_midi
        steps = [0, 2, 4, 5, 7, 9, 11, 12, 14, 16, 17, 19, 21, 23, 24]
        if delta not in steps:
            return None

        new_pos = steps.index(delta)
        ascending = new_pos >= self.pos
        self.pos = new_pos

        if ascending:
            return self.fingers_asc[new_pos]
        else:
            return self.fingers_desc[14 - new_pos]


# ── Hand splitter ─────────────────────────────────────────────────────────────

class HandSplitter:
    """
    Splits a single MIDI stream into left and right hand events.

    First two notes establish LH (lower MIDI) and RH (higher MIDI).
    Subsequent notes are assigned to whichever hand's last note is closer.
    State persists across segments so hands don't need re-establishing
    after each 2-second gap.
    """

    def __init__(self):
        self._buf = []          # (midi, time_ms) — holds first note until second arrives
        self._active = False
        self.lh_last = None
        self.rh_last = None

    def assign(self, midi, time_ms):
        """Returns list of (midi, hand, time_ms) — 0, 1, or 2 items."""
        if not self._active:
            self._buf.append((midi, time_ms))
            if len(self._buf) < 2:
                return []
            (n1, t1), (n2, t2) = self._buf
            self._buf = []
            self._active = True
            if n1 < n2:
                self.lh_last, self.rh_last = n1, n2
                return [(n1, 'left', t1), (n2, 'right', t2)]
            else:
                self.lh_last, self.rh_last = n2, n1
                return [(n1, 'right', t1), (n2, 'left', t2)]

        lh_d = abs(midi - self.lh_last)
        rh_d = abs(midi - self.rh_last)
        hand = 'left' if lh_d <= rh_d else 'right'
        if hand == 'left':
            self.lh_last = midi
        else:
            self.rh_last = midi
        return [(midi, hand, time_ms)]


# ── Segment ───────────────────────────────────────────────────────────────────

class Segment:
    """
    Collects events for one scale run and validates them in real time.

    Validation rules:
    - Each note must be within ±2 semitones of the previous note in the
      same hand stream (enforces scale step sizes).
    - Each note's pitch class must match at least one candidate scale.
    Once a segment is marked invalid, further notes are ignored until the
    next 2-second gap resets it.
    """

    def __init__(self, scales):
        self.lh_events = []
        self.rh_events = []
        self.candidates = set(scales.keys())
        self._scales = scales
        self._locked = None
        self.valid = True
        self._lh_tracker = None
        self._rh_tracker = None

    def _init_trackers(self, scale_name):
        scale = self._scales[scale_name]
        self._lh_tracker = HandScaleTracker(scale['fingering']['left'])
        self._rh_tracker = HandScaleTracker(scale['fingering']['right'])
        # Retroactively assign fingers to already-collected events
        for e in self.lh_events:
            e['finger'] = self._lh_tracker.get_finger(e['midi'])
        for e in self.rh_events:
            e['finger'] = self._rh_tracker.get_finger(e['midi'])

    def add(self, event, hand):
        if not self.valid:
            return

        stream  = self.lh_events   if hand == 'left' else self.rh_events
        tracker = self._lh_tracker if hand == 'left' else self._rh_tracker

        # Step size check — only from the second note in each hand stream
        if stream:
            step = abs(event['midi'] - stream[-1]['midi'])
            if step > 2:
                self.valid = False
                print(f"  [step {step}st too large — discarded, wait 2s]")
                return

        # Narrow scale candidates by pitch class
        pc = event['midi'] % 12
        self.candidates = {s for s in self.candidates
                           if pc in self._scales[s]['pitch_classes']}
        if not self.candidates:
            self.valid = False
            print(f"  [{event['name']} matches no scale — discarded, wait 2s]")
            return

        event['finger'] = tracker.get_finger(event['midi']) if tracker else None
        stream.append(event)

        if len(self.candidates) == 1 and self._locked is None:
            self._locked = next(iter(self.candidates))
            self._init_trackers(self._locked)
            print(f"  → Scale identified: {self._scales[self._locked]['display']}")

    @property
    def scale_name(self):
        if self._locked:
            return self._locked
        return next(iter(self.candidates)) if len(self.candidates) == 1 else None

    def is_useful(self):
        return (self.valid
                and len(self.lh_events) >= MIN_NOTES_PER_HAND
                and len(self.rh_events) >= MIN_NOTES_PER_HAND
                and self.scale_name is not None)


# ── Metrics ───────────────────────────────────────────────────────────────────

def compute_hand_metrics(events, scale=None, hand=None):
    if len(events) < 2:
        return None
    times = np.array([e['time_ms'] for e in events])
    ioi = np.diff(times)
    mean_ioi = float(np.mean(ioi))

    finger_iois = {}
    for i in range(1, len(events)):
        f = events[i].get('finger')
        if f:
            finger_iois.setdefault(f, []).append(float(times[i] - times[i - 1]))

    per_finger = {}
    for f, iois in sorted(finger_iois.items()):
        mean_t = float(np.mean(iois))
        per_finger[str(f)] = {
            'name': FINGER_NAMES.get(f, f'Finger {f}'),
            'note_count': len(iois),
            'mean_interval_ms': round(mean_t, 1),
            'deviation_from_avg_ms': round(mean_t - mean_ioi, 1),
            'stddev_ms': round(float(np.std(iois)), 1) if len(iois) > 1 else 0.0,
        }

    return {
        'speed_bpm': round(60000 / mean_ioi, 1),
        'mean_ioi_ms': round(mean_ioi, 1),
        'evenness_stddev_ms': round(float(np.std(ioi)), 2),
        'evenness_cv_pct': round(float(np.std(ioi) / mean_ioi * 100), 1),
        'per_finger': per_finger,
    }


# ── Display ───────────────────────────────────────────────────────────────────

def print_segment_results(seg, scales):
    scale = scales[seg.scale_name]
    print(f"\n{'='*56}")
    print(f"  {scale['display']}  "
          f"(LH: {len(seg.lh_events)} notes  RH: {len(seg.rh_events)} notes)")
    for hand, events in [('right', seg.rh_events), ('left', seg.lh_events)]:
        m = compute_hand_metrics(events)
        if not m:
            continue
        label = hand.capitalize() + ' Hand'
        print(f"\n  {label}:  {m['speed_bpm']} BPM  "
              f"±{m['evenness_stddev_ms']}ms evenness ({m['evenness_cv_pct']}%)")
        print(f"  {'Finger':<10} {'Notes':>5} {'Avg':>10} {'vs Avg':>10} {'StdDev':>8}")
        print(f"  {'-'*47}")
        for _, d in m['per_finger'].items():
            dev = d['deviation_from_avg_ms']
            dev_str = f"+{dev:.1f}" if dev > 0 else f"{dev:.1f}"
            flag = "  ← slow" if dev > 20 else ("  ← fast" if dev < -20 else "")
            print(f"  {d['name']:<10} {d['note_count']:>5} "
                  f"{d['mean_interval_ms']:>7.1f}ms "
                  f"{dev_str:>8}ms  {d['stddev_ms']:>5.1f}ms{flag}")
    print(f"{'='*56}\n")


# ── Save ──────────────────────────────────────────────────────────────────────

def save_segment(seg, scales, index, session_id=None):
    os.makedirs('data/sessions', exist_ok=True)
    prefix = session_id or datetime.now().strftime('%Y%m%d_%H%M%S')
    base = f"data/sessions/{prefix}_seg{index:02d}_{seg.scale_name}"
    scale = scales[seg.scale_name]

    doc = {
        'session_id': session_id,
        'timestamp': datetime.now().isoformat(),
        'scale': seg.scale_name,
        'scale_display': scale['display'],
        'segment_index': index,
        'metrics': {
            'right': compute_hand_metrics(seg.rh_events),
            'left': compute_hand_metrics(seg.lh_events),
        },
        'notes': {
            'right': seg.rh_events,
            'left': seg.lh_events,
        },
    }
    path = f"{base}.json"
    with open(path, 'w') as f:
        json.dump(doc, f, indent=2)
    print(f"  Saved: {path}")
    return doc


# ── Coach trigger ─────────────────────────────────────────────────────────────

def _maybe_run_coach(segment_session_id):
    """Run per-segment coaching analysis and post to Webex."""
    if not _auto_coach:
        return
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print("  [coach] ANTHROPIC_API_KEY not set -- skipping.")
        return
    try:
        print("  [coach] Analyzing session...")
        report = run_coach(segment_session_id)
        if os.environ.get('WEBEX_ROOM_ID'):
            post_card(report)
        else:
            print("  [coach] WEBEX_ROOM_ID not set -- skipping card delivery.")
    except Exception as e:
        print(f"  [coach] Error: {e}")


def _run_session_summary(session_id, scales_played):
    """Run one summary coaching analysis (with charts) per scale played in this session."""
    if not scales_played:
        return
    if not os.environ.get('ANTHROPIC_API_KEY'):
        print("  [summary] ANTHROPIC_API_KEY not set -- skipping.")
        return
    print(f"\n[summary] Analyzing {len(scales_played)} scale(s) from this session...")
    for scale in scales_played:
        try:
            _emit('coach_started', scale=scale)
            report = run_coach_summary(session_id, scale)

            # Pull data for charts. Failures here shouldn't block card delivery.
            panel_path = None
            try:
                history    = _mcp_dispatch("get_scale_history",  {"scale": scale})
                _emit('mcp_query', scale=scale)
                rh_trends  = _mcp_dispatch("get_finger_trends",  {"scale": scale, "hand": "right"})
                lh_trends  = _mcp_dispatch("get_finger_trends",  {"scale": scale, "hand": "left"})
                panel_path = render_summary_panel(scale, history, rh_trends, lh_trends, session_id)
                _emit('chart_generated', scale=scale)
            except Exception as e:
                print(f"  [summary] Chart generation failed for {scale}: {e}")

            if os.environ.get('WEBEX_ROOM_ID'):
                post_card(report, attachment=panel_path)
                _emit('webex_sent', scale=scale)
            else:
                print("  [summary] WEBEX_ROOM_ID not set -- skipping card delivery.")
        except Exception as e:
            print(f"  [summary] Error coaching {scale}: {e}")


# ── Session ───────────────────────────────────────────────────────────────────

def run_session(scales, max_minutes=5, summary=True):
    midi_in = rtmidi.MidiIn()
    ports = midi_in.get_ports()
    if not ports:
        print("No MIDI devices found!")
        return

    print(f"\nConnected: {ports[0]}")
    print(f"Play any major scale with both hands.")
    print(f"2-second pause ends each run. Press A0 (lowest key) or Ctrl+C to finish.\n")

    midi_in.open_port(0)
    start_time = time.perf_counter()
    session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    _emit('session_started', session_id=session_id)

    publisher_type = os.environ.get('PUBLISHER_TYPE', 'hec').lower()
    publisher = HECPublisher() if publisher_type == 'hec' else MQTTPublisher()
    stop_event = threading.Event()

    summary_mode = summary
    if summary_mode:
        print("  [mode] summary mode -- one card per scale at session end (no per-segment cards)")

    # ── Non-blocking publish queue ────────────────────────────────────────────
    # All HEC POSTs run in a background thread so the MIDI callback never stalls
    # waiting on network. The queue drainer flushes before the session exits.
    _pub_q = queue.Queue()

    def _publish_worker():
        while True:
            item = _pub_q.get()
            if item is None:        # poison pill — drain complete
                _pub_q.task_done()
                break
            kind, args = item
            if kind == 'note':
                publisher.publish_note(*args)
            elif kind == 'segment':
                publisher.publish_segment(*args)
            _pub_q.task_done()

    _pub_thread = threading.Thread(target=_publish_worker, daemon=True, name='hec-publisher')
    _pub_thread.start()

    lock = threading.Lock()
    state = {
        'segment': Segment(scales),
        'splitter': HandSplitter(),
        'gap_timer': None,
        'seg_count': 0,
        'scales_played': [],   # ordered list of distinct scale names played
    }

    def process_and_reset():
        seg_snapshot = None
        seg_index = None
        discard_msg = None

        with lock:
            seg = state['segment']
            if seg.is_useful():
                state['seg_count'] += 1
                seg_snapshot = seg
                seg_index = state['seg_count']
                if seg.scale_name and seg.scale_name not in state['scales_played']:
                    state['scales_played'].append(seg.scale_name)
            else:
                ln = len(seg.lh_events)
                rn = len(seg.rh_events)
                if ln > 0 or rn > 0:
                    if ln == 0 or rn == 0:
                        discard_msg = f"  [single hand only (LH:{ln} RH:{rn}) -- discarded]"
                    else:
                        discard_msg = f"  [too short or no scale (LH:{ln} RH:{rn}) -- discarded]"
            state['segment'] = Segment(scales)

        # All I/O outside the lock: print, disk write, queue — none of these block MIDI
        if discard_msg:
            print(discard_msg)
        if seg_snapshot is not None:
            print_segment_results(seg_snapshot, scales)
            doc = save_segment(seg_snapshot, scales, seg_index, session_id)
            _pub_q.put(('segment', (doc, session_id)))
            rh_bpm = doc.get('metrics', {}).get('right', {}) or {}
            _emit('segment_complete',
                  index=seg_index, scale=seg_snapshot.scale_name,
                  rh_bpm=round(rh_bpm.get('speed_bpm', 0), 1))
            if not summary_mode:
                _maybe_run_coach(session_id)

    def on_gap():
        process_and_reset()

    def reset_gap_timer():
        if state['gap_timer']:
            state['gap_timer'].cancel()
        t = threading.Timer(GAP_SECONDS, on_gap)
        t.daemon = True
        t.start()
        state['gap_timer'] = t

    def callback(message, _=None):
        msg, _ = message
        if msg[0] & 0xF0 != 0x90:   # NOTE_ON on any channel
            return

        midi = msg[1]

        if midi == 21:  # A0 — stop session (check before velocity filter)
            print("\n  [A0 pressed — ending session...]")
            _emit('session_ended', segments=state['seg_count'])
            stop_event.set()
            return

        if msg[2] == 0:             # velocity=0 is a note-off
            return

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        note_lines = []
        note_publishes = []
        with lock:
            assignments = state['splitter'].assign(midi, elapsed_ms)
            for note_midi, hand, note_time in assignments:
                event = {
                    'time_ms': note_time,
                    'midi': note_midi,
                    'name': note_name(note_midi),
                    'velocity': msg[2],
                }
                state['segment'].add(event, hand)
                finger = event.get('finger')
                flabel = FINGER_NAMES.get(finger, '?') if finger else '?'
                note_lines.append(
                    f"  ♪ {note_name(note_midi):<4} {hand[0].upper()}H  "
                    f"finger:{flabel:<8}  t:{note_time:8.0f}ms"
                )
                note_publishes.append(
                    (dict(event), hand, state['segment'].scale_name or 'unknown')
                )

        # All I/O outside the lock: terminal writes and queue puts are non-blocking
        for line in note_lines:
            print(line)
        for (ev_dict, hand, scale_name), line in zip(note_publishes, note_lines):
            _pub_q.put(('note', (ev_dict, hand, scale_name, session_id)))
            _emit('note_played', note=ev_dict['name'], hand=hand,
                  finger=ev_dict.get('finger'), scale=scale_name)

        reset_gap_timer()

    midi_in.set_callback(callback)

    deadline = start_time + max_minutes * 60
    try:
        while not stop_event.is_set():
            remaining = deadline - time.perf_counter()
            if remaining <= 0:
                break
            stop_event.wait(timeout=min(0.5, remaining))
    except KeyboardInterrupt:
        pass

    if state['gap_timer']:
        state['gap_timer'].cancel()
    midi_in.close_port()

    # Process any final segment, then flush pending HEC posts (max 10s)
    process_and_reset()
    _pub_q.put(None)                    # poison pill
    _pub_thread.join(timeout=10)        # don't hang forever if Splunk is slow
    publisher.disconnect()
    print(f"\nSession complete. {state['seg_count']} segment(s) saved to data/sessions/")

    # Summary coaching: one card per scale-type at session end
    if summary_mode and state['scales_played']:
        if post_analyzing_notice and os.environ.get('WEBEX_ROOM_ID'):
            post_analyzing_notice(state['scales_played'])
        # Brief pause to let HEC events index in Splunk before MCP queries
        time.sleep(3)
        _run_session_summary(session_id, state['scales_played'])


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Scale practice session')
    parser.add_argument('--minutes', '-m', type=int, default=5,
                        help='Session duration in minutes (default: 5)')
    parser.add_argument('--summary', action=argparse.BooleanOptionalAction, default=True,
                        help='Generate summary card at session end (default: on)')
    args = parser.parse_args()

    print('=== Scale Practice Session ===\n')
    scales = load_fingerings()
    print(f"Loaded {len(scales)} scales from {FINGERINGS_PATH}\n")
    run_session(scales, max_minutes=args.minutes, summary=args.summary)
