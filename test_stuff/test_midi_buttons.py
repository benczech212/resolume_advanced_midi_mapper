import rtmidi
import time

controller_name = "Launchpad Mini"

def select_port_by_name(midi, port_type="input", keyword=controller_name):
    ports = midi.get_ports()
    for i, name in enumerate(ports):
        if keyword in name:
            midi.open_port(i)
            print(f"✅ Opened {port_type} port: {name}")
            return midi
    print(f"❌ No matching {port_type} ports found with keyword '{keyword}'")
    exit(1)

def main():
    midi_in = rtmidi.MidiIn()
    midi_out = rtmidi.MidiOut()

    midi_in = select_port_by_name(midi_in, "input", controller_name)
    midi_out = select_port_by_name(midi_out, "output", controller_name)

    print(f"\n🎛️ Press a button on your {controller_name}...")

    try:
        while True:
            msg = midi_in.get_message()
            if msg:
                message, delta = msg
                status, note, velocity = message
                print(f"🎹 MIDI Message Received: {message} (Δt: {delta:.4f}s)")

                # Check only that it's a Note On message (status 0x90–0x9F)
                if 0x90 <= status <= 0x9F and velocity > 0:
                    print(f"Button {note} pressed. Velocity: {velocity}")
                    print("💡 Cycling velocity from 0 to 127...")
                    for new_velocity in range(128):
                        midi_out.send_message([0x90, note, new_velocity])
                        # print(f"✅ Sent velocity {new_velocity} to Note {note}")
                        time.sleep(0.02)  # Small delay to see the effect
            time.sleep(0.01)

    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        midi_in.close_port()
        midi_out.close_port()

if __name__ == "__main__":
    main()
