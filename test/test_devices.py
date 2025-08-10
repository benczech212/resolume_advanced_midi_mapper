# test/test_buttons.py
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # add repo root to sys.path

import asyncio
import logging
from run import load_yaml, DEFAULT_CONFIG
from libraries.devices import (
    JoystickController, LaunchpadMiniController, APC40MK2Controller
)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("button_test")

def is_buttonish(control):
    # MIDI notes -> ('note', note_num, channel)
    if isinstance(control, tuple) and control and control[0] == "note":
        return True
    # Joystick buttons / hats (axes are ignored here)
    if isinstance(control, str) and (control.startswith("button_") or control.startswith("hat_")):
        return True
    return False

def press_release(control, value):
    """
    Return ("PRESS"|"RELEASE"|None, extra_info) for button-like inputs.
    For MIDI notes: value>0 = PRESS, 0 = RELEASE
    For joystick buttons: 1 = PRESS, 0 = RELEASE
    For hat: log on any change (show -1/0/1), treat nonzero as PRESS.
    """
    if isinstance(control, tuple) and control[0] == "note":
        return ("PRESS" if value else "RELEASE", None)
    if isinstance(control, str):
        if control.startswith("button_"):
            return ("PRESS" if value else "RELEASE", None)
        if control.startswith("hat_"):
            # hats are -1/0/1 — consider any nonzero as PRESS
            return ("PRESS" if value else "RELEASE", None)
    return (None, None)

async def main():
    cfg = load_yaml("config.yml", DEFAULT_CONFIG)

    # Build devices from config flags
    q: asyncio.Queue = asyncio.Queue()
    devices = []
    if cfg.get("enable_joystick", True):
        devices.append(JoystickController(
            q,
            device_index=cfg.get("joystick_index", 0),
            deadzone=cfg.get("joystick_deadzone", 0.05),
            emit_all_every=cfg.get("joystick_emit_all_period", 0.1),
        ))
    if cfg.get("enable_launchpad", False):
        devices.append(LaunchpadMiniController(q, port_match=cfg["midi"]["launchpad_in_match"]))
    if cfg.get("enable_apc40", True):
        devices.append(APC40MK2Controller(q, port_match=cfg["midi"]["apc40_in_match"]))

    for d in devices:
        log.debug("Starting device task: %s", type(d).__name__)
    tasks = [asyncio.create_task(d.run()) for d in devices]

    # Edge detection to avoid spam
    last_vals = {}

    async def printer():
        while True:
            ev = await q.get()
            # Uncomment to see EVERYTHING:
            # log.debug("[EVENT] device=%s control=%s value=%s", ev.device, ev.control, ev.value)

            if not is_buttonish(ev.control):
                continue

            key = (ev.device, ev.control)
            prev = last_vals.get(key)
            if prev == ev.value:
                continue  # no change, skip
            last_vals[key] = ev.value

            kind, _ = press_release(ev.control, ev.value)
            if kind is None:
                continue

            # Pretty print MIDI channel as human (1..16)
            if isinstance(ev.control, tuple) and ev.control[0] == "note":
                _, note, ch = ev.control
                human_ch = ch + 1
                log.info("%s | %s note=%d ch=%d val=%s", kind, ev.device, note, human_ch, ev.value)
            else:
                # joystick buttons/hats
                log.info("%s | %s %s val=%s", kind, ev.device, ev.control, ev.value)

    tasks.append(asyncio.create_task(printer()))

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
