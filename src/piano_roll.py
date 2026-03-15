import mido
import pretty_midi
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import numpy as np
import time
import rtmidi

# ── PART 1: Record MIDI to file ──────────────────────────────────────────────

def record_midi(output_file="data/recording.mid", duration=15):
    """Record MIDI input from piano for a set duration."""
    
    import os
    os.makedirs("data", exist_ok=True)
    
    midi_in = rtmidi.MidiIn()
    ports = midi_in.get_ports()
    
    if not ports:
        print("No MIDI devices found!")
        return False
    
    print(f"Recording from: {ports[0]}")
    print(f"Recording for {duration} seconds... Play something!\n")
    
    midi_in.open_port(0)
    
    mid = mido.MidiFile()
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage('set_tempo', tempo=500000))
    
    messages = []
    start_time = time.time()
    last_time = start_time
    
    def callback(message, data=None):
        nonlocal last_time
        msg, delta = message
        now = time.time()
        elapsed = now - last_time
        last_time = now
        ticks = int(elapsed * 1000)
        messages.append((ticks, msg))
        status = msg[0]
        if status == 144 and msg[2] > 0:
            notes = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
            note = notes[msg[1] % 12] + str((msg[1] // 12) - 1)
            print(f"  ♪ {note} (velocity {msg[2]})")
    
    midi_in.set_callback(callback)
    
    for i in range(duration, 0, -1):
        print(f"\r  Time remaining: {i}s  ", end="", flush=True)
        time.sleep(1)
    
    print(f"\n\nRecording complete! Captured {len(messages)} events.")
    
    for ticks, msg in messages:
        try:
            track.append(mido.Message(
                'note_on' if msg[0] == 144 else 'note_off',
                note=msg[1],
                velocity=msg[2],
                time=ticks
            ))
        except Exception:
            pass
    
    midi_in.close_port()
    mid.save(output_file)
    print(f"Saved to: {output_file}")
    return True

# ── PART 2: Render piano roll ─────────────────────────────────────────────────

def render_piano_roll(midi_file="data/recording.mid"):
    """Render a MIDI file as a piano roll visualisation."""
    
    pm = pretty_midi.PrettyMIDI(midi_file)
    
    fig, ax = plt.subplots(figsize=(14, 6))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#1a1a2e')
    
    note_names = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
    colors = {
        'white': '#4a9eff',
        'black': '#ff6b9d',
    }
    black_notes = {1, 3, 6, 8, 10}
    
    all_notes = []
    for instrument in pm.instruments:
        for note in instrument.notes:
            all_notes.append(note)
    
    if not all_notes:
        print("No notes found in MIDI file!")
        return
    
    min_pitch = min(n.pitch for n in all_notes) - 2
    max_pitch = max(n.pitch for n in all_notes) + 2
    
    for note in all_notes:
        is_black = (note.pitch % 12) in black_notes
        color = colors['black'] if is_black else colors['white']
        duration = note.end - note.start
        alpha = 0.6 + (note.velocity / 127) * 0.4
        
        rect = patches.FancyBboxPatch(
            (note.start, note.pitch - 0.4),
            duration, 0.8,
            boxstyle="round,pad=0.02",
            facecolor=color,
            edgecolor='none',
            alpha=alpha
        )
        ax.add_patch(rect)
    
    # Y axis — note names
    ax.set_ylim(min_pitch, max_pitch)
    yticks = range(int(min_pitch), int(max_pitch) + 1)
    ax.set_yticks(list(yticks))
    ax.set_yticklabels([
        f"{note_names[p % 12]}{(p // 12) - 1}" for p in yticks
    ], fontsize=8, color='#888888')
    
    # X axis — time
    end_time = max(n.end for n in all_notes)
    ax.set_xlim(0, end_time + 0.5)
    ax.set_xlabel("Time (seconds)", color='#888888', fontsize=10)
    
    # Grid lines at C notes
    for pitch in yticks:
        if pitch % 12 == 0:
            ax.axhline(y=pitch, color='#333355', linewidth=0.5, zorder=0)
    
    ax.tick_params(colors='#888888')
    for spine in ax.spines.values():
        spine.set_edgecolor('#333333')
    
    ax.set_title(
        f"Piano Roll — {len(all_notes)} notes",
        color='white', fontsize=13, pad=12
    )
    
    plt.tight_layout()
    
    output_img = midi_file.replace('.mid', '_roll.png')
    plt.savefig(output_img, dpi=150, bbox_inches='tight',
                facecolor='#1a1a2e')
    print(f"Piano roll saved to: {output_img}")
    plt.show()

# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Piano Roll Recorder & Visualiser ===\n")
    
    if record_midi(duration=15):
        print("\nRendering piano roll...")
        render_piano_roll()
