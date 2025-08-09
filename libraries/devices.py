# libraries/devices.py

import asyncio
import logging
import mido
import pygame

logger = logging.getLogger(__name__)


class DeviceEvent:
    """
    Normalized input event used by InputMapper.
    device: str  e.g. "apc40", "launchpad", "joystick"
    control: Any e.g. "axis_2", ("note", 48, 1), ("cc", 21, 1)
    value: float/int (velocity, cc value, axis position, etc.)
    """
    def __init__(self, device: str, control, value):
        self.device = device
        self.control = control
        self.value = value


class BaseInputDevice:
    """
    Base class for devices that push DeviceEvent objects into a queue.
    """
    def __init__(self, event_queue: asyncio.Queue, device_name: str):
        self.event_queue = event_queue
        self.device_name = device_name

    async def push_event(self, control, value):
        await self.event_queue.put(DeviceEvent(self.device_name, control, value))


# -------------------
# Joystick Controller
# -------------------
class LogiJoystickController(BaseInputDevice):
    def __init__(self, event_queue, osc_bus=None,
                 device_index=0, deadzone=0.05, emit_all_every=0.1):
        super().__init__(event_queue, "joystick")
        self.device_index = device_index
        self.deadzone = deadzone
        self.emit_all_every = emit_all_every
        self.joystick = None

    def _init_joystick(self) -> bool:
        pygame.init()
        pygame.joystick.init()
        count = pygame.joystick.get_count()
        if count <= self.device_index:
            logger.warning("No joystick found at index %d (count=%d)", self.device_index, count)
            return False
        self.joystick = pygame.joystick.Joystick(self.device_index)
        self.joystick.init()
        logger.info("Joystick connected: %s", self.joystick.get_name())
        return True

    async def run(self):
        if not self._init_joystick():
            return

        clock = pygame.time.Clock()
        # we’ll push at ~1/emit_all_every Hz
        while True:
            pygame.event.pump()

            # Axes
            for axis in range(self.joystick.get_numaxes()):
                val = self.joystick.get_axis(axis)
                if abs(val) < self.deadzone:
                    val = 0.0
                await self.push_event(f"axis_{axis}", float(val))

            # Buttons
            for btn in range(self.joystick.get_numbuttons()):
                state = int(self.joystick.get_button(btn))
                await self.push_event(f"button_{btn}", state)

            # Hats
            for hat in range(self.joystick.get_numhats()):
                x, y = self.joystick.get_hat(hat)
                await self.push_event(f"hat_{hat}_x", int(x))
                await self.push_event(f"hat_{hat}_y", int(y))

            # Throttle loop to a reasonable rate
            if self.emit_all_every > 0:
                clock.tick(max(1, int(1 / self.emit_all_every)))
            else:
                await asyncio.sleep(self.emit_all_every if self.emit_all_every > 0 else 0)


# -------------------
# MIDI Input Device
# -------------------
class MidiInputDevice(BaseInputDevice):
    def __init__(self, event_queue, device_name: str, port_match: str):
        super().__init__(event_queue, device_name)
        self.port_match = port_match

    def _find_port(self):
        for name in mido.get_input_names():
            if self.port_match.lower() in name.lower():
                return name
        return None

    async def run(self):
        # Extra visibility
        all_ins = mido.get_input_names()
        logger.debug("[%s] Available MIDI IN ports: %s", self.device_name, all_ins)

        port_name = self._find_port()
        if not port_name:
            logger.warning("[%s] No matching MIDI input found for '%s'", self.device_name, self.port_match)
            return

        logger.info("[%s] Listening on MIDI input: %s", self.device_name, port_name)

        loop = asyncio.get_event_loop()

        def _cb(msg):
            try:
                logger.debug("[%s] Raw MIDI: %s", self.device_name, msg)
                if msg.type == "note_on":
                    fut = asyncio.run_coroutine_threadsafe(
                        self.push_event(("note", msg.note, msg.channel), msg.velocity), loop)
                    fut.result()  # make exceptions visible
                elif msg.type == "note_off":
                    fut = asyncio.run_coroutine_threadsafe(
                        self.push_event(("note", msg.note, msg.channel), 0), loop)
                    fut.result()
                elif msg.type == "control_change":
                    fut = asyncio.run_coroutine_threadsafe(
                        self.push_event(("cc", msg.control, msg.channel), msg.value), loop)
                    fut.result()
            except Exception as e:
                logger.exception("[%s] MIDI callback error: %s", self.device_name, e)

        # Keep the port open with a callback; this spawns a background thread
        inport = mido.open_input(port_name, callback=_cb)

        try:
            # Park this task forever; callback will feed events
            while True:
                await asyncio.sleep(1.0)
        finally:
            inport.close()
            logger.info("[%s] MIDI input closed", self.device_name)


class LaunchpadMiniController(MidiInputDevice):
    def __init__(self, event_queue, port_match="Launchpad"):
        super().__init__(event_queue, "launchpad", port_match)


class APC40MK2Controller(MidiInputDevice):
    def __init__(self, event_queue, port_match="APC40"):
        super().__init__(event_queue, "apc40", port_match)
