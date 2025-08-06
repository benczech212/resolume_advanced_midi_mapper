
from czech_mapper import *
from pythonosc import udp_client
import logging
import time
import os
import rtmidi
import math

# === Configuration ===
LOG_LEVEL = logging.DEBUG
RESOLUME_HOST = "192.168.4.71"
RESOLUME_HTTP_PORT = 8080
RESOLUME_OSC_PORT = 7000
MIDI_CONTROLLER_NAME = "APC"

NAME_TO_CHANNEL = {
    "FFT": 0,
    "Stage Lighting": 1,
    "Stage Effects": 2,
    "Back Panel": 3,
    "Wire Trace": 4,
    "Merkaba": 5,
    "Flower": 6,
    "Top": 7
}





# === Button Callbacks ===
def effect_button_callback(state, midi_out, channel):
    channel_name = channel_group_mapping.get(channel, {}).get("group_name", "Unknown")
    logging.debug(f"Effect button {'pressed' if state else 'released'} on channel {channel_name} ID {channel}")
    current_state[channel].update("effect", state)
    

def color_button_callback(state, midi_out, channel):
    channel_name = channel_group_mapping.get(channel, {}).get("group_name", "Unknown")
    logging.debug(f"Color button {'pressed' if state else 'released'} on channel {channel_name} ID {channel}")
    current_state[channel].update("color", state)

def activator_button_callback(state, midi_out, channel):
    channel_name = channel_group_mapping.get(channel, {}).get("group_name", "Unknown")
    logging.debug(f"Activator button {'pressed' if state else 'released'} on channel {channel_name} ID {channel}")
    current_state[channel].update("playing", state)
    logging.info(f"🎬 Playing next clip on channel {channel_name} ({channel})")
    

def stop_clip_callback(state, midi_out, channel):
    channel_name = channel_group_mapping.get(channel, {}).get("group_name", "Unknown")
    logging.info(f"Stop Clip button {'pressed' if state else 'released'} on channel {channel_name} ID {channel}")
    current_state[channel].update("playing", False)
    set_leds(midi_out, [{"channel": channel, "note": 50, "value": 0}])  # Set activator LED to Off
    

def transform_button_callback(state, midi_out, channel):
    channel_name = channel_group_mapping.get(channel, {}).get("group_name", "Unknown")
    state = not current_state[channel].state["transform"]
    logging.info(f"Transform button {'pressed' if state else 'released'} on channel {channel_name} ID {channel}")
    current_state[channel].update("transform", state)

def stop_all_clips_callback(midi_out):
    logging.info("Stopping all clips")
    for channel in current_state:
        current_state[channel].update("playing", False)
        set_leds(midi_out, [{"channel": channel, "note": 50, "value": 0}])  # Set activator LED to Off

def fill_button_callback(state, midi_out, channel, fill_value):
    channel_name = channel_group_mapping.get(channel, {}).get("group_name", "Unknown")
    logging.info(f"Fill button {'pressed' if state else 'released'} on channel {channel_name} ID {channel}")
    current_state[channel].update("fill", fill_value)
    if current_state[channel].total_fill_layers > 0:
        current_state[channel].update("playing", True)
        

        


# === Main Setup ===
setup_logging(LOG_LEVEL, RESOLUME_HOST, RESOLUME_OSC_PORT, RESOLUME_HTTP_PORT)
channel_group_mapping, layer_list, group_list = get_channel_group_mapping(RESOLUME_HOST, RESOLUME_HTTP_PORT,NAME_TO_CHANNEL)

midi_in = rtmidi.MidiIn()
midi_out = rtmidi.MidiOut()

def open_named_port(midi_port, port_name, direction):
    available_ports = midi_port.get_ports()
    for i, name in enumerate(available_ports):
        if port_name in name:
            midi_port.open_port(i)
            logging.info(f"Opened {direction} port: {name}")
            return
    raise RuntimeError(f"Could not find {direction} port with name '{port_name}'")

open_named_port(midi_in, MIDI_CONTROLLER_NAME, "MIDI In")
open_named_port(midi_out, MIDI_CONTROLLER_NAME, "MIDI Out")

osc_client = udp_client.SimpleUDPClient(RESOLUME_HOST, RESOLUME_OSC_PORT)

note_mappings = []
# note_mappings = [
#     {"name": "Effect Button",       "note": 48, "callback": effect_button_callback,         "toggle": True},
#     {"name": "Color Button",        "note": 49, "callback": color_button_callback,          "toggle": True},
#     {"name": "Activator Button",    "note": 50, "callback": activator_button_callback,       "toggle": True},
#     {"name": "Fill 20% Button",   "note": 57, "callback": lambda state, midi_out, channel: fill_button_callback(state,midi_out, channel, fill_value=0.2), "toggle": True, "hold_callback": transform_button_callback, "hold_repeat_interval": None},
#     {"name": "Fill 40% Button",   "note": 56, "callback": lambda state, midi_out, channel: fill_button_callback(state,midi_out, channel, fill_value=0.4), "toggle": True, "hold_callback": transform_button_callback, "hold_repeat_interval": None},
#     {"name": "Fill 60% Button",   "note": 55, "callback": lambda state, midi_out, channel: fill_button_callback(state,midi_out, channel, fill_value=0.6), "toggle": True, "hold_callback": transform_button_callback, "hold_repeat_interval": None},
#     {"name": "Fill 80% Button",   "note": 54, "callback": lambda state, midi_out, channel: fill_button_callback(state,midi_out, channel, fill_value=0.8), "toggle": True, "hold_callback": transform_button_callback, "hold_repeat_interval": None},
#     {"name": "Fill 100% Button",   "note": 53, "callback": lambda state, midi_out, channel: fill_button_callback(state,midi_out, channel, fill_value=1.0), "toggle": True, "hold_callback": transform_button_callback, "hold_repeat_interval": None},
#     # {"name": "Activator Button",    "note": 57, "callback": activator_button_callback,       "toggle": True, "hold_callback": transform_button_callback, "hold_repeat_interval": None},
#     # {"name": "Activator Hold",    "note": 50, "callback": activator_button_callback,       "toggle": False},
#     {"name": "Stop Clip Button",    "note": 52, "callback": stop_clip_callback,              "toggle": True},
#     # {"name": "Transform Button",    "note": 57, "callback": transform_button_callback,       "toggle": True},
# ]

midi_mappings = []
# Repeated mappings
for channel, group in channel_group_mapping.items():
    group_name = group["group_name"]
    group_index = group["group_index"]
    for mapping in note_mappings:

        pass
        
        # midi_mappings.append(MidiMapping(
        #     name=f"{group_name} {mapping['name']}",
        #     type=mapping.get("type", "note"),
        #     channel=channel,
        #     note= mapping["note"],
        #     toggle=mapping.get("toggle", False),
        #     callback=mapping.get("callback", None)
        #     , easing=mapping.get("easing", None),
        #     hold_callback=mapping.get("hold_callback", None),
        #     hold_repeat_interval=mapping.get("hold_repeat_interval", None)
        # ))
        

current_state = {
    channel: ControllerState(channel, channel_group_mapping=channel_group_mapping, layer_list=layer_list, midi_out=midi_out) for channel in NAME_TO_CHANNEL.values()
}
# run update loop for each channel on startup
for channel in current_state:
    current_state[channel].update_loop()

# === Event Loop ===
logging.info("🎛️ Starting MIDI event loop")
try:
    while True:
        msg = midi_in.get_message()
        if msg:
            message, delta = msg
            status, data1, data2 = message
            msg_type = status & 0xF0
            channel = status & 0x0F

            if msg_type == 0x90:
                logging.debug(f"🎹 NOTE ON: Note {data1} | Velocity {data2} | Channel {channel}")
            elif msg_type == 0x80:
                logging.debug(f"🔈 NOTE OFF: Note {data1} | Channel {channel}")
            elif msg_type == 0xB0:
                logging.debug(f"🎛 CC: Controller {data1} | Value {data2} | Channel {channel}")
            else:
                logging.debug(f"🎲 Unknown MIDI Message: {message}")

            for m in midi_mappings:
                if m.matches(message):
                    m.handle(message, midi_out)

            if channel in current_state:
                current_state[channel].update_loop()

        time.sleep(0.01)
except KeyboardInterrupt:
    logging.info("🛑 Exiting.")
finally:
    midi_in.close_port()
    midi_out.close_port()
    logging.info("✅ Ports closed.")
