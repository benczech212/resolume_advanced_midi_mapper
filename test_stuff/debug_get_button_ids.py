import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from czech_mapper import *
from pythonosc import udp_client
import logging
import time
import os
import rtmidi

controller_name = "APC"
midi_in = rtmidi.MidiIn()
midi_out = rtmidi.MidiOut()

def open_named_port(midi, keyword, port_type):
    name_match = keyword.lower()
    logging.info(f"Opening {port_type} port containing: '{name_match}'")
    available_ports = midi.get_ports()
    for i, port in enumerate(available_ports):
        if name_match in port.lower():
            logging.info(f"Opening {port_type} port: {port}")
            midi.open_port(i)
            return
    logging.error(f"No matching {port_type} ports found with keyword '{name_match}'")
    raise Exception(f"No matching {port_type} ports found with keyword '{name_match}'")


# Open the first available input port
open_named_port(midi_in, controller_name, "MIDI In")
open_named_port(midi_out, controller_name, "MIDI Out")
print("Listening for button presses... (Press Ctrl+C to exit)")

try:
    while True:
        msg = midi_in.get_message()
        if msg:
            message, delta_time = msg
            if len(message) >= 3:
                status = message[0]
                channel = (status & 0xF)
                note = message[1]
                velocity = message[2]
                if velocity > 0:
                    state = "🟢 Pressed"
                else:
                    state = "⚪ Released"
                print(f"{str(state).ljust(12)} Channel: {str(channel).ljust(4)} Note: {str(note).ljust(4)} Status: {str(status).ljust(4)} Delta Time: {delta_time:.4f}s")


        time.sleep(0.01)
except KeyboardInterrupt:
    print("Exiting...")

midi_in.close_port()
