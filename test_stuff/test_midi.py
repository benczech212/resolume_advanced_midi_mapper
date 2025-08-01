import rtmidi

midi_in = rtmidi.MidiIn()
midi_out = rtmidi.MidiOut()

print("Available MIDI Inputs:")
for i, name in enumerate(midi_in.get_ports()):
    print(f"{i}: {name}")

print("\nAvailable MIDI Outputs:")
for i, name in enumerate(midi_out.get_ports()):
    print(f"{i}: {name}")
