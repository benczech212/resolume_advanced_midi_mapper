import time
import rtmidi

# === Settings ===
NOTE_RANGE = range(0, 128)        # Test all 128 possible notes
VELOCITY_RANGE = range(0, 7)      # Use 0–6 to match APC40 LED behavior
DELAY = 0.01                       # Delay between messages (in seconds)

# === Find and open the APC40 output port ===
midi_out = rtmidi.MidiOut()
port_name_match = "APC"

ports = midi_out.get_ports()
matched_index = next((i for i, name in enumerate(ports) if port_name_match in name), None)

if matched_index is None:
    print(f"❌ Could not find output port with name containing '{port_name_match}'")
    exit(1)

midi_out.open_port(matched_index)
print(f"✅ Opened output port: {ports[matched_index]}")

# === Test loop ===
print(f"\n🧪 Testing all notes (0–127) with velocities {list(VELOCITY_RANGE)}")

try:
    for note in NOTE_RANGE:
        for velocity in VELOCITY_RANGE:
            msg = [0x90, note, velocity]  # Note On on Channel 1
            midi_out.send_message(msg)
            print(f"Sent: Note {note}, Velocity {velocity}")
            time.sleep(DELAY)

        # Optional: turn the note off (some controllers will stay lit)
        midi_out.send_message([0x90, note, 0])
        time.sleep(0.05)

except KeyboardInterrupt:
    print("🛑 Stopped by user.")

finally:
    midi_out.close_port()
    print("✅ MIDI output closed.")
