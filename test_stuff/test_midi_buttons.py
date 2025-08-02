import rtmidi
import time
import json
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

                    # Step through velocities quickly
                    print("Stepping through velocities 1-127 quickly...")
                    for v in range(1, 128):
                        midi_out.send_message([status, note, v])
                        time.sleep(0.03)  # 30ms per step for visibility

                    # Prompt user for each velocity
                    velocity_map = {}
                    for v in range(1, 128):
                        midi_out.send_message([status, note, v])
                        color = input(f"Enter color for Note {note} at Velocity {v} (or 'skip' to skip): ").strip()
                        if color.lower() == 'skip':
                            continue
                        orig_color = color
                        count = 1
                        while color in velocity_map:
                            count += 1
                            color = f"{orig_color}_{count}"
                        velocity_map[color] = v
                        print(f"✅ Color '{color}' saved for Note {note} at Velocity {v}")

                    # Save map to file
                    with open('velocity_map.json', 'w') as f:
                        json.dump(velocity_map, f, indent=2)
                    print("Velocity map saved to velocity_map.json")
                    break  # Exit after one button mapping

    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        midi_in.close_port()
        midi_out.close_port()

if __name__ == "__main__":
    main()
