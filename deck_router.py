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

from libraries.devices import (
    LogiJoystickController, 
    LaunchpadMiniController, APC40MK2Controller
)
from libraries.state_reflector import StateReflector
from libraries.resolume_http import fetch_composition, populate_deck_manager


def load_yaml(path: str, default_text: str = None) -> dict:
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    if default_text is not None:
        return yaml.safe_load(default_text)
    return {}


DEFAULT_CONFIG = """
osc:
  tx_host: "127.0.0.1"
  tx_port: 7000
  rx_host: "0.0.0.0"
  rx_port: 7001

http_api:
  host: "127.0.0.1"
  port: 8080
  timeout: 2.0
  refresh_seconds: 5.0

midi:
  launchpad_in_match: "Launchpad"
  launchpad_out_match: "Launchpad"
  apc40_in_match: "APC40"
  apc40_out_match: "APC40"

enable_joystick: true
joystick_index: 0
joystick_deadzone: 0.05
joystick_emit_all_period: 0.1

enable_launchpad: false
enable_apc40: true

reflect_hz: 30.0

# example mapping; override in your real config.yml
group_to_deck_mapping:
  "Stage": "stage"
  "Background": "background"
  "Wire Trace": "wires"
  "Merkaba": "merkaba"
  "Flower": "flower"
  "Top": "top"

# optional: deck->note maps for LED reflection policies (used by StateReflector if you want)
led_map:
  launchpad_deck_notes: {}
  apc_deck_notes: {}

# device-agnostic templates (expanded to bindings)
devices:
  apc40:
    kind: "midi"
    in_match: "APC40"
    out_match: "APC40"
    channel_to_deck:
      2: stage
      3: background
      4: wires
      5: merkaba
      6: flower
      7: top

templates:
  per_deck:
    - device: apc40
      rules:
        - control: ["note", 48, "{channel}"]
          action: toggle_effects
          deck: "{deck}"
          edge: press
        - control: ["note", 49, "{channel}"]
          action: toggle_colors
          deck: "{deck}"
          edge: press
        - control: ["note", 50, "{channel}"]
          action: toggle_transform
          deck: "{deck}"
          edge: press
        - control: ["note", 57, "{channel}"]
          action: set_fill
          deck: "{deck}"
          fixed_value: 0.0
          edge: press
        - control: ["note", 56, "{channel}"]
          action: set_fill
          deck: "{deck}"
          fixed_value: 0.25
          edge: press
        - control: ["note", 55, "{channel}"]
          action: set_fill
          deck: "{deck}"
          fixed_value: 0.5
          edge: press
        - control: ["note", 54, "{channel}"]
          action: set_fill
          deck: "{deck}"
          fixed_value: 0.75
          edge: press
        - control: ["note", 53, "{channel}"]
          action: set_fill
          deck: "{deck}"
          fixed_value: 1.0
          edge: press
        - control: ["note", 52, "{channel}"]
          action: stop_deck
          deck: "{deck}"
          edge: press

  global:
    - device: apc40
      control: ["note", 81, 0]
      action: stop_all_decks
      edge: press
    - device: apc40
      control: ["note", 91, 0]
      action: start_autopilot
      edge: press
    - device: apc40
      control: ["note", 92, 0]
      action: stop_autopilot
      edge: press
    - device: apc40
      control: ["note", 93, 0]
      action: toggle_record
      edge: press
    - device: apc40
      control: ["note", 99, 0]
      action: tempo_tap
      edge: press
    - device: apc40
      control: ["note", 101, 0]
      action: nudge_minus
      edge: press
    - device: apc40
      control: ["note", 100, 0]
      action: nudge_plus
      edge: press
    - device: apc40
      control: ["note", 98, 0]
      action: bpm_resync
      edge: press
    - device: apc40
      control: ["note", 65, 0]
      action: toggle_metronome
      edge: press
"""


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

        # Callbacks and InputMapper (use template expansion → bindings)
        self.callbacks = CallbackRegistry(self.deck_mgr, self.osc)
        expanded_bindings = expand_templates(cfg)
        logging.debug("Expanded %d bindings", len(expanded_bindings))
        self.mapper = InputMapper(self.callbacks, expanded_bindings)

        # LED reflector
        self.reflector = StateReflector(
            self.deck_mgr, self.osc,
            self.lp_bus.mapper if self.lp_bus else None,
            self.apc_bus.mapper if self.apc_bus else None,
            hz=cfg.get("reflect_hz", 30.0)
        )
        led_map = cfg.get("led_map", {})
        self.reflector.lp_note_map = {k: int(v) for k, v in (led_map.get("launchpad_deck_notes", {}) or {}).items()}
        self.reflector.apc_note_map = {k: int(v) for k, v in (led_map.get("apc_deck_notes", {}) or {}).items()}

        # Devices -> events
        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.devices = []
        if cfg.get("enable_joystick", True):
            self.devices.append(LogiJoystickController(
                self.event_queue, self.osc,
                device_index=cfg.get("joystick_index", 0),
                deadzone=cfg.get("joystick_deadzone", 0.05),
                emit_all_every=cfg.get("joystick_emit_all_period", 0.1),
            ))
        if cfg.get("enable_launchpad", False):
            self.devices.append(LaunchpadMiniController(self.event_queue, port_match=cfg["midi"]["launchpad_in_match"]))
        if cfg.get("enable_apc40", True):
            self.devices.append(APC40MK2Controller(self.event_queue, port_match=cfg["midi"]["apc40_in_match"]))

    async def _pump_events(self):
        while True:
            ev = await self.event_queue.get()
            # Debug callout on *every* input event (MIDI & joystick)
            logging.debug("[EVENT] device=%s control=%s value=%s", ev.device, ev.control, ev.value)
            # If you want strictly MIDI only, uncomment:
            # if isinstance(ev.control, tuple) and ev.control and ev.control[0] in ("note", "cc"):
            await self.mapper.handle_event(ev)

    async def _run_devices(self):
      for d in self.devices:
          logging.debug("Starting device task: %s", type(d).__name__)
      tasks = [asyncio.create_task(d.run()) for d in self.devices]
      await asyncio.gather(*tasks)


    async def _refresh_composition_http(self):
        http_cfg = self.cfg.get("http_api", {})
        host = http_cfg.get("host", "127.0.0.1")
        port = int(http_cfg.get("port", 8080))
        timeout = float(http_cfg.get("timeout", 2.0))
        period = float(http_cfg.get("refresh_seconds", 5.0))

        while True:
            data = fetch_composition(host, port, timeout=timeout)
            if data:
                populate_deck_manager(self.deck_mgr, data)
            await asyncio.sleep(period)

    async def run(self):
      loop = asyncio.get_event_loop()
      await self.osc.start_server(loop)
      logging.info("OSC server started on %s:%s", self.cfg["osc"]["rx_host"], self.cfg["osc"]["rx_port"])
      tasks = [
          asyncio.create_task(self._pump_events()),
          asyncio.create_task(self._run_devices()),
          asyncio.create_task(self.reflector.run()),
          asyncio.create_task(self._refresh_composition_http()),
      ]
      await asyncio.gather(*tasks)




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
