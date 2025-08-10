# deck_router.py

import asyncio
import logging
import os
import yaml
import mido


from libraries.deck_model import DeckManager
from libraries.osc_bus import OSCBus
from libraries.midi_bus import MidiBus
from libraries.callbacks import CallbackRegistry
from libraries.input_mapper import InputMapper
from libraries.binding_templates import expand_templates
from libraries.ui_decks import DeckStateUI

from libraries.devices import (
    JoystickController, 
    LaunchpadMiniController, APC40MK2Controller
)
from libraries.state_reflector import StateReflector, build_deck_to_channel_from_cfg
from libraries.resolume_http import fetch_composition, populate_deck_manager


def load_yaml(path: str, default_text: str = None) -> dict:
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    if default_text is not None:
        return yaml.safe_load(default_text)
    return {}
# load config-default.yml 

DEFAULT_CONFIG = load_yaml("config-default.yml")

class App:
    def __init__(self, cfg: dict, lp_led_map: dict, apc_led_map: dict):
        self.cfg = cfg

        # Deck state + OSC bus
        self.deck_mgr = DeckManager(cfg["group_to_deck_mapping"])
        osc_cfg = cfg["osc"]
        self.osc = OSCBus(
            tx_host=osc_cfg["tx_host"], tx_port=osc_cfg["tx_port"],
            rx_host=osc_cfg["rx_host"], rx_port=osc_cfg["rx_port"],
            deck_mgr=self.deck_mgr
        )

        # MIDI LED buses
        self.lp_bus = MidiBus(cfg["midi"]["launchpad_out_match"], lp_led_map, "launchpad") if cfg.get("enable_launchpad", False) else None
        self.apc_bus = MidiBus(cfg["midi"]["apc40_out_match"], apc_led_map, "apc40") if cfg.get("enable_apc40", True) else None

        # NEW reflector wiring (only this one; do not reassign later)
        deck_to_channel = build_deck_to_channel_from_cfg(self.cfg)
        self.reflector = StateReflector(
    self.deck_mgr,
    self.osc,
    hz=self.cfg.get("reflect_hz", 30.0),
    apc_bus=self.apc_bus,
    deck_to_channel=deck_to_channel,
    blink_hz=self.cfg.get("blink_hz", 2.0),   # <--- NEW knob
)

        # Callbacks and InputMapper
        self.callbacks = CallbackRegistry(self.deck_mgr, self.osc)
        expanded_bindings = expand_templates(cfg)
        logging.debug("Expanded %d bindings", len(expanded_bindings))
        self.mapper = InputMapper(self.callbacks, expanded_bindings)

        # Devices -> events
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.devices = []
        joy_cfg = cfg.get("joystick", {})
        if joy_cfg.get("enabled", True):
            poll = 1.0 / max(1, int(joy_cfg.get("poll_hz", 20)))
            self.devices.append(JoystickController(
                self.event_queue, self.osc,
                device_index=joy_cfg.get("index", 0),
                deadzone=joy_cfg.get("deadzone", 0.05),
                emit_all_every=poll,
                axis_step=joy_cfg.get("axis_step", 0.02),
            ))
        if cfg.get("enable_launchpad", False):
            self.devices.append(LaunchpadMiniController(self.event_queue, port_match=cfg["midi"]["launchpad_in_match"]))
        if cfg.get("enable_apc40", True):
            self.devices.append(APC40MK2Controller(self.event_queue, port_match=cfg["midi"]["apc40_in_match"]))


    async def _pump_events(self):
        while True:
            ev = await self.event_queue.get()
            logging.debug("[EVENT] device=%s control=%s value=%s", ev.device, ev.control, ev.value)

            # Let normal bindings run first (set_fill etc.)
            await self.mapper.handle_event(ev)

            # --- NEW: repaint fills after APC release on notes 57..53 ---
            try:
                if (
                    ev.device == "apc40"
                    and isinstance(ev.control, tuple)
                    and len(ev.control) >= 2
                    and ev.control[0] == "note"
                ):
                    note = ev.control[1]
                    ch = ev.control[2] if len(ev.control) >= 3 else 0  # mido channel (0-based)
                    if note in (57, 56, 55, 54, 53, 52) and (ev.value == 0):
                        if hasattr(self.reflector, "refresh_deck_by_channel"):
                            self.reflector.refresh_deck_by_channel(ch)
            except Exception:
                logging.exception("post-release LED refresh failed")

    async def _run_devices(self):
      for d in self.devices:
          logging.debug("Starting device task: %s", type(d).__name__)
      tasks = [asyncio.create_task(d.run()) for d in self.devices]
      await asyncio.gather(*tasks)


    async def _load_composition_http_once(self):
        http_cfg = self.cfg.get("http_api", {})
        host = http_cfg.get("host", "127.0.0.1")
        port = int(http_cfg.get("port", 8080))
        timeout = float(http_cfg.get("timeout", 2.0))
        data = fetch_composition(host, port, timeout=timeout)
        if data:
            populate_deck_manager(self.deck_mgr, data)
            logging.info("Composition loaded once at startup")
        else:
            logging.warning("Composition fetch failed at startup")

    async def run(self):
        self.ui = None
        ui_cfg = self.cfg.get("ui", {})
        if ui_cfg.get("enable", False):
            self.ui = DeckStateUI(
                self.deck_mgr,
                fps=ui_cfg.get("fps", 30),
                total_slots=ui_cfg.get("total_slots", 8),
                slot_order=build_slot_order_from_channels(self.cfg, total_slots=8)
            )

        loop = asyncio.get_running_loop()
        await self.osc.start_server(loop)
        logging.info("OSC server started on %s:%s", self.cfg["osc"]["rx_host"], self.cfg["osc"]["rx_port"])

        # Load composition ONCE
        await self._load_composition_http_once()

        # Reset LEDs/notes on start (unchanged)
        try:
            dev_cfg = (self.cfg.get("devices", {}) or {}).get("apc40", {}) or {}
            if dev_cfg.get("reset_notes_on_start", True) and self.apc_bus:
                self.apc_bus.all_notes_off(channels=range(16))
            lp_cfg = (self.cfg.get("devices", {}) or {}).get("launchpad", {}) or {}
            if lp_cfg.get("reset_notes_on_start", False) and self.lp_bus:
                self.lp_bus.all_notes_off(channels=range(16))
        except Exception:
            logging.exception("LED reset on start failed")

        tasks = [
            asyncio.create_task(self._pump_events()),
            asyncio.create_task(self._run_devices()),
            asyncio.create_task(self.reflector.run()),
            # (periodic HTTP refresh removed)
        ]
        if self.ui:
            tasks.append(asyncio.create_task(self.ui.run()))
        await asyncio.gather(*tasks)

def build_slot_order_from_channels(cfg, total_slots=8):
    """
    Returns a list of length total_slots where index (slot-1) contains the deck name
    mapped from devices.apc40.channel_to_deck. Missing channels become None (blank).
    """
    ch2d = (cfg.get("devices", {})
              .get("apc40", {})
              .get("channel_to_deck", {})) or {}
    # keys may be strings from YAML; normalize to int
    norm = {}
    for k, v in ch2d.items():
        try:
            norm[int(k)] = v
        except Exception:
            continue

    slots = []
    for ch in range(1, total_slots + 1):
        slots.append(norm.get(ch))  # None if not present
    return slots


def main():
    # Logging setup
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    logging.info("Booting deck router")
    logging.debug("MIDI INPUTS: %s", mido.get_input_names())
    logging.debug("MIDI OUTPUTS: %s", mido.get_output_names())

    # Load config + optional LED maps
    cfg_path = "config.yml"
    lp_map_path = "launchpad_led_map.yml"
    apc_map_path = "apc_led_map.yml"

    cfg = load_yaml(cfg_path, DEFAULT_CONFIG)
    lp_map = load_yaml(lp_map_path) if cfg.get("enable_launchpad", False) and os.path.exists(lp_map_path) else {}
    apc_map = load_yaml(apc_map_path) if cfg.get("enable_apc40", True) and os.path.exists(apc_map_path) else {}

    logging.debug("Config loaded. enable_apc40=%s enable_launchpad=%s", cfg.get("enable_apc40", True), cfg.get("enable_launchpad", False))

    app = App(cfg, lp_map, apc_map)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logging.info("Shutting down (KeyboardInterrupt)")
    except Exception as e:
        logging.exception("Fatal error: %s", e)


if __name__ == "__main__":
    main()
