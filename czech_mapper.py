import time
import threading
import logging
import os
import math
import rtmidi
from libraries.resolume_http_api import *


last_press_times = {}  # (channel, note) -> last_time
press_start_times = {}  # (channel, note) -> time when press started
hold_threads = {}  # (channel, note) -> Thread
HOLD_THRESHOLD = 0.75  # seconds
DEBOUNCE_INTERVAL = 0.2  # seconds

# An individual mapping of actions to do when a specific midi note or controller is pressed
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










# A class to manage the state of each channel
# This class will handle the MIDI state for each channel, including the group and layer information
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
    def set_leds(self, targets):
        for target in targets:
            channel = target["channel"]
            note = target["note"]
            value = target.get("value", 127)
            self.midi_out.send_message([0x90 + channel, note, value])
    def update_loop(self):
        logging.debug(f"Updating LEDs for channel {self.channel} ({self.group_name})")
        if self.state["playing"]: 
            self.set_leds([{"channel": self.channel, "note": 60, "value": 127}])   # Set activator LED to Green
            self.set_leds([{"channel": self.channel, "note": 52, "value": 2}])     # Set stop clip LED to Blinking Green
        else:
            self.set_leds([{"channel": self.channel, "note": 60, "value": 0}])     # set activator LED to Off
            self.set_leds([{"channel": self.channel, "note": 52, "value": 0}])     # set stop clip LED to Off  

        if self.state["color"]: self.set_leds([{"channel": self.channel, "note": 61, "value": 127}])
        else: self.set_leds([{"channel": self.channel, "note": 61, "value": 0}])

        if self.state["effect"]: self.set_leds([{"channel": self.channel, "note": 62, "value": 127}])
        else: self.set_leds([{"channel": self.channel, "note": 62, "value": 0}])

        transform_color = 5  if self.state["transform"]      else  1
        fill_layer_int = int(self.state["fill"] * self.total_fill_layers)
        for i in range(fill_layer_int):
            if self.state["playing"]:
                self.set_leds([{"channel": self.channel, "note": 57 - i, "value": transform_color}])
            else:
                self.set_leds([{"channel": self.channel, "note": 57 - i, "value": 0}])
        for j in range(5- fill_layer_int):
            self.set_leds([{"channel": self.channel, "note": 57 - fill_layer_int - j, "value": 0}])

    def pick_fill_layers(self):
        fill_layers_int = math.ceil(self.state["fill"] * self.total_fill_layers)

        fill_layer_ids = [ layer["layer_index"] for layer in self.layer_list if layer["group_index"] == self.group_index and layer["layer_type"] == "Fill Layer"]
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

class LayoutMap:
    def __init__(self, layout_file, rotation=0):
        self.layout_map = self.load_layout(layout_file)
        self.rotation = rotation
        if rotation not in [0, 90, 180, 270]:
            raise ValueError("Rotation must be one of: 0, 90, 180, 270 degrees")
        self.rotate_layout()
        

    def rotate_layout(self):
        if self.rotation == 90:
            self.layout_map = {(y, -x): v for (x, y), v in self.layout_map.items()}
        elif self.rotation == 180:
            self.layout_map = {(-x, -y): v for (x, y), v in self.layout_map.items()}
        elif self.rotation == 270:
            self.layout_map = {(-y, x): v for (x, y), v in self.layout_map.items()}

    def load_layout(self, layout_file):
        with open(layout_file, 'r') as f:
            return json.load(f)

    def get_entry(self, x, y):
        return self.layout_map.get((x, y))

    def get_all_entries(self):
        return self.layout_map.values()

    def get_note_channel_status_by_xy(self, x, y):
        entry = self.get_entry(x, y)
        if entry:
            return entry["note"], entry["status"]
        return None, None

    
class MidiController:
    status_map = {
        144: "Note",
        176: "CC",
    }
    def __init__(self, config, callback_registry=None):
        self.controller_name = config["name"]
        self.layout_map_file = config["layout_map"]
        self.action_map_file = config["action_map"]
        self.rotation = config.get("rotation", 0)
        self.callback_registry = callback_registry or {}

        self.layout_map = LayoutMap(self.layout_map_file, self.rotation)
        self.mappings = self.load_action_map(self.action_map_file)

        self.midi_in = rtmidi.MidiIn()
        self.midi_out = rtmidi.MidiOut()
        self.open_ports()
        self.ports = []

    def open_ports(self):
        self.open_named_port(self.midi_in, self.controller_name, "input")
        self.open_named_port(self.midi_out, self.controller_name, "output")

    def open_named_port(self, midi, keyword, port_type):
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

    def load_action_map(self, path):
        with open(path, "r") as f:
            data = json.load(f)

        note_map = {}
        cc_map = {}

        for entry in data:
            mapping = MidiMapping(
                name=entry["name"],
                type=entry.get("type", "note"),
                channel=entry.get("channel"),
                note=entry.get("note"),
                controller=entry.get("controller"),
                toggle=entry.get("toggle", False),
                callback=self.callback_registry.get(entry.get("callback")),
                easing=entry.get("easing"),
                hold_callback=self.callback_registry.get(entry.get("hold_callback")),
                hold_repeat_interval=entry.get("hold_repeat_interval")
            )

            if mapping.type == "note":
                note_map[(mapping.channel, mapping.note)] = mapping
            elif mapping.type == "cc":
                cc_map[(mapping.channel, mapping.controller)] = mapping

        self.note_map = note_map
        self.cc_map = cc_map
        return list(note_map.values()) + list(cc_map.values())  # Optional: full list if needed


    def set_leds(self, targets):
        for target in targets:
            channel = target["channel"]
            note = target["note"]
            value = target.get("value", 127)
            self.midi_out.send_message([0x90 + channel, note, value])


    def handle_midi_message(self, message):
        values, delta_time = message
        if len(values) < 3:
            logging.warning(f"Received invalid MIDI message: {values}")
            return

        status, data1, value = values
        msg_type = status & 0xF0
        channel = status & 0x0F

        mapping = None
        if msg_type in (0x90, 0x80):  # Note On/Off
            mapping = self.note_map.get((channel, data1))
        elif msg_type == 0xB0:  # Control Change
            mapping = self.cc_map.get((channel, data1))

        if mapping:
            mapping.handle((status, data1, value), self.midi_out)
        else:
            logging.debug(f"No mapping for channel {channel}, msg_type {hex(msg_type)}, data1 {data1}")

    

def load_controllers(config_file="controllers_config.json", callback_registry=None):
    with open(config_file, "r") as f:
        controller_configs = json.load(f)

    controllers = []
    for config in controller_configs:
        controller = MidiController(config, callback_registry)
        controllers.append(controller)
    return controllers
