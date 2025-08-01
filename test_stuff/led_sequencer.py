import rtmidi
import time
import threading

# MIDI note layout: Notes 53-57 on Channels 0-7
# This creates a grid of (x=note_offset, y=channel)

GRID_MAPPING = []

NOTE_START = 53
NOTE_END = 57
CHANNEL_START = 0
CHANNEL_END = 7

grid_x_size = NOTE_END - NOTE_START + 1
grid_y_size = CHANNEL_END - CHANNEL_START + 1

VELOCITY_MAP = {
    '6 color': {
        'off': 0,
        'green': 1,
        'green blink': 2,
        'red': 3,
        'red blink': 4,
        'yellow': 5,
        'yellow blink': 6,
    },
    '2 color': {
        'off': 0,
        'green': 1,
        'green blink': 2
    },
    '1 color': {
        'off': 0,
        'green': 1
    }
}

for y, channel in enumerate(range(CHANNEL_START, CHANNEL_END + 1)):
    for x, note in enumerate(range(NOTE_START, NOTE_END + 1)):
        GRID_MAPPING.append({
            "channel": channel,
            "note": note,
            "x": x,
            "y": y
        })

def open_named_port(midi, name_match, port_type):
    ports = midi.get_ports()
    for i, name in enumerate(ports):
        if name_match.lower() in name.lower():
            midi.open_port(i)
            return
    raise RuntimeError(f"❌ Could not open {port_type} port containing: '{name_match}'")

def channel_note_to_position(channel, note):
    for mapping in GRID_MAPPING:
        if mapping['channel'] == channel and mapping['note'] == note:
            return mapping['x'], mapping['y']
    return None, None

def position_to_channel_note(x, y):
    for mapping in GRID_MAPPING:
        if mapping['x'] == x and mapping['y'] == y:
            return mapping['channel'], mapping['note']
    return None, None

def set_led_by_position(midi_out, x, y, velocity):
    channel, note = position_to_channel_note(x, y)
    if channel is not None and note is not None:
        midi_out.send_message([0x90 + channel, note, velocity])
        print(f"Set LED at ({x}, {y}) to velocity {velocity}")
    else:
        print(f"Invalid position: ({x}, {y})")

def set_knob_led_type(midi_out, knob_index, value):
    if 0 <= knob_index < 8:
        controller_id = 0x18 + knob_index
        midi_out.send_message([0xB0, controller_id, value])
        print(f"Set knob {knob_index + 1} (CC {controller_id}) to value {value}")

def sweep_knob_value(midi_out, knob_index):
    if 0 <= knob_index < 8:
        controller_id = 0x18 + knob_index
        for value in range(128):
            midi_out.send_message([0xB0, controller_id, value])
            time.sleep(0.02)
        print(f"Swept values for knob {knob_index + 1}")

def color_wipe():
    for y in range(grid_y_size):
        for x in range(grid_x_size):
            set_led_by_position(midi_out, x, y, VELOCITY_MAP['6 color']['green'])
            time.sleep(0.05)
            set_led_by_position(midi_out, x, y, VELOCITY_MAP['6 color']['off'])

def draw_square_effect():
    min_x, min_y = 0, 0
    max_x, max_y = grid_x_size - 1, grid_y_size - 1

    while min_x <= max_x and min_y <= max_y:
        for x in range(min_x, max_x + 1):
            set_led_by_position(midi_out, x, min_y, VELOCITY_MAP['6 color']['green'])
        for y in range(min_y + 1, max_y + 1):
            set_led_by_position(midi_out, max_x, y, VELOCITY_MAP['6 color']['green'])
        for x in range(max_x - 1, min_x - 1, -1):
            set_led_by_position(midi_out, x, max_y, VELOCITY_MAP['6 color']['green'])
        for y in range(max_y - 1, min_y, -1):
            set_led_by_position(midi_out, min_x, y, VELOCITY_MAP['6 color']['green'])

        time.sleep(0.1)
        min_x += 1
        min_y += 1
        max_x -= 1
        max_y -= 1

def run_effect(effect_func):
    thread = threading.Thread(target=effect_func)
    thread.start()
    return thread

midi_out = rtmidi.MidiOut()
midi_in = rtmidi.MidiIn()
open_named_port(midi_in, "APC", "input")
open_named_port(midi_out, "APC", "output")

# Launch effects
# run_effect(color_wipe)
# run_effect(draw_square_effect)

# Set knob LED rings to Volume Style (value 2)
for i in range(8):
    set_knob_led_type(midi_out, i, 2)

# Sweep DEVICE Knob 1 values
run_effect(lambda: sweep_knob_value(midi_out, 0))
