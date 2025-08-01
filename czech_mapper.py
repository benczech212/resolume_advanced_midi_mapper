import time
import threading
import logging
import os
import math
from resolume_http_api import *

last_press_times = {}  # (channel, note) -> last_time
press_start_times = {}  # (channel, note) -> time when press started
hold_threads = {}  # (channel, note) -> Thread
HOLD_THRESHOLD = 0.75  # seconds
DEBOUNCE_INTERVAL = 0.2  # seconds

class MidiMapping:
    def __init__(self, name, type="note", channel=None, note=None, controller=None, toggle=False, callback=None, easing=None, hold_callback=None, hold_repeat_interval=None):
        self.name = name
        self.type = type  # note or cc
        self.channel = channel
        self.note = note
        self.controller = controller
        self.toggle = toggle
        self.callback = callback
        self.easing = easing
        self.state = False
        self.hold_callback = hold_callback
        self.hold_repeat_interval = hold_repeat_interval
        self.hold_triggered = False

    def matches(self, message):
        status, data1, _ = message
        msg_type = status & 0xF0
        msg_channel = status & 0x0F
        if msg_channel != self.channel:
            return False
        if self.type == 'note' and msg_type in (0x90, 0x80):
            return self.note == data1
        elif self.type == 'cc' and msg_type == 0xB0:
            return self.controller == data1
        return False

    def _start_hold_thread(self, key, midi_out):
        def hold_loop():
            time.sleep(HOLD_THRESHOLD)
            if key not in press_start_times:
                return
            self.hold_triggered = True
            if self.hold_callback:
                self.hold_callback(True, midi_out, self.channel)
            if self.hold_repeat_interval:
                while key in press_start_times:
                    time.sleep(self.hold_repeat_interval)
                    self.hold_callback(True, midi_out, self.channel)
        thread = threading.Thread(target=hold_loop, daemon=True)
        hold_threads[key] = thread
        thread.start()

    def handle(self, message, midi_out):
        status, data1, value = message
        msg_type = status & 0xF0
        key = (self.channel, self.note)

        if self.type == 'note':
            if msg_type == 0x90 and value > 0:  # Note ON
                now = time.time()
                last_time = last_press_times.get(key, 0)
                if now - last_time < DEBOUNCE_INTERVAL:
                    return
                last_press_times[key] = now
                press_start_times[key] = now
                self.hold_triggered = False
                self._start_hold_thread(key, midi_out)

            elif msg_type == 0x80 or (msg_type == 0x90 and value == 0):  # Note OFF
                start_time = press_start_times.pop(key, None)
                if key in hold_threads:
                    hold_threads.pop(key, None)
                if start_time:
                    held_duration = time.time() - start_time
                    if self.hold_triggered:
                        return  # Already handled by hold logic
                    if self.toggle:
                        self.state = not self.state
                        if self.callback:
                            self.callback(self.state, midi_out, self.channel)
                    elif self.callback:
                        self.callback(False, midi_out, self.channel)

        elif self.type == 'cc' and msg_type == 0xB0:
            if self.callback:
                self.callback(value, midi_out, self.channel, self.easing)


# === Logging ===
def setup_logging(log_level, resolume_host, resolume_osc_port, resolume_http_port):
    log_dir = "log"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    logging.basicConfig(level=log_level, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    log_file_name = os.path.join(log_dir, f"midi_log_{time.strftime('%Y%m%d_%H%M%S')}.log")
    file_handler = logging.FileHandler(log_file_name, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    logger.info("🚀 Starting MIDI Mapper")
    logger.info(f"Resolume Host: {resolume_host}, OSC Port: {resolume_osc_port}, HTTP Port: {resolume_http_port}")


# === Resolume Info ===
def get_channel_group_mapping(resolume_host, resolume_http_port,name_to_channel):
    channel_group_mapping = {}
    group_list = {}
    layer_list = process_composition(resolume_host, resolume_http_port)

    for layer in layer_list:
        group_name = layer["group"]
        group_index = layer["group_index"]
        channel = name_to_channel.get(group_name)

        if channel is not None:
            channel_group_mapping[channel] = {
                "group_name": group_name,
                "group_index": group_index
            }

        if group_name not in group_list:
            group_list[group_name] = []
        group_list[group_name].append(layer)

    return channel_group_mapping, layer_list, group_list




# === MIDI Setup ===
def open_named_port(midi, name_match, port_type):
    ports = midi.get_ports()
    for i, name in enumerate(ports):
        if name_match.lower() in name.lower():
            midi.open_port(i)
            logging.info(f"✅ Opened {port_type} port: {name}")
            return
    raise RuntimeError(f"❌ Could not open {port_type} port containing: '{name_match}'")

# === LED Control ===
def set_leds(midi_out, targets):
    for target in targets:
        channel = target["channel"]
        note = target["note"]
        value = target.get("value", 127)
        midi_out.send_message([0x90 + channel, note, value])





# === Controller State ===
class ControllerState:
    def __init__(self, channel,channel_group_mapping, layer_list, midi_out):
        self.midi_out = midi_out
        self.channel_group_mapping = channel_group_mapping
        self.layer_list = layer_list
        self.channel = channel
        self.group_name = channel_group_mapping.get(channel, {}).get("group_name", "Unknown")
        self.group_index = channel_group_mapping.get(channel, {}).get("group_index", 0)
        self.state = {
            "playing": False,
            "color": False,
            "effect": False,
            "transform": False,
            "fill": 0.0,
        }
        self.all_fill_layers = [layer for layer in layer_list if layer["group_index"] == self.group_index and layer["layer_type"] == "Fill Layer"]
        self.total_fill_layers = len(self.all_fill_layers)

    def update(self, key, value):
        if key in self.state:
            logging.debug(f"Updating state for channel {self.channel}, key {key} to {value}")
            self.state[key] = value
        else:
            logging.warning(f"Unknown channel {self.channel} in state update")

    def get(self):
        return {
            "channel": self.channel,
            "group_name": self.group_name,
            "group_index": self.group_index,
            "state": self.state
        }

    def update_loop(self):
        logging.debug(f"Updating LEDs for channel {self.channel} ({self.group_name})")
        if self.state["playing"]: 
            set_leds(self.midi_out, [{"channel": self.channel, "note": 60, "value": 127}])   # Set activator LED to Green
            set_leds(self.midi_out, [{"channel": self.channel, "note": 52, "value": 2}])     # Set stop clip LED to Blinking Green
        else:
            set_leds(self.midi_out, [{"channel": self.channel, "note": 60, "value": 0}])     # set activator LED to Off
            set_leds(self.midi_out, [{"channel": self.channel, "note": 52, "value": 0}])     # set stop clip LED to Off  

        if self.state["color"]: set_leds(self.midi_out, [{"channel": self.channel, "note": 61, "value": 127}])
        else: set_leds(self.midi_out, [{"channel": self.channel, "note": 61, "value": 0}])

        if self.state["effect"]: set_leds(self.midi_out, [{"channel": self.channel, "note": 62, "value": 127}])
        else: set_leds(self.midi_out, [{"channel": self.channel, "note": 62, "value": 0}])

        transform_color = 5  if self.state["transform"]      else  1
        fill_layer_int = int(self.state["fill"] * self.total_fill_layers)
        for i in range(fill_layer_int):
            if self.state["playing"]:
                set_leds(self.midi_out, [{"channel": self.channel, "note": 57 - i, "value": transform_color}])
            else:
                set_leds(self.midi_out, [{"channel": self.channel, "note": 57 - i, "value": 0}])
        for j in range(5- fill_layer_int):
            set_leds(self.midi_out, [{"channel": self.channel, "note": 57 - fill_layer_int - j, "value": 0}])

    def pick_fill_layers(self):
        fill_layers_int = math.ceil(self.state["fill"] * self.total_fill_layers)

        fill_layer_ids = [ layer["layer_index"] for layer in layer_list if layer["group_index"] == self.group_index and layer["layer_type"] == "Fill Layer"]
        if fill_layers_int == 0:
            fill_layers = []
            logging.info(f"Channel {self.channel} ({self.group_name}) - No fill layers selected")
        elif fill_layers_int >= len(fill_layer_ids):
            fill_layers = fill_layer_ids
            logging.info(f"Channel {self.channel} ({self.group_name}) - All fill layers selected")
        else:
            fill_layers = fill_layer_ids[:fill_layers_int]
            logging.info(f"Channel {self.channel} ({self.group_name}) - Selected {fill_layers_int} fill layers: {fill_layers}") 

        
        return fill_layers
