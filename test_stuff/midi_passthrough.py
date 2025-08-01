import rtmidi
import time

# Change these to match the names you used in loopMIDI
INPUT_PORT_NAME = "Virtual MIDI Out"   # Resolume ➝ script
OUTPUT_PORT_NAME = "Virtual MIDI In"   # script ➝ Resolume

def open_named_port(midi, name, port_type="input"):
    ports = midi.get_ports()
    for i, port in enumerate(ports):
        if name.lower() in port.lower():
            midi.open_port(i)
            print(f"✅ Opened {port_type} port: {port}")
            return
    raise RuntimeError(f"❌ {port_type.capitalize()} port '{name}' not found.")

def main():
    midi_in = rtmidi.MidiIn()
    midi_out = rtmidi.MidiOut()

    open_named_port(midi_in, INPUT_PORT_NAME, "input")
    open_named_port(midi_out, OUTPUT_PORT_NAME, "output")

    print("🎛️ Virtual MIDI passthrough running...")

    try:
        while True:
            msg = midi_in.get_message()
            if msg:
                message, delta = msg
                print(f"🎹 IN: {message}")
                # You can modify the message here if needed
                midi_out.send_message(message)
                print(f"➡️  OUT: {message}")
            time.sleep(0.001)

    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        midi_in.close_port()
        midi_out.close_port()

if __name__ == "__main__":
    main()
