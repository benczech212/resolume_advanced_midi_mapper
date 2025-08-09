import asyncio
import yaml

from libraries.deck_model import DeckManager
from libraries.osc_bus import OSCBus
from libraries.midi_bus import MidiBus
from libraries.callbacks import CallbackRegistry
from libraries.input_mapper import InputMapper
from libraries.devices import (
    JoystickController, LaunchpadMiniController, APC40MK2Controller
)
from libraries.state_reflector import StateReflector
from libraries.resolume_http import fetch_composition, populate_deck_manager

def load_yaml(path: str, default_text: str = None) -> dict:
    if path is None and default_text is not None:
        return yaml.safe_load(default_text)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

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

enable_launchpad: true
enable_apc40: true

reflect_hz: 30.0

group_to_deck_mapping:
  "Group A": "deck_a"
  "Group B": "deck_b"

led_map:
  launchpad_deck_notes:
    deck_a: 64
    deck_b: 65
  apc_deck_notes:
    deck_a: 40
    deck_b: 41

bindings:
  - device: "joystick"
    control: "button_0"
    action: "toggle_effects"
    deck: "deck_a"
    edge: "press"

  - device: "joystick"
    control: "axis_2"
    action: "set_fill"
    deck: "deck_a"

  - device: "launchpad"
    control: ["note", 64]
    action: "toggle_colors"
    deck: "deck_b"
    edge: "press"

  - device: "apc40"
    control: ["cc", 21]
    action: "set_fill"
    deck: "deck_b"

  - device: "launchpad"
    control: ["note", 65]
    action: "stop_deck"
    deck: "deck_b"
    edge: "release"
"""

class App:
    def __init__(self, cfg: dict, lp_led_map: dict, apc_led_map: dict):
        self.cfg = cfg
        self.deck_mgr = DeckManager(cfg["group_to_deck_mapping"])

        osc_cfg = cfg["osc"]
        self.osc = OSCBus(
            tx_host=osc_cfg["tx_host"], tx_port=osc_cfg["tx_port"],
            rx_host=osc_cfg["rx_host"], rx_port=osc_cfg["rx_port"],
            deck_mgr=self.deck_mgr
        )

        self.lp_bus = MidiBus(cfg["midi"]["launchpad_out_match"], lp_led_map, "launchpad") if cfg.get("enable_launchpad", True) else None
        self.apc_bus = MidiBus(cfg["midi"]["apc40_out_match"], apc_led_map, "apc40") if cfg.get("enable_apc40", True) else None

        self.callbacks = CallbackRegistry(self.deck_mgr, self.osc)
        self.mapper = InputMapper(self.callbacks, cfg.get("bindings", []))

        self.reflector = StateReflector(
            self.deck_mgr, self.osc,
            self.lp_bus.mapper if self.lp_bus else None,
            self.apc_bus.mapper if self.apc_bus else None,
            hz=cfg.get("reflect_hz", 30.0)
        )
        led_map = cfg.get("led_map", {})
        self.reflector.lp_note_map = {k: int(v) for k, v in (led_map.get("launchpad_deck_notes", {}) or {}).items()}
        self.reflector.apc_note_map = {k: int(v) for k, v in (led_map.get("apc_deck_notes", {}) or {}).items()}

        self.event_queue: asyncio.Queue = asyncio.Queue()
        self.devices = []
        if cfg.get("enable_joystick", True):
            self.devices.append(JoystickController(
                self.event_queue, self.osc,
                device_index=cfg.get("joystick_index", 0),
                deadzone=cfg.get("joystick_deadzone", 0.05),
                emit_all_every=cfg.get("joystick_emit_all_period", 0.1),
            ))
        if cfg.get("enable_launchpad", True):
            self.devices.append(LaunchpadMiniController(self.event_queue, port_match=cfg["midi"]["launchpad_in_match"]))
        if cfg.get("enable_apc40", True):
            self.devices.append(APC40MK2Controller(self.event_queue, port_match=cfg["midi"]["apc40_in_match"]))

    async def _pump_events(self):
        while True:
            ev = await self.event_queue.get()
            await self.mapper.handle_event(ev)

    async def _run_devices(self):
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
        tasks = [
            asyncio.create_task(self._pump_events()),
            asyncio.create_task(self._run_devices()),
            asyncio.create_task(self.reflector.run()),
            asyncio.create_task(self._refresh_composition_http()),
        ]
        await asyncio.gather(*tasks)

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=str, default=None, help="Path to config.yml")
    parser.add_argument("--lp-map", type=str, default=None, help="Path to launchpad_led_map.yml")
    parser.add_argument("--apc-map", type=str, default=None, help="Path to apc_led_map.yml")
    args = parser.parse_args()

    cfg = load_yaml(args.config, DEFAULT_CONFIG)
    lp_map = load_yaml(args.lp_map) if cfg.get("enable_launchpad", True) and args.lp_map else {}
    apc_map = load_yaml(args.apc_map) if cfg.get("enable_apc40", True) and args.apc_map else {}

    app = App(cfg, lp_map, apc_map)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
