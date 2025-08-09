import asyncio
import json
import re
from typing import Optional
from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer

from .deck_model import DeckManager

class OSCBus:
    """
    - TX to Resolume (control)
    - RX from Resolume (feedback -> groups/layers discovery)
    - Custom joystick telemetry under /czechb/joysticks/*
    """
    def __init__(self, tx_host: str, tx_port: int, rx_host: str, rx_port: int, deck_mgr: DeckManager):
        self.client = SimpleUDPClient(tx_host, tx_port)
        self.rx_host = rx_host
        self.rx_port = rx_port
        self.deck_mgr = deck_mgr

        self.dispatcher = Dispatcher()
        self.dispatcher.map("/composition/groups/*/name", self._on_group_name)
        self.dispatcher.map("/composition/groups/*/layers/*/name", self._on_layer_name)
        self.dispatcher.set_default_handler(self._on_any)

        self._server: Optional[AsyncIOOSCUDPServer] = None
        self._transport = None

        self._re_group = re.compile(r"^/composition/groups/(\d+)/name$")
        self._re_layer = re.compile(r"^/composition/groups/(\d+)/layers/(\d+)/name$")

    # Incoming
    def _on_group_name(self, addr: str, *args):
        m = self._re_group.match(addr)
        if not m: return
        g_idx = int(m.group(1))
        name = str(args[0]) if args else f"Group {g_idx}"
        self.deck_mgr.upsert_group(g_idx, name)

    def _on_layer_name(self, addr: str, *args):
        m = self._re_layer.match(addr)
        if not m: return
        g_idx = int(m.group(1))
        l_idx = int(m.group(2))
        name = str(args[0]) if args else f"Layer {l_idx}"
        self.deck_mgr.upsert_layer(g_idx, l_idx, name)

    def _on_any(self, addr, *args):
        # Uncomment for diagnostics:
        # print("[OSC-IN]", addr, args)
        pass

    async def start_server(self, loop: asyncio.AbstractEventLoop):
        self._server = AsyncIOOSCUDPServer((self.rx_host, self.rx_port), self.dispatcher, loop)
        transport, protocol = await self._server.create_serve_endpoint()
        self._transport = transport

    async def stop_server(self):
        if self._transport:
            self._transport.close()

    # Outgoing control (placeholder addresses—adjust to your Resolume schema)
    def send_play(self, deck_name: str, on: bool):
        self.client.send_message(f"/deck/{deck_name}/play", 1 if on else 0)

    def send_effects_toggle(self, deck_name: str, on: bool):
        self.client.send_message(f"/deck/{deck_name}/effects", 1 if on else 0)

    def send_colors_toggle(self, deck_name: str, on: bool):
        self.client.send_message(f"/deck/{deck_name}/colors", 1 if on else 0)

    def send_fill(self, deck_name: str, value: float):
        self.client.send_message(f"/deck/{deck_name}/fill", float(value))

    # Joystick telemetry
    def send_joystick_axis(self, index: int, value: float):
        self.client.send_message(f"/czechb/joysticks/axis/{index}/value", float(value))

    def send_joystick_button(self, index: int, state: int):
        self.client.send_message(f"/czechb/joysticks/button/{index}/value", int(state))

    def send_joystick_hat(self, index: int, x: int, y: int):
        self.client.send_message(f"/czechb/joysticks/hat/{index}/x", int(x))
        self.client.send_message(f"/czechb/joysticks/hat/{index}/y", int(y))

    def send_joystick_all(self, snapshot: dict):
        self.client.send_message("/czechb/joysticks/all", json.dumps(snapshot))
