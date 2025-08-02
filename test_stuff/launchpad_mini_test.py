import sys
import os
import time
import json
import logging
import threading
import rtmidi
from collections import deque

# Config
controller_name = "Launchpad Mini"
layout_map_file = "layout_maps/launchpad_mini.json"
bpm_max_age = 8  # seconds
bpm_min_taps = 3

# Load layout map
layout_map = {}
with open(layout_map_file, 'r') as f:
    raw_map = json.load(f)
    layout_map = {
        (entry["x"], entry["y"]): {
            "note": entry["note"],
            "status": entry["status"],
            "name": entry["name"]
        }
        for entry in raw_map["layout_map"]
    }

note_to_xy = {v["note"]: k for k, v in layout_map.items() if v["status"] == 144}

def led_color(red=0, green=0, copy=True, clear=True, flash=False):
    flags = 0
    if flash:
        flags |= 8
    elif copy and clear:
        flags |= 12
    elif copy:
        flags |= 4
    elif clear:
        flags |= 8
    return (16 * green) + red + flags

def set_led(midi_out, status, note, value):
    midi_out.send_message([status, note, value])

def set_led_at_xy(midi_out, x, y, value=127):
    entry = layout_map.get((x, y))
    if entry:
        set_led(midi_out, entry["status"], entry["note"], value)

# === BPM and Flash Control ===
press_times = deque()
bpm_lock = threading.Lock()
bpm_phase_event = threading.Event()

current_bpm = 120
bpm_leds = [(0, 7), (1, 7), (2, 7)]

def update_bpm():
    global current_bpm
    now = time.time()

    # Remove old entries
    while press_times and (now - press_times[0] > bpm_max_age):
        press_times.popleft()

    if len(press_times) >= bpm_min_taps:
        intervals = [t2 - t1 for t1, t2 in zip(press_times, list(press_times)[1:])]
        avg_interval = sum(intervals) / len(intervals)
        bpm = 60 / avg_interval
        with bpm_lock:
            current_bpm = bpm
            logging.info(f"BPM updated: {current_bpm:.2f}")

def handle_note_on(note):
    if note == 120:  # H9
        press_times.append(time.time())
        update_bpm()

def flash_bpm_loop(midi_out):
    on_val = led_color(3, 0)
    off_val = led_color(0, 0)

    while True:
        with bpm_lock:
            bpm = current_bpm
        interval = 60 / bpm

        # LED on
        for (x, y) in bpm_leds:
            set_led_at_xy(midi_out, x, y, on_val)
        time.sleep(0.1)

        # LED off
        for (x, y) in bpm_leds:
            set_led_at_xy(midi_out, x, y, off_val)

        # Wait remaining beat duration or until resync
        waited = 0
        step = 0.01
        while waited < (interval - 0.1):
            if bpm_phase_event.is_set():
                bpm_phase_event.clear()
                break
            time.sleep(step)
            waited += step


# === MIDI Port Helpers ===
def open_named_port(midi, name, direction="input"):
    ports = midi.get_ports()
    for i, port in enumerate(ports):
        if name.lower() in port.lower():
            midi.open_port(i)
            logging.info(f"{direction.capitalize()} port opened: {port}")
            return
    raise Exception(f"{direction.capitalize()} port for '{name}' not found. Available: {ports}")

def midi_input_callback(event, data=None):
    message, _ = event
    if message[0] == 0x90 and message[2] > 0:  # Note On with velocity > 0
        note = message[1]
        handle_note_on(note)

# === Entry Point ===
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    midi_in = rtmidi.MidiIn()
    midi_out = rtmidi.MidiOut()

    open_named_port(midi_in, controller_name, "input")
    open_named_port(midi_out, controller_name, "output")

    midi_in.set_callback(midi_input_callback)

    # Start BPM flashing thread
    threading.Thread(target=flash_bpm_loop, args=(midi_out,), daemon=True).start()

    # Idle loop
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        logging.info("Exiting.")
