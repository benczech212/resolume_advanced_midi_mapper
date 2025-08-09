import asyncio
import time
import pygame
import mido
from typing import Any, Optional

from .osc_bus import OSCBus

class DeviceEvent:
    def __init__(self, device: str, control: Any, value: float):
        self.device = device
        self.control = control  # str or ('note', n) or ('cc', n)
        self.value = value

class BaseDevice:
    def __init__(self, name: str, event_queue: asyncio.Queue):
        self.name = name
        self.event_queue = event_queue

    async def run(self):
        raise NotImplementedError

class JoystickController(BaseDevice):
    def __init__(self, event_queue: asyncio.Queue, oscbus: OSCBus,
                 device_index: int = 0, deadzone: float = 0.05, emit_all_every: float = 0.1):
        super().__init__("joystick", event_queue)
        self.device_index = device_index
        self.deadzone = deadzone
        self.osc = oscbus
        self.initialized = False
        self.emit_all_every = emit_all_every
        self.last_emit_all = 0.0

    def _dz(self, v: float) -> float:
        return 0.0 if abs(v) < self.deadzone else v

    async def run(self):
        if not self.initialized:
            pygame.init()
            pygame.joystick.init()
            if pygame.joystick.get_count() <= self.device_index:
                print("No joystick found at index", self.device_index)
                return
            self.joy = pygame.joystick.Joystick(self.device_index)
            self.joy.init()
            self.initialized = True
            print("Joystick:", self.joy.get_name())

        while True:
            await asyncio.sleep(0.01)
            pygame.event.pump()

            axes_vals = []
            for axis in range(self.joy.get_numaxes()):
                v = self._dz(self.joy.get_axis(axis))
                axes_vals.append(v)
                await self.event_queue.put(DeviceEvent("joystick", f"axis_{axis}", float(v)))
                self.osc.send_joystick_axis(axis, float(v))

            btn_vals = []
            for btn in range(self.joy.get_numbuttons()):
                state = int(self.joy.get_button(btn))
                btn_vals.append(state)
                await self.event_queue.put(DeviceEvent("joystick", f"button_{btn}", state))
                self.osc.send_joystick_button(btn, state)

            hat_vals = []
            for h in range(self.joy.get_numhats()):
                x, y = self.joy.get_hat(h)
                hat_vals.append((x, y))
                await self.event_queue.put(DeviceEvent("joystick", f"hat_{h}_x", int(x)))
                await self.event_queue.put(DeviceEvent("joystick", f"hat_{h}_y", int(y)))
                self.osc.send_joystick_hat(h, int(x), int(y))

            now = time.time()
            if now - self.last_emit_all >= self.emit_all_every:
                snapshot = { "axes": axes_vals, "buttons": btn_vals, "hats": hat_vals }
                self.osc.send_joystick_all(snapshot)
                self.last_emit_all = now

class MidiInputDevice(BaseDevice):
    def __init__(self, name: str, event_queue: asyncio.Queue, port_match: str):
        super().__init__(name, event_queue)
        self.port_match = port_match
        self.inport: Optional[mido.ports.BaseInput] = None

    def _open_input(self):
        for name in mido.get_input_names():
            if self.port_match.lower() in name.lower():
                return mido.open_input(name)
        return None

    async def run(self):
        self.inport = self._open_input()
        if not self.inport:
            print(f"[{self.name}] MIDI input not found for match:", self.port_match)
            return
        loop = asyncio.get_event_loop()
        while True:
            msg = await loop.run_in_executor(None, self.inport.receive)
            if msg.type in ("note_on", "note_off"):
                val = msg.velocity if msg.type == "note_on" else 0
                await self.event_queue.put(DeviceEvent(self.name, ("note", msg.note), val))
            elif msg.type == "control_change":
                await self.event_queue.put(DeviceEvent(self.name, ("cc", msg.control), msg.value))

class LaunchpadMiniController(MidiInputDevice):
    def __init__(self, event_queue: asyncio.Queue, port_match="Launchpad"):
        super().__init__("launchpad", event_queue, port_match)

class APC40MK2Controller(MidiInputDevice):
    def __init__(self, event_queue: asyncio.Queue, port_match="APC40"):
        super().__init__("apc40", event_queue, port_match)
