import rtmidi
import time
import threading
import random
from pythonosc import udp_client
import math
from resolume_info_fetch import *
import logging
import os





RESOLUME_HOST = '192.168.4.71'
RESOLUME_OSC_PORT = 7000
RESOLUME_HTTP_PORT = 8080

# DEBUG = True  # Show raw MIDI activity
LAYER_COUNT = 34


# === Map hardcoded names to fetched group info ===
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
LOG_LEVEL = logging.INFO

OSC_CLIENT = udp_client.SimpleUDPClient(RESOLUME_HOST, RESOLUME_OSC_PORT)

# === Debounce State ===
last_press_times = {}  # (channel, note) -> last_time
DEBOUNCE_INTERVAL = 0.2  # seconds

# === Hold Button State ===
hold_threads = {}  # (channel, note) -> thread
hold_flags = {}  # (channel, note) -> Event
HOLD_INTERVAL = 0.15  # seconds between repeated callbacks



def setup_logging():
    # make a unique log file for each run

    logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(levelname)s - %(message)s')
    logger = logging.getLogger(__name__)
    log_file_name = f"midi_log_{time.strftime('%Y%m%d_%H%M%S')}.log"
    log_file_path = os.path.join(os.getcwd(), log_file_name)
    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    logger.info("Starting up MIDI Mapper")
    logger.info(f"Resolume Host: {RESOLUME_HOST}, OSC Port: {RESOLUME_OSC_PORT}, HTTP Port: {RESOLUME_HTTP_PORT}")
    

    return logger

def start_hold_thread(mapping, midi_out):
    key = (mapping.channel, mapping.note)
    stop_event = threading.Event()
    hold_flags[key] = stop_event

    def repeat_callback():
        while not stop_event.wait(HOLD_INTERVAL):
            mapping.callback(True, midi_out, mapping.channel)

    t = threading.Thread(target=repeat_callback)
    t.daemon = True
    hold_threads[key] = t
    t.start()

def stop_hold_thread(mapping):
    key = (mapping.channel, mapping.note)
    if key in hold_flags:
        hold_flags[key].set()
        del hold_flags[key]
        del hold_threads[key]

def get_group_name(channel):
    return CHANNEL_GROUP_MAPPING.get(channel, {}).get("name", f"Channel {channel}")

def get_group_id(channel):
    return CHANNEL_GROUP_MAPPING.get(channel, {}).get("group_id", channel)

# === Easing Functions ===
def apply_easing(value, easing="linear"):
    x = value / 127.0
    if easing == "linear":
        return x
    elif easing == "ease_in_sine":
        return 1 - math.cos((x * math.pi) / 2)
    elif easing == "ease_out_sine":
        return math.sin((x * math.pi) / 2)
    elif easing == "ease_in_out_sine":
        return -(math.cos(math.pi * x) - 1) / 2
    else:
        return x

# === State Tracking ===
class ChannelState:
    def __init__(self):
        self.blind = False
        self.solo = False
        self.colors = False
        self.effects = False
        self.fills = False
        self.transforms = False
        self.playing = False

channel_states = {ch: ChannelState() for ch in range(16)}

# === Utilities ===
def set_led(midi_out, channel, note, state, velocity_on=3):
    velocity = velocity_on if state else 0
    status = 0x90 | channel
    midi_out.send_message([status, note, velocity])

def blink_led(midi_out, channel, note, times=3, interval=0.3, velocity=3):
    for _ in range(times):
        set_led(midi_out, channel, note, True, velocity)
        time.sleep(interval)
        set_led(midi_out, channel, note, False)
        time.sleep(interval)

# === Action Callbacks ===
def blind(state, midi_out, channel, target_notes=None):
    group_id = get_group_id(channel)
    channel_states[channel].blind = state
    if target_notes:
        for (target_channel, target_note, velocity) in target_notes:
            midi_out.send_message([0x90 | target_channel, target_note, velocity])
    # set_led(midi_out, channel, 48, state)
    logger.info(f"{'🔴 BLIND ON' if state else '🔴 BLIND OFF'} – Layer {get_group_name(channel)}")
    OSC_CLIENT.send_message(f"/composition/groups/{group_id}/bypassed", int(state))

def solo(state, midi_out, channel, target_notes=None):
    group_id = get_group_id(channel)
    channel_states[channel].solo = state
    if target_notes:
        for (target_channel, target_note, velocity) in target_notes:
            midi_out.send_message([0x90 | target_channel, target_note, velocity])
    # set_led(midi_out, channel, 49, state)
    logger.info(f"{'🔵 SOLO ON' if state else '🔵 SOLO OFF'} – Layer {get_group_name(channel)}")
    OSC_CLIENT.send_message(f"/composition/groups/{group_id}/solo", int(state))

def next_clip(state, midi_out, channel, target_notes=None):
    group_id = get_group_id(channel)
    channel_states[channel].playing = state
    channel_states[channel].fills = state
    channel_states[channel].effects = state
    channel_states[channel].colors = state
    channel_states[channel].transforms = state
    # set_led(midi_out, channel, 50, state)
    logger.info(f"🟢 NEXT CLIP – Layer {get_group_name(channel)}")
    if not state:
        OSC_CLIENT.send_message(f"/composition/groups/{group_id}/connectnextcolumn", 1)
    else:
        OSC_CLIENT.send_message(f"/composition/groups/{group_id}/connectnextcolumn", 0)
    if target_notes:
        for (target_channel, target_note, velocity) in target_notes:
            midi_out.send_message([0x90 | target_channel, target_note, velocity])

def stop_clips(state, midi_out, channel, target_notes=None):
    group_id = get_group_id(channel)
    channel_states[channel].playing = False
    channel_states[channel].fills = False
    channel_states[channel].effects = False
    channel_states[channel].colors = False
    channel_states[channel].transforms = False
    # set_led(midi_out, channel, 52, state)
    if not state:
        if target_notes:
            for (target_channel, target_note, velocity) in target_notes:
                midi_out.send_message([0x90 | target_channel, target_note, velocity])
        OSC_CLIENT.send_message(f"/composition/groups/{group_id}/columns/1/connect", 1)
        logger.info(f"🛑 STOP CLIPS – Layer {get_group_name(channel)}")

def stop_all_clips(state, midi_out, channel, target_notes=None):
    for ch in range(8):
        group_id = get_group_id(ch)
        channel_states[ch].playing = False
        channel_states[ch].fills = False
        channel_states[ch].effects = False
        channel_states[ch].colors = False
        channel_states[ch].transforms = False
        # set_led(midi_out, ch, 52, state)
    logger.info(f"🛑🛑 STOP ALL CLIPS – Triggered on {get_group_name(channel)}")
    if target_notes:
        for (target_channel, target_note, _) in target_notes:
            midi_out.send_message([0x90 | target_channel, target_note, 0])
    OSC_CLIENT.send_message(f"/composition/columns/1/connect", 1)

def set_master_level(value, midi_out, channel, easing="linear"):
    group_id = get_group_id(channel)
    scaled = apply_easing(value, easing)
    logger.info(f"🎚️ MASTER LEVEL – Layer {get_group_name(channel)} = {scaled:.2f}")
    OSC_CLIENT.send_message(f"/composition/groups/{group_id}/master", scaled)

def set_composition_master(value, midi_out, channel, easing="linear"):
    scaled = apply_easing(value, easing)
    logger.info(f" COMPOSITION MASTER = {scaled:.2f}")
    OSC_CLIENT.send_message(f"/composition/master", scaled)

def set_autopilot_all(value, midi_out, channel):
    logger.info(f"🚦 AUTOPILOT {'ON' if value == 3 else 'OFF'}")
    for layer_id in range(1, LAYER_COUNT + 1):
        OSC_CLIENT.send_message(f"/composition/layers/{layer_id}/autopilot/target", value)

def send_osc_pulse(path, value=1,duration=0.1):
    logger.info(f"📡 OSC SEND: {path}")
    OSC_CLIENT.send_message(path, value)
    time.sleep(duration)  # Small delay to ensure message is sent
    OSC_CLIENT.send_message(path, 0)

def send_osc_command(path,value=1):
    logger.info(f"📡 OSC SEND: {path}")
    OSC_CLIENT.send_message(path, value)


def set_fill_layers_for_group_from_channel_id(channel_id, amount=0.2, target_notes=None):
    if amount <= 0:
        logger.warning("❌ Amount must be greater than 0.")
        return []
    channel_states[channel_id].fills = True
    group_name = get_group_name(channel_id)
    group_id = get_group_id(channel_id)
    for group in CHANNEL_GROUP_MAPPING.values():
        if group["group_id"] == group_id:
            group_name = group["name"]
            break
    else:
        logger.warning(f"❌ No group found for channel {channel_id}.")
        return []
    all_fill_layers = [layer for layer in layer_list if layer["group_index"] == group_id and "Fill Layer" in layer["type"]]
    fill_layer_count = len(all_fill_layers)
    if not all_fill_layers:
        logger.warning(f"❌ No fill layers found for group {group_name}.")
        return []
    amount = math.ceil(fill_layer_count * amount)

    logger.info(f"Picking {amount} fill layers for group {group_name} (ID: {group_id})")

    # Select all available fill layers from the group
    selected_fill_layers = random.sample(all_fill_layers, amount)
    logger.info(f"Selected {len(selected_fill_layers)} fill layers: {[layer['layer_name'] for layer in selected_fill_layers]}")
    for layer in all_fill_layers:
        if layer not in selected_fill_layers:
            layer_index = layer["layer_index"]
            OSC_CLIENT.send_message(f"/composition/layers/{layer_index}/clips/1/connect", 1)
        else:
            layer_index = layer["layer_index"]
            OSC_CLIENT.send_message(f"/composition/layers/{layer_index}/clips/2/connect", 1)
    if target_notes:
        for (target_channel, target_note, velocity) in target_notes:
            midi_out.send_message([0x90 | target_channel, target_note, velocity])

def set_layer_type_for_group_from_channel_id(channel_id, layer_type, state=True, target_notes=None):
    group_name = get_group_name(channel_id)
    group_id = get_group_id(channel_id)
    if group_id not in CHANNEL_GROUP_MAPPING:
        logger.warning(f"❌ No group found for channel {channel_id}.")
        return []
    
    all_layers = [layer for layer in layer_list if layer["group_index"] == group_id and layer_type in layer["type"]]
    if not all_layers:
        logger.warning(f"❌ No {layer_type} layers found for group {group_name}.")
        return []
    if layer_type == "Fill Layer": channel_states[channel_id].fills = state
    elif layer_type == "Effects Layer":  channel_states[channel_id].effects = state
    elif layer_type == "Color Layer": channel_states[channel_id].colors = state
    elif layer_type == "Transform Layer": channel_states[channel_id].transforms = state

    
    for layer in all_layers:
        layer_index = layer["layer_index"]
        column_index = random.randrange(2, 10)
        logger.info(f"{'Activating' if state else 'Deactivating'} {layer_type} layer (Layer ID: {layer_index}) for group {group_name} (Group ID: {group_id})")
        if state:
            OSC_CLIENT.send_message(f"/composition/layers/{layer_index}/clips/{column_index}/connect", 1)
        else:
            OSC_CLIENT.send_message(f"/composition/layers/{layer_index}/clips/1/connect", 1)
    for (target_channel, target_note, velocity) in target_notes or []:
        
        midi_out.send_message([0x90 | target_channel, target_note, 0 if not state else velocity])        
    


# === Mapping Class ===
class Mapping:
    def __init__(self, name, type, channel, note=None, controller=None, toggle=False, callback=None, trigger_on='press', target_notes=None, easing=None):
        self.name = name
        self.type = type  # 'note' or 'cc'
        self.channel = channel
        self.note = note
        self.controller = controller
        self.toggle = toggle
        self.callback = callback
        self.trigger_on = trigger_on  # 'press', 'release', or 'hold'
        self.state = False
        self.target_notes = target_notes or []
        self.easing = easing

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

    def handle(self, message, midi_out):
        status, data1, value = message
        msg_type = status & 0xF0
        key = (self.channel, self.note)

        if self.type == 'note':
            if msg_type == 0x90 and value > 0:
                now = time.time()
                last_time = last_press_times.get(key, 0)
                if now - last_time < DEBOUNCE_INTERVAL:
                    return
                last_press_times[key] = now

                if self.trigger_on == 'hold':
                    start_hold_thread(self, midi_out)
                elif self.toggle:
                    self.state = not self.state
                    if self.callback and self.trigger_on == 'press':
                        self.callback(self.state, midi_out, self.channel)
                elif self.callback and self.trigger_on == 'press':
                    self.callback(True, midi_out, self.channel)

            elif msg_type == 0x80 or (msg_type == 0x90 and value == 0):
                if self.trigger_on == 'hold':
                    stop_hold_thread(self)
                elif not self.toggle and self.callback and self.trigger_on == 'release':
                    self.callback(False, midi_out, self.channel, self.target_notes)

        elif self.type == 'cc' and msg_type == 0xB0:
            if self.callback:
                self.callback(value, midi_out, self.channel, self.easing)

logger = setup_logging()



logger.info("Getting composition info...")
CHANNEL_GROUP_MAPPING = {}
# Load composition info
composition_info = get_composition_info(RESOLUME_HOST, RESOLUME_HTTP_PORT)
# Get all unique groups from the "Group" column and their group id
group_list = composition_info.drop_duplicates(subset=["group"])[["group", "group_index"]].to_dict(orient="records")
layer_list = composition_info.to_dict(orient="records")

for group in group_list:
    group_name = group["group"]
    group_index = group["group_index"]
    channel = NAME_TO_CHANNEL.get(group_name, group_index)
    CHANNEL_GROUP_MAPPING[channel] = {
        "name": group_name,
        "group_id": group_index
    }   



logger.debug("Channel Group Mapping: %s", CHANNEL_GROUP_MAPPING)

# === Setup MIDI ===
midi_in = rtmidi.MidiIn()
midi_out = rtmidi.MidiOut()

def open_named_port(midi, name_match, port_type):
    ports = midi.get_ports()
    for i, name in enumerate(ports):
        if name_match.lower() in name.lower():
            midi.open_port(i)
            logging.info(f"✅ Opened {port_type} port: {name}")
            return
    raise RuntimeError(f"❌ Could not open {port_type} port containing: '{name_match}'")

open_named_port(midi_in, "APC", "input")
open_named_port(midi_out, "APC", "output")

# Clear all lights
for ch in range(16):
    for note in range(128):
        midi_out.send_message([0x90 | ch, note, 0])
logger.info("🧹 Cleared all notes on startup.")

# === Define Mappings ===
mappings = []
VELOCITY_COLORS = {
    'blinking yellow' : 6,
    'yellow': 5,
    'blinking red': 4,
    'red': 3,
    'blinking green': 2,
    'green': 1

}
for ch in range(8):
    mappings.append(Mapping("Color Layer Toggle", "note", ch, note=49, toggle=True, trigger_on="press", callback=lambda state, midi_out, channel: set_layer_type_for_group_from_channel_id(channel, "Color Layer", state, target_notes=[(channel, 49, 3)])))
    mappings.append(Mapping("Effect Layer Toggle", "note", ch, note=48, toggle=True, trigger_on="press", callback=lambda state, midi_out, channel: set_layer_type_for_group_from_channel_id(channel, "Effects Layer", state, target_notes=[(channel, 48, 3)])))
    mappings.append(Mapping("Transform Layer Toggle", "note", ch, note=51, toggle=True, trigger_on="press", callback=lambda state, midi_out, channel: set_layer_type_for_group_from_channel_id(channel, "Transform Layer", state, target_notes=[(channel, 51, 3)])))
    mappings.append(Mapping("Activator", "note", ch, note=50, toggle=False, trigger_on="press", callback=lambda state, midi_out, channel, *_: next_clip(state, midi_out, channel, target_notes=[(channel, 50, VELOCITY_COLORS["green"]), (channel, 48 , 1), (channel, 49, 1),(channel, 53, VELOCITY_COLORS["yellow"]), (channel, 54, VELOCITY_COLORS["green"]), (channel, 55, VELOCITY_COLORS["green"]), (channel, 56, VELOCITY_COLORS["green"]), (channel, 57, VELOCITY_COLORS["green"])])))
    # mappings.append(Mapping("Activator Release", "note", ch, note=50, toggle=False, trigger_on="release", callback= let_led()
    mappings.append(Mapping("Stop Clips", "note", ch, note=52, toggle=False, trigger_on="release", callback=stop_clips, target_notes=[(ch, 52, 0), (ch, 50, 0)]))
    mappings.append(Mapping("Set Master Level", "cc", ch, controller=7, callback=set_master_level, easing="ease_in_out_sine"))
    mappings.append(Mapping("Fill Level 20%", "note", ch, note=57, toggle=False, trigger_on="press", callback=lambda state, midi_out, channel, *_: set_fill_layers_for_group_from_channel_id(channel, amount=0.2, target_notes=[(channel, 57, VELOCITY_COLORS["yellow"]), (channel, 56, 0), (channel, 55, 0), (channel, 54, 0), (channel, 53, 0)])))
    mappings.append(Mapping("Fill Level 40%", "note", ch, note=56, toggle=False, trigger_on="press", callback=lambda state, midi_out, channel, *_: set_fill_layers_for_group_from_channel_id(channel, amount=0.4, target_notes=[(channel, 56, VELOCITY_COLORS["yellow"]), (channel, 57, VELOCITY_COLORS["green"]), (channel, 55, 0), (channel, 54, 0), (channel, 53, 0)])))
    mappings.append(Mapping("Fill Level 60%", "note", ch, note=55, toggle=False, trigger_on="press", callback=lambda state, midi_out, channel, *_: set_fill_layers_for_group_from_channel_id(channel, amount=0.6, target_notes=[(channel, 55, VELOCITY_COLORS["yellow"]), (channel, 56, VELOCITY_COLORS["green"]), (channel, 57, VELOCITY_COLORS["green"]), (channel, 54, 0), (channel, 53, 0)])))
    mappings.append(Mapping("Fill Level 80%", "note", ch, note=54, toggle=False, trigger_on="press", callback=lambda state, midi_out, channel, *_: set_fill_layers_for_group_from_channel_id(channel, amount=0.8, target_notes=[(channel, 54, VELOCITY_COLORS["yellow"]), (channel, 55, VELOCITY_COLORS["green"]), (channel, 56, VELOCITY_COLORS["green"]), (channel, 57, VELOCITY_COLORS["green"]), (channel, 53, 0)])))
    mappings.append(Mapping("Fill Level 100%", "note", ch, note=53, toggle=False, trigger_on="press", callback=lambda state, midi_out, channel, *_: set_fill_layers_for_group_from_channel_id(channel, amount=1.0, target_notes=[(channel, 53, VELOCITY_COLORS["yellow"]), (channel, 54, VELOCITY_COLORS["green"]), (channel, 55, VELOCITY_COLORS["green"]), (channel, 56, VELOCITY_COLORS["green"]), (channel, 57, VELOCITY_COLORS["green"])])))

mappings += [
    Mapping("Stop All Clips", "note", 0, note=81, trigger_on="press", callback=stop_all_clips, target_notes=[(ch, n, 0) for ch in range(8) for n in (50, 52)]),
    Mapping("Composition Master", "cc", 0, controller=14, callback=set_composition_master, easing="ease_in_out_sine"),
    Mapping("Autopilot On", "note", 0, note=91, trigger_on="press", callback=lambda *_: set_autopilot_all(3, *_[1:3])),
    Mapping("Autopilot Off", "note", 0, note=92, trigger_on="press", callback=lambda *_: set_autopilot_all(0, *_[1:3])),
    Mapping("BPM Tap", "note", 0, note=99, trigger_on="press", callback=lambda *_: send_osc_pulse("/composition/tempocontroller/tempotap")),
    Mapping("BPM Nudge - Press", "note", 0, note=101, trigger_on="press", callback=lambda *_: send_osc_command("/composition/tempocontroller/tempopull", value=1.0)),
    Mapping("BPM Nudge - Release", "note", 0, note=101, trigger_on="release", callback=lambda *_: send_osc_command("/composition/tempocontroller/tempopull", value=0.0)),
    Mapping("BPM Nudge + Press", "note", 0, note=100, trigger_on="press", callback=lambda *_: send_osc_command("/composition/tempocontroller/tempopush", value=1.0)),
    Mapping("BPM Nudge + Release", "note", 0, note=100, trigger_on="release", callback=lambda *_: send_osc_command("/composition/tempocontroller/tempopush", value=0.0)),
    Mapping("BPM Resync", "note", 0, note=98, trigger_on="press", callback=lambda *_: send_osc_pulse("/composition/tempocontroller/resync")),
    Mapping("Tempo Inc", "note", 0, note=94, trigger_on="press", callback=lambda *_: send_osc_pulse("/composition/tempocontroller/tempo/inc")),
    Mapping("Tempo Inc", "note", 0, note=94, trigger_on="hold", callback=lambda *_: send_osc_pulse("/composition/tempocontroller/tempo/inc")),
    Mapping("Tempo Dec", "note", 0, note=95, trigger_on="press", callback=lambda *_: send_osc_pulse("/composition/tempocontroller/tempo/dec")),
    Mapping("Tempo Dec", "note", 0, note=95, trigger_on="hold", callback=lambda *_: send_osc_pulse("/composition/tempocontroller/tempo/dec")),
    Mapping("Tempo Multiply", "note", 0, note=96, trigger_on="press", callback=lambda *_: send_osc_pulse("/composition/tempocontroller/tempo/multiply")),
    Mapping("Tempo Divide", "note", 0, note=97, trigger_on="press", callback=lambda *_: send_osc_pulse("/composition/tempocontroller/tempo/divide")),
]

# === Main Loop ===
logger.info("Starting MIDI event loop...")
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

            for m in mappings:
                if m.matches(message):
                    m.handle(message, midi_out)

        time.sleep(0.01)
except KeyboardInterrupt:
    logging.info("🛑 Exiting.")
finally:
    midi_in.close_port()
    midi_out.close_port()
    logging.info("✅ Ports closed.")
