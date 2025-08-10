# test/test_buttons.py
import os, sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # repo root

import asyncio
import logging
import mido
from run import load_yaml, DEFAULT_CONFIG

# Import whichever joystick class exists
try:
    from libraries.devices import JoystickController as Joy
except ImportError:
    from libraries.devices import JoystickController as Joy
from libraries.devices import LaunchpadMiniController, APC40MK2Controller

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
log = logging.getLogger("button_test")

def _press_release(control, value):
    if isinstance(control, tuple) and control[0] == "note":
        return "PRESS" if value else "RELEASE"
    if isinstance(control, str) and (control.startswith("button_") or control.startswith("hat_")):
        return "PRESS" if value else "RELEASE"
    return None

async def main():
    cfg = load_yaml("config.yml", DEFAULT_CONFIG)

    log.debug("MIDI INPUTS: %s", mido.get_input_names())
    log.debug("MIDI OUTPUTS: %s", mido.get_output_names())

    q: asyncio.Queue = asyncio.Queue()
    devices = []
    if cfg.get("enable_joystick", True):
        devices.append(Joy(q,
                           device_index=cfg.get("joystick_index", 0),
                           deadzone=cfg.get("joystick_deadzone", 0.05),
                           emit_all_every=cfg.get("joystick_emit_all_period", 0.1)))
    if cfg.get("enable_launchpad", True):
        devices.append(LaunchpadMiniController(q, port_match=cfg["midi"]["launchpad_in_match"]))
    if cfg.get("enable_apc40", True):
        devices.append(APC40MK2Controller(q, port_match=cfg["midi"]["apc40_in_match"]))

    def _report(t: asyncio.Task):
        try: t.result()
        except Exception as e: logging.exception("Device task crashed: %s", e)

    tasks = [asyncio.create_task(d.run()) for d in devices]
    for t in tasks: t.add_done_callback(_report)

    async def printer():
        last = {}
        while True:
            ev = await q.get()
            log.debug("[EVENT] device=%s control=%s value=%s", ev.device, ev.control, ev.value)
            # edge detection
            key = (ev.device, ev.control)
            if last.get(key) == ev.value:
                continue
            last[key] = ev.value
            kind = _press_release(ev.control, ev.value)
            if isinstance(ev.control, tuple):  # MIDI note
                _, note, ch = ev.control
                log.info("%s | %s note=%d ch=%d val=%s", kind or "-", ev.device, note, ch+1, ev.value)
            else:
                log.info("%s | %s %s val=%s", kind or "-", ev.device, ev.control, ev.value)

    tasks.append(asyncio.create_task(printer()))
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
