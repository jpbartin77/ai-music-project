"""
practice_session.py — Two-handed scale practice capture and scoring.

Auto-detects the scale being played from the fingering file, splits the
MIDI stream into left/right hand events, and scores each complete scale
run on speed, evenness, and per-finger timing.

Segments are separated by 2-second silences. Single-hand segments are
discarded. Output is one JSON file per valid segment in data/sessions/.
"""

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
sys.path.insert(0, str(pathlib.Path(__file__).parent))
from mqtt_publisher import MQTTPublisher

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

def save_segment(seg, scales, index):
    os.makedirs('data/sessions', exist_ok=True)
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    base = f"data/sessions/{ts}_seg{index:02d}_{seg.scale_name}"
    scale = scales[seg.scale_name]

    doc = {
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


# ── Session ───────────────────────────────────────────────────────────────────

def run_session(scales, max_minutes=5):
    midi_in = rtmidi.MidiIn()
    ports = midi_in.get_ports()
    if not ports:
        print("No MIDI devices found!")
        return

    print(f"\nConnected: {ports[0]}")
    print(f"Play any major scale with both hands.")
    print(f"2-second pause ends each run. Ctrl+C to finish.\n")

    midi_in.open_port(0)
    start_time = time.perf_counter()
    session_id = datetime.now().strftime('%Y%m%d_%H%M%S')

    publisher = MQTTPublisher()

    lock = threading.Lock()
    state = {
        'segment': Segment(scales),
        'splitter': HandSplitter(),
        'gap_timer': None,
        'seg_count': 0,
    }

    def process_and_reset():
        with lock:
            seg = state['segment']
            if seg.is_useful():
                state['seg_count'] += 1
                print_segment_results(seg, scales)
                doc = save_segment(seg, scales, state['seg_count'])
                publisher.publish_segment(doc, session_id)
            else:
                ln = len(seg.lh_events)
                rn = len(seg.rh_events)
                if ln > 0 or rn > 0:
                    if ln == 0 or rn == 0:
                        print(f"  [single hand only (LH:{ln} RH:{rn}) — discarded]")
                    else:
                        print(f"  [too short or no scale (LH:{ln} RH:{rn}) — discarded]")
            # Splitter persists — hands already established
            state['segment'] = Segment(scales)

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
        if msg[0] != 144 or msg[2] == 0:   # NOTE_ON with velocity > 0 only
            return

        midi = msg[1]
        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

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
                print(f"  ♪ {note_name(note_midi):<4} {hand[0].upper()}H  "
                      f"finger:{flabel:<8}  t:{note_time:8.0f}ms")
                publisher.publish_note(
                    event, hand, state['segment'].scale_name or 'unknown', session_id
                )

        reset_gap_timer()

    midi_in.set_callback(callback)

    try:
        time.sleep(max_minutes * 60)
    except KeyboardInterrupt:
        pass

    if state['gap_timer']:
        state['gap_timer'].cancel()
    midi_in.close_port()

    # Process any final segment
    process_and_reset()
    publisher.disconnect()
    print(f"\nSession complete. {state['seg_count']} segment(s) saved to data/sessions/")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('=== Scale Practice Session ===\n')
    scales = load_fingerings()
    print(f"Loaded {len(scales)} scales from {FINGERINGS_PATH}\n")
    minutes = int(input('Max session minutes [5]: ').strip() or 5)
    run_session(scales, max_minutes=minutes)
