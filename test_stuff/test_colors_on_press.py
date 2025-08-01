import rtmidi
import time

# === Settings ===
VELOCITY_RANGE = range(0, 7)  # For testing LED behavior (APC40 uses 0–6)
DELAY = 0.5                   # Time between lighting steps

# === Utility: Open a named port ===
def open_named_port(midi, name_match, port_type="input"):
    ports = midi.get_ports()
    for i, port in enumerate(ports):
        if name_match.lower() in port.lower():
            midi.open_port(i)
            print(f"✅ Opened {port_type} port: {port}")
            return
    raise RuntimeError(f"❌ {port_type.capitalize()} port containing '{name_match}' not found.")

# === Main Loop ===
def main():
    midi_in = rtmidi.MidiIn()
    midi_out = rtmidi.MidiOut()

    # Set to "APC" or use "Virtual MIDI" if routing via loopMIDI
    open_named_port(midi_in, "APC", "input")
    open_named_port(midi_out, "APC", "output")

    print("🎛️ Listening for Note or CC messages on your MIDI controller...")

    try:
        while True:
            msg = midi_in.get_message()
            if msg:
                message, delta = msg
                status, data1, data2 = message

                # Note On (Channel 1–16): 0x90 to 0x9F
                if 0x90 <= status <= 0x9F and data2 > 0:
                    note = data1
                    velocity = data2
                    print(f"\n🎹 NOTE ON: Note {note} | Velocity {velocity}")
                    print(f"🔁 Cycling velocities for Note {note}...")

                    for v in VELOCITY_RANGE:
                        midi_out.send_message([0x90, note, v])
                        print(f"  ➜ Sent velocity {v}")
                        time.sleep(DELAY)

                    # Turn off after test
                    midi_out.send_message([0x90, note, 0])
                    print(f"✅ Done. Note {note} turned off.")

                # Note Off
                elif 0x80 <= status <= 0x8F:
                    print(f"🎹 NOTE OFF: Note {data1}")

                # Control Change (CC)
                elif 0xB0 <= status <= 0xBF:
                    cc = data1
                    value = data2
                    print(f"🎛 CONTROL CHANGE: CC {cc} | Value {value}")

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n🛑 Exiting...")
    finally:
        midi_in.close_port()
        midi_out.close_port()
        print("✅ MIDI ports closed.")

if __name__ == "__main__":
    main()
