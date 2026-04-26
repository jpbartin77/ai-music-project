import rtmidi
import time

def note_number_to_name(note_number):
    notes = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
    octave = (note_number // 12) - 1
    note = notes[note_number % 12]
    return f"{note}{octave}"

def midi_callback(message, data=None):
    msg, delta_time = message
    status = msg[0]
    kind = status & 0xF0
    ch   = (status & 0x0F) + 1

    if kind == 0x90 and len(msg) > 2:
        is_on = msg[2] > 0
        note  = note_number_to_name(msg[1])
        label = "NOTE ON " if is_on else "NOTE OFF"
        marker = "  *** A0 STOP KEY ***" if msg[1] == 21 and is_on else ""
        print(f"{label} | ch={ch} | {note:<4} (MIDI {msg[1]:3d}) | vel={msg[2]:3d}{marker}")
    elif kind == 0x80 and len(msg) > 1:
        note = note_number_to_name(msg[1])
        print(f"NOTE OFF | ch={ch} | {note:<4} (MIDI {msg[1]:3d})")
    else:
        print(f"RAW      | {[hex(b) for b in msg]}")

def main():
    midi_in = rtmidi.MidiIn()
    ports = midi_in.get_ports()
    
    print("=== Available MIDI Devices ===")
    if not ports:
        print("No MIDI devices found. Is your piano connected and on?")
        return
    
    for i, port in enumerate(ports):
        print(f"  [{i}] {port}")
    
    print("\nConnecting to port 0...")
    midi_in.open_port(0)
    midi_in.set_callback(midi_callback)
    
    print("Listening for MIDI input. Play something! (Ctrl+C to stop)\n")
    
    try:
        while True:
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nStopped.")
    
    midi_in.close_port()

if __name__ == "__main__":
    main()