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
    
    if status == 144 and msg[2] > 0:  # Note On
        note = note_number_to_name(msg[1])
        velocity = msg[2]
        print(f"NOTE ON  | {note:<4} | velocity: {velocity}")
    
    elif status == 128 or (status == 144 and msg[2] == 0):  # Note Off
        note = note_number_to_name(msg[1])
        print(f"NOTE OFF | {note:<4}")

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