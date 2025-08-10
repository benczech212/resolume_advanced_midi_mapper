# test/midi_probe.py
import time
import mido

# Force RtMidi backend on Windows (helps avoid weird default backend issues)
try:
    mido.set_backend('mido.backends.rtmidi')
except Exception:
    pass

print("MIDI INPUT PORTS:")
inputs = mido.get_input_names()
for i, name in enumerate(inputs):
    print(f"  [{i}] {name}")

if not inputs:
    print("No MIDI input ports found. Is your device connected and driver installed?")
    raise SystemExit(1)

# Auto-pick APC40 or Launchpad if present; else pick first
preferred = None
for name in inputs:
    if "APC40" in name:
        preferred = name
        break
if not preferred:
    for name in inputs:
        if "Launchpad" in name:
            preferred = name
            break
if not preferred:
    preferred = inputs[0]

print(f"\nOpening input: {preferred}")
with mido.open_input(preferred) as inport:
    print("Listening. Press some buttons/keys. Ctrl+C to exit.")
    try:
        while True:
            for msg in inport.iter_pending():
                print("MIDI:", msg)
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nExiting.")
