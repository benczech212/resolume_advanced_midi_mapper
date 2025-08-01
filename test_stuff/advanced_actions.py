import rtmidi
import time

# === Constants ===
TARGET_CHANNEL = 7   # Controller 9 = Channel 10 (0-based)
TRIGGER_ON_NOTE = 51
TRIGGER_OFF_NOTE = 52
TARGET_NOTES = range(53, 58)  # Notes 53 to 57 inclusive

def open_named_port(midi, name_match, port_type="input"):
    ports = midi.get_ports()
    for i, port in enumerate(ports):
        if name_match.lower() in port.lower():
            midi.open_port(i)
            print(f"✅ Opened {port_type} port: {port}")
            return
    raise RuntimeError(f"❌ {port_type.capitalize()} port containing '{name_match}' not found.")

def send_note_on(midi_out, note, velocity, channel):
    status = 0x90 | channel  # Note On message on target channel
    midi_out.send_message([status, note, velocity])

def main():
    midi_in = rtmidi.MidiIn()
    midi_out = rtmidi.MidiOut()

    open_named_port(midi_in, "APC", "input")   # Change to "Virtual" if using loopMIDI
    open_named_port(midi_out, "APC", "output")

    print(f"\n🎛️ Listening for MIDI... Press Note {TRIGGER_ON_NOTE} to light up 53–57, Note {TRIGGER_OFF_NOTE} to turn off.")

    try:
        while True:
            msg = midi_in.get_message()
            if msg:
                message, delta = msg
                status, data1, data2 = message
                msg_type = status & 0xF0
                channel = status & 0x0F

                # Debug: print all messages
                if msg_type == 0x90:
                    print(f"🎹 NOTE ON: Note {data1} | Velocity {data2} | Channel {channel + 1}")
                elif msg_type == 0x80:
                    print(f"🔈 NOTE OFF: Note {data1} | Channel {channel + 1}")
                elif msg_type == 0xB0:
                    print(f"🎛 CONTROL CHANGE: CC {data1} | Value {data2} | Channel {channel + 1}")
                else:
                    print(f"🔍 MIDI Message: {message}")

                # Now check for your triggers
                if msg_type == 0x90 and data2 > 0 and channel == TARGET_CHANNEL:
                    if data1 == TRIGGER_ON_NOTE:
                        print(f"🎬 Trigger ON – Lighting notes {list(TARGET_NOTES)} on channel {TARGET_CHANNEL + 1}")
                        for n in TARGET_NOTES:
                            send_note_on(midi_out, n, 127, TARGET_CHANNEL)

                    elif data1 == TRIGGER_OFF_NOTE:
                        print(f"🎬 Trigger OFF – Turning off notes {list(TARGET_NOTES)} on channel {TARGET_CHANNEL + 1}")
                        for n in TARGET_NOTES:
                            send_note_on(midi_out, n, 0, TARGET_CHANNEL)

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("🛑 Exiting.")
    finally:
        midi_in.close_port()
        midi_out.close_port()
        print("✅ Ports closed.")

if __name__ == "__main__":
    main()
