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
                # Figure out if Note or CC
                msg_type = message[0] & 0xF0
                if msg_type in (0x80, 0x90):  # Note Off or Note On
                    state = "⚪ Released" if msg_type == 0x80 else "🟢 Pressed"
                elif msg_type in (0xB0, 0xE0):  # CC or Pitch Bend
                    state = "CC" if msg_type == 0xB0 else "Pitch Bend"
                else:
                    state = "Unknown"
                status = message[0]
                channel = (status & 0xF)
                note = message[1]
                velocity = message[2]
                message_type = status - channel
                if message_type == 128:
                    state = "⚪ Released"
                elif message_type == 144:
                    state = "🟢 Pressed"
                print(f"{str(state).ljust(12)} Channel: {str(channel).ljust(4)} Note: {str(note).ljust(4)} Status: {str(status).ljust(4)} Delta Time: {delta_time:.4f}s")


        time.sleep(0.01)
except KeyboardInterrupt:
    print("Exiting...")

midi_in.close_port()
