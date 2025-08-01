# Launchpad
from czech_mapper import *
from pythonosc import udp_client
import logging
import time
import os
import rtmidi

controller_name = "Launchpad Mini"

open_named_port(controller_name)
midi_in = rtmidi.MidiIn()
midi_out = rtmidi.MidiOut()

while True:
    # listen for button presses
    message = midi_in.get_message()
    if message:
        handle_midi_message(message, midi_out)