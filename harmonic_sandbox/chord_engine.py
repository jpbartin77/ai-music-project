import mido
import random
from mido import Message, MidiFile, MidiTrack

CHORD_TYPES = {
    'maj': [0, 4, 7],
    'min': [0, 3, 7],
    'm':   [0, 3, 7],
    'dim': [0, 3, 6],
    'aug': [0, 4, 8],
    '7':   [0, 4, 7, 10],
    'maj7':[0, 4, 7, 11],
    'min7':[0, 3, 7, 10],
    'm7':  [0, 3, 7, 10],
    'dim7':[0, 3, 6, 9],
    '9':   [0, 4, 7, 10, 14],
    'b9':  [0, 4, 7, 10, 13],
}

NOTE_MAP = {
    'C': 60, 'C#': 61, 'Db': 61, 'D': 62, 'D#': 63, 'Eb': 63, 'E': 64,
    'F': 65, 'F#': 66, 'Gb': 66, 'G': 67, 'G#': 68, 'Ab': 68,
    'A': 69, 'A#': 70, 'Bb': 70, 'B': 71
}

def parse_chord(chord_name):
    if len(chord_name) > 1 and chord_name[1] in ['#', 'b']:
        root_str = chord_name[:2]
        quality_str = chord_name[2:]
    else:
        root_str = chord_name[:1]
        quality_str = chord_name[1:]
        
    # Base Root (Middle C area)
    base_root = NOTE_MAP.get(root_str, 60) - 12 
    
    if quality_str == "": quality_str = "maj"
    intervals = CHORD_TYPES.get(quality_str, [0, 4, 7]) 
    
    # --- JAZZ VOICING LOGIC ---
    voiced_notes = []
    
    # 1. The Anchor: Drop the Root way down (Bass Player)
    voiced_notes.append(base_root - 12)
    
    # 2. The Colors: Spread the other notes out
    for i in intervals:
        if i == 0: continue # We already added the bass root
        
        note_val = base_root + i
        
        # Rule A: Always bump the 3rd UP an octave (Open the sound)
        # (3rds are intervals 3 or 4)
        if i in [3, 4]:
            note_val += 12
            
        # Rule B: Bump Extensions (9ths) UP an octave (Sparkle)
        if i > 12:
            note_val += 12
            
        # Rule C: Keep 5ths and 7ths in the middle range
        # (No change needed)
        
        voiced_notes.append(note_val)
        
    # Sort them so they play in order (helps the visualizer look clean)
    voiced_notes.sort()
    return voiced_notes

def generate_progression(chord_list, filename="generated_progression.mid"):
    # print(f"🎵 Generating Jazz-Voiced MIDI for: {chord_list}")
    mid = MidiFile()
    track = MidiTrack()
    mid.tracks.append(track)
    track.append(Message('program_change', program=0, time=0))
    
    # Slow & Deep (960 ticks per beat)
    TICKS_PER_BEAT = 960 
    
    try:
        for chord_name in chord_list:
            notes = parse_chord(chord_name)
            
            # --- HUMANIZER START ---
            accumulated_strum = 0
            
            for note in notes:
                # Velocity Jitter
                human_velocity = random.randint(75, 105) # Slightly louder for jazz
                
                # Strumming (Arpeggiation)
                strum_ticks = random.randint(0, 15)
                accumulated_strum += strum_ticks
                
                track.append(Message('note_on', note=note, velocity=human_velocity, time=strum_ticks))
            
            # --- HUMANIZER END ---
            base_duration = TICKS_PER_BEAT - accumulated_strum
            
            is_first_release = True
            for note in notes:
                release_jitter = random.randint(0, 20)
                if is_first_release:
                    delta_time = base_duration + release_jitter
                    is_first_release = False
                else:
                    delta_time = release_jitter
                
                track.append(Message('note_off', note=note, velocity=60, time=delta_time))
                
        mid.save(filename)
        return True
    except Exception as e:
        # print(f"❌ Error: {e}")
        return False