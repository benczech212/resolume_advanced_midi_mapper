
from pythonosc import udp_client
import logging
import time
import os
import rtmidi
import sys

# === Configuration ===
LOG_LEVEL = logging.DEBUG
RESOLUME_HOST = "192.168.4.71"
RESOLUME_HTTP_PORT = 8080
RESOLUME_OSC_PORT = 7000

# callbacks
def test_callback(state, midi_out, channel):
    print(f"Button {'pressed' if state else 'released'} on channel {channel}")




def toggle_activator(state, midi_out, channel):
    print(f"Toggling activator. State: {state}, Channel: {channel}")
    # Do something here with Resolume or MIDI


def test_hold_callback(state, midi_out, channel):
    print(f"Hold callback triggered. State: {state}, Channel: {channel}")
    # Do something here with Resolume or MIDI

# Automatically load all functions from this module
callback_registry = {
    name: func
    for name, func in globals().items()
    if callable(func) and not name.startswith("_")
}
from czech_mapper import *

setup_logging(LOG_LEVEL,RESOLUME_HOST,RESOLUME_OSC_PORT,RESOLUME_HTTP_PORT)

controllers = load_controllers("controller_configs/launchpad_and_apc.json")


    


while True:
    try: 
        for controller in controllers:
            # listen for midi messages
            midi_in = controller.midi_in
            midi_out = controller.midi_out
            msg = midi_in.get_message()
            if msg:
                controller.handle_midi_message(msg)
        time.sleep(0.01)  # Sleep to prevent busy-waiting
    except KeyboardInterrupt:
        print("Exiting...")
        break