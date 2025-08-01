import rtmidi
import time

# === Known APC40 Classic Grid Start Notes ===
GRID_START_NOTES = [53, 69, 85, 101, 117]



def open_named_port(midi, name_match, port_type="input"):
    ports = midi.get_ports()
    for i, port in enumerate(ports):
        if name_match.lower() in port.lower():
            midi.open_port(i)
            print(f"✅ Opened {port_type} port: {port}")
            return
    raise RuntimeError(f"❌ {port_type.capitalize()} port containing '{name_match}' not found.")

def main():
    midi_in = rtmidi.MidiIn()
    open_named_port(midi_in, "APC", "input")

    print("🎛️ Press buttons/knobs/faders on your APC40 to inspect their messages...")
    print("🔁 Press buttons in order to help with mapping. Ctrl+C to stop.\n")

    seen_notes = set()
    seen_cc = set()

    try:
        while True:
            msg = midi_in.get_message()
            if msg:
                message, delta = msg
                status, data1, data2 = message
                channel = status & 0x0F
                msg_type = status & 0xF0

                if msg_type == 0x90:  # Note On
                    note = data1
                    velocity = data2

                    if (note, velocity) not in seen_notes:
                        seen_notes.add((note, velocity))
                        print(f"🎹 NOTE ON: Note {note} | Velocity {velocity} | Channel {channel+1}")
                    

                elif msg_type == 0x80:  # Note Off
                    pass
                    # print(f"🎹 NOTE OFF: Note {data1} | Channel {channel+1}")

                elif msg_type == 0xB0:  # Control Change
                    cc_num = data1
                    cc_val = data2

                    if (cc_num, cc_val) not in seen_cc:
                        seen_cc.add((cc_num, cc_val))
                        print(f"🎛 CC: Controller {cc_num} | Value {cc_val} | Channel {channel+1}")

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n🛑 Exiting mapping debugger.")
        midi_in.close_port()

if __name__ == "__main__":
    main()
