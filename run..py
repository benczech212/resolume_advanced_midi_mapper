"""Entry point for the advanced MIDI mapper.

This script demonstrates how to configure multiple controllers (e.g. APC
and Launchpad) using controller configurations that separate action
mappings from physical location mappings.  Each controller spawns its own
input loop and, for devices like the Launchpad, auxiliary threads can
update LEDs to display tempo or other state.
"""

from __future__ import annotations

import logging
import math
import threading
import time
import random
from typing import Dict, List

import rtmidi
from pythonosc import udp_client

from czech_mapper import (
    MidiMapping,
    setup_logging,
    get_channel_group_mapping,
    open_named_port,
    ControllerState,
)
from controller_config import ControllerConfig, ActionMapping


# === Global Configuration ===
LOG_LEVEL = logging.DEBUG
RESOLUME_HOST = "192.168.4.71"
RESOLUME_HTTP_PORT = 8080
RESOLUME_OSC_PORT = 7000

NAME_TO_CHANNEL = {
    "FFT": 0,
    "Stage Lighting": 1,
    "Stage Effects": 2,
    "Back Panel": 3,
    "Wire Trace": 4,
    "Merkaba": 5,
    "Flower": 6,
    "Top": 7,
}


# === Callback Definitions ===
def effect_button_callback(state: bool, midi_out: rtmidi.MidiOut, channel: int) -> None:
    max_column = 8  # Assuming 4 columns for effects
    """Toggle effect layer state on the given channel."""
    group_name = channel_group_mapping.get(channel, {}).get("group_name", "Unknown")
    logging.debug(
        f"Effect button {'pressed' if state else 'released'} on channel {group_name} ID {channel}"
    )
    current_state[channel].update("effect", state)
    # Immediately update LEDs to reflect new state
    current_state[channel].update_loop()
    effect_layers = []
    for layer in layer_list:
        if layer["group_index"] == channel:
            if layer["layer_type"] == "Effect Layer":
                effect_layers.append(layer)
    
        # pick random effect layer to toggle
    if effect_layers:
        selected_layer = random.choice(effect_layers)
        selected_layer_id = selected_layer["layer_id"]
        selected_column = random.randint(1, max_column)  # Randomly select a column (1-4)
        osc_client.send_message(f"/composition/layers/{selected_layer_id}/clips/{selected_column if state else 0}/connect")
        logging.info(f"🎛️ Toggled effect layer {selected_layer['layer_name']} on channel {group_name} ({channel})")


def color_button_callback(state: bool, midi_out: rtmidi.MidiOut, channel: int) -> None:
    """Toggle color layer state on the given channel."""
    channel_name = channel_group_mapping.get(channel, {}).get("group_name", "Unknown")
    logging.debug(
        f"Color button {'pressed' if state else 'released'} on channel {channel_name} ID {channel}"
    )
    current_state[channel].update("color", state)
    current_state[channel].update_loop()


def activator_button_callback(state: bool, midi_out: rtmidi.MidiOut, channel: int) -> None:
    """Toggle clip playback on the given channel."""
    channel_name = channel_group_mapping.get(channel, {}).get("group_name", "Unknown")
    logging.debug(
        f"Activator button {'pressed' if state else 'released'} on channel {channel_name} ID {channel}"
    )
    current_state[channel].update("playing", state)
    # Turn on activator LED when playing
    current_state[channel].update_loop()
    logging.info(f"🎬 Playing next clip on channel {channel_name} ({channel})")
    # send midi message to turn on activator LED
    midi_out.send_message([0x90 + channel, 50, 127])  # Note On for activator LED


def stop_clip_callback(state: bool, midi_out: rtmidi.MidiOut, channel: int) -> None:
    """Stop clip playback on the given channel and turn off activator LED."""
    channel_name = channel_group_mapping.get(channel, {}).get("group_name", "Unknown")
    logging.info(
        f"Stop Clip button {'pressed' if state else 'released'} on channel {channel_name} ID {channel}"
    )
    current_state[channel].update("playing", False)
    # Turn off activator LED and update LEDs
    midi_out.send_message([0x90 + channel, 50, 0])
    current_state[channel].update_loop()


def transform_button_callback(state: bool, midi_out: rtmidi.MidiOut, channel: int) -> None:
    """Toggle transform state on the given channel."""
    channel_name = channel_group_mapping.get(channel, {}).get("group_name", "Unknown")
    new_state = not current_state[channel].state["transform"]
    logging.info(
        f"Transform button {'pressed' if new_state else 'released'} on channel {channel_name} ID {channel}"
    )
    current_state[channel].update("transform", new_state)
    current_state[channel].update_loop()


def fill_button_callback(state: bool, midi_out: rtmidi.MidiOut, channel: int, fill_value: float) -> None:
    """Set fill amount for the given channel and optionally toggle playback."""
    channel_name = channel_group_mapping.get(channel, {}).get("group_name", "Unknown")
    logging.info(
        f"Fill button {'pressed' if state else 'released'} on channel {channel_name} ID {channel}"
    )
    current_state[channel].update("fill", fill_value)
    if current_state[channel].total_fill_layers > 0:
        current_state[channel].update("playing", True)
    # Update LEDs after changing fill and playing state
    current_state[channel].update_loop()


# Launchpad‑specific callbacks
def bpm_tap_callback(state: bool, midi_out: rtmidi.MidiOut, channel: int) -> None:
    """Handle BPM tap on the Launchpad."""
    if state:
        logging.info(f"🕒 BPM tap detected on channel {channel} (Launchpad)")


def resync_phase_callback(state: bool, midi_out: rtmidi.MidiOut, channel: int) -> None:
    """Handle phase resync on the Launchpad."""
    if state:
        logging.info(f"🔄 Resync phase triggered on channel {channel} (Launchpad)")


# === LED Threads ===
def launchpad_bpm_led_loop(midi_out: rtmidi.MidiOut, stop_event: threading.Event) -> None:
    """Continuously flash four note positions to represent a 4/4 beat."""
    beat_notes = [51, 52, 67, 68]
    while not stop_event.is_set():
        for note in beat_notes:
            midi_out.send_message([0x90, note, 3])
            time.sleep(0.15)
            midi_out.send_message([0x90, note, 0])
            if stop_event.is_set():
                break
        time.sleep(0.2)


# === Controller Configurations ===
# === Controller Configurations ===
def build_controller_configs() -> Dict[str, ControllerConfig]:
    """Construct ControllerConfig instances for the APC and Launchpad."""
    # Base note mappings common to both controllers
    base_note_mappings: List[ActionMapping] = [
        # For APC hardware the buttons already act as toggles, so set toggle=False to avoid double toggling
        ActionMapping(name="Effect Button",    note=48, toggle=False, callback=effect_button_callback),
        ActionMapping(name="Color Button",     note=49, toggle=False, callback=color_button_callback),
        ActionMapping(name="Activator Button", note=50, toggle=False, callback=lambda s,m,ch: activator_button_callback(True, m, ch)),
        ActionMapping(name="Fill 20% Button",  note=57, toggle=True,  callback=lambda s,m,ch: fill_button_callback(s, m, ch, 0.2), hold_callback=transform_button_callback),
        ActionMapping(name="Fill 40% Button",  note=56, toggle=True,  callback=lambda s,m,ch: fill_button_callback(s, m, ch, 0.4), hold_callback=transform_button_callback),
        ActionMapping(name="Fill 60% Button",  note=55, toggle=True,  callback=lambda s,m,ch: fill_button_callback(s, m, ch, 0.6), hold_callback=transform_button_callback),
        ActionMapping(name="Fill 80% Button",  note=54, toggle=True,  callback=lambda s,m,ch: fill_button_callback(s, m, ch, 0.8), hold_callback=transform_button_callback),
        ActionMapping(name="Fill 100% Button", note=53, toggle=True,  callback=lambda s,m,ch: fill_button_callback(s, m, ch, 1.0), hold_callback=transform_button_callback),
        ActionMapping(name="Stop Clip Button", note=52, toggle=True,  callback=stop_clip_callback),
    ]

    # APC configuration – uses the base mappings only
    apc_config = ControllerConfig(
        name="APC",
        midi_name="APC",
        action_mappings=list(base_note_mappings),
    )

    # Launchpad configuration – includes base mappings and extra actions
    launchpad_config = ControllerConfig(
        name="Launchpad",
        midi_name="Launchpad",
        action_mappings=list(base_note_mappings),
    )
    # Additional Launchpad actions
    launchpad_config.add_action(ActionMapping(name="BPM Tap",    note=120, toggle=False, callback=bpm_tap_callback))
    launchpad_config.add_action(ActionMapping(name="Resync Phase", note=104, toggle=False, callback=resync_phase_callback))

    # Example location mappings for Launchpad: map channels/notes to x/y
    for ch in range(8):
        for i, note in enumerate(range(53, 58)):
            launchpad_config.set_location(ch, note, x=i, y=ch)

    return {"APC": apc_config, "Launchpad": launchpad_config}



def build_midi_mappings(config: ControllerConfig) -> List[MidiMapping]:
    """Expand a controller config into a list of MidiMapping instances for each channel.

    If no channel/group mapping has been obtained from Resolume, fall back to the
    channels defined in NAME_TO_CHANNEL, using generic group names.
    """
    mappings: List[MidiMapping] = []
    # For controllers like Launchpad that don't use channel mapping, assign all actions to channel 0
    if not config.use_channel_mapping:
        for action in config.action_mappings:
            mappings.append(
                MidiMapping(
                    name=f"{config.name} {action.name}",
                    type=action.type,
                    channel=0,
                    note=action.note,
                    controller=action.controller,
                    toggle=action.toggle,
                    callback=action.callback,
                    easing=action.easing,
                    hold_callback=action.hold_callback,
                    hold_repeat_interval=action.hold_repeat_interval,
                )
            )
        return mappings

    # If channel_group_mapping is empty, build generic channel mappings
    if not channel_group_mapping:
        default_channels = list(NAME_TO_CHANNEL.values()) or list(range(8))
        for channel in default_channels:
            group = {"group_name": f"Channel {channel}", "group_index": channel}
            for action in config.action_mappings:
                mappings.append(
                    MidiMapping(
                        name=f"{group['group_name']} {action.name}",
                        type=action.type,
                        channel=channel,
                        note=action.note,
                        controller=action.controller,
                        toggle=action.toggle,
                        callback=action.callback,
                        easing=action.easing,
                        hold_callback=action.hold_callback,
                        hold_repeat_interval=action.hold_repeat_interval,
                    )
                )
    else:
        for channel, group in channel_group_mapping.items():
            for action in config.action_mappings:
                mappings.append(
                    MidiMapping(
                        name=f"{group['group_name']} {action.name}",
                        type=action.type,
                        channel=channel,
                        note=action.note,
                        controller=action.controller,
                        toggle=action.toggle,
                        callback=action.callback,
                        easing=action.easing,
                        hold_callback=action.hold_callback,
                        hold_repeat_interval=action.hold_repeat_interval,
                    )
                )
    return mappings


def controller_event_loop(name: str, midi_in: rtmidi.MidiIn, midi_out: rtmidi.MidiOut, mappings: List[MidiMapping]) -> None:
    """Continuously dispatch MIDI messages to the appropriate mappings."""
    logging.info(f"🎛️ Starting event loop for {name}")
    try:
        while True:
            msg = midi_in.get_message()
            if msg:
                message, _delta = msg
                status, data1, value = message
                msg_type = status & 0xF0
                channel = status & 0x0F
                handled = False

                # Note-On or Control Change with value > 0 indicates a press
                if (msg_type == 0x90 and value > 0) or (msg_type == 0xB0 and value > 0):
                    msg_desc = f"🎹 {name} pressed: channel {channel}, id {data1}, value {value}"
                    print(msg_desc)
                    logging.info(msg_desc)
                    handled = True

                # Dispatch to any matching mappings
                for m in mappings:
                    if m.matches(message):
                        m.handle(message, midi_out)
                        handled = True

                # Print any other messages (note-off, value 0 messages, system messages) for debugging
                if not handled:
                    msg_hex = f"0x{status:02X}"
                    debug_msg = f"🔍 {name} other MIDI message: status {msg_hex}, data1 {data1}, value {value}, channel {channel}"
                    print(debug_msg)
                    logging.debug(debug_msg)

            time.sleep(0.01)
    except KeyboardInterrupt:
        logging.info(f"🛑 Event loop for {name} interrupted")



if __name__ == "__main__":
    # Set up logging
    logger = setup_logging(LOG_LEVEL, RESOLUME_HOST, RESOLUME_OSC_PORT, RESOLUME_HTTP_PORT)

    # Fetch Resolume composition info and build group/channel mapping
    channel_group_mapping, layer_list, group_list = get_channel_group_mapping(
        RESOLUME_HOST, RESOLUME_HTTP_PORT, NAME_TO_CHANNEL
    )

    # Build controller configs and their MIDI mappings
    controller_configs = build_controller_configs()

    # Global state for each channel (used by callbacks)
    global current_state
    current_state = {
        channel: ControllerState(
            channel,
            channel_group_mapping=channel_group_mapping,
            layer_list=layer_list,
            midi_out=None,
        )
        for channel in NAME_TO_CHANNEL.values()
    }

    # OSC client (shared)
    osc_client = udp_client.SimpleUDPClient(RESOLUME_HOST, RESOLUME_OSC_PORT)

    # Keep track of threads to stop them later if needed
    threads: List[threading.Thread] = []
    stop_events: Dict[str, threading.Event] = {}

    for name, config in controller_configs.items():
        midi_in = rtmidi.MidiIn()
        midi_out = rtmidi.MidiOut()
        try:
            open_named_port(midi_in, config.midi_name, "input")
            open_named_port(midi_out, config.midi_name, "output")
        except Exception as e:
            logging.warning(f"Skipping controller {name}: {e}")
            continue

        # Update midi_out for each channel state (so callbacks can send messages)
        for state in current_state.values():
            state.midi_out = midi_out

        midi_mappings = build_midi_mappings(config)

        # Start controller event loop in its own thread
        t = threading.Thread(
            target=controller_event_loop, args=(name, midi_in, midi_out, midi_mappings), daemon=True
        )
        t.start()
        threads.append(t)

        # Launchpad BPM LED thread
        if config.name.lower() == "launchpad":
            stop_event = threading.Event()
            stop_events[name] = stop_event
            led_thread = threading.Thread(
                target=launchpad_bpm_led_loop, args=(midi_out, stop_event), daemon=True
            )
            led_thread.start()
            threads.append(led_thread)

    # Run update loops for each channel once on startup
    for state in current_state.values():
        state.update_loop()

    # Keep main thread alive while child threads run
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("👋 Shutting down...")
        for name, event in stop_events.items():
            event.set()
