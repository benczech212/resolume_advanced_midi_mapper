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
class JoystickController(BaseInputDevice):
    def __init__(self, event_queue, osc_bus=None,
                 device_index=0, deadzone=0.05, emit_all_every=0.1,
                 axis_step=0.02):
        super().__init__(event_queue, "joystick")
        self.device_index = device_index
        self.deadzone = deadzone
        self.emit_all_every = emit_all_every
        self.axis_step = axis_step
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

        logger.debug("[joystick] axes=%d buttons=%d hats=%d",
                    self.joystick.get_numaxes(),
                    self.joystick.get_numbuttons(),
                    self.joystick.get_numhats())

        # Remember last-emitted values
        last_axes: dict[int, float] = {}
        last_buttons: dict[int, int] = {}
        last_hats: dict[tuple[int, str], int] = {}

        # Tune this to control noise/verbosity (e.g., 0.02 = ~2% step)
        axis_step = 0.02

        while True:
            pygame.event.pump()

            # Axes: [-1..1] -> emit only if quantized value changed
            for axis in range(self.joystick.get_numaxes()):
                raw = float(self.joystick.get_axis(axis))
                val = 0.0 if abs(raw) < self.deadzone else raw
                if axis_step > 0:
                    q = round(val / axis_step) * axis_step
                else:
                    q = val
                if last_axes.get(axis) != q:
                    last_axes[axis] = q
                    await self.push_event(f"axis_{axis}", q)
                    logger.debug("[joystick] axis_%d -> %.3f", axis, q)

            # Buttons: 0/1 -> emit only on change
            for btn in range(self.joystick.get_numbuttons()):
                state = int(self.joystick.get_button(btn))
                if last_buttons.get(btn) != state:
                    last_buttons[btn] = state
                    await self.push_event(f"button_{btn}", state)
                    logger.debug("[joystick] button_%d -> %d", btn, state)

            # Hats: (-1,0,1) per axis -> emit only on change
            for hat in range(self.joystick.get_numhats()):
                x, y = self.joystick.get_hat(hat)
                if last_hats.get((hat, "x")) != int(x):
                    last_hats[(hat, "x")] = int(x)
                    await self.push_event(f"hat_{hat}_x", int(x))
                    logger.debug("[joystick] hat_%d_x -> %d", hat, x)
                if last_hats.get((hat, "y")) != int(y):
                    last_hats[(hat, "y")] = int(y)
                    await self.push_event(f"hat_{hat}_y", int(y))
                    logger.debug("[joystick] hat_%d_y -> %d", hat, y)

            # Cooperative yield (set lower for snappier UI, higher to reduce CPU)
            await asyncio.sleep(self.emit_all_every if self.emit_all_every > 0 else 0.05)


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
        # import mido, asyncio, logging
        logger = logging.getLogger(__name__)

        all_ins = mido.get_input_names()
        logger.debug("[%s] Available MIDI IN ports: %s", self.device_name, all_ins)

        port_name = self._find_port()
        logger.debug("[%s] Selected MIDI IN: %s (match=%s)", self.device_name, port_name, self.port_match)
        if not port_name:
            logger.warning("[%s] No matching MIDI input found for '%s'", self.device_name, self.port_match)
            return

        loop = asyncio.get_event_loop()

        def _cb(msg):
            # logger.debug("[%s] Raw MIDI: %s", self.device_name, msg)  # FIRST touchpoint
            try:
                if msg.type == "note_on":
                    asyncio.run_coroutine_threadsafe(
                        self.push_event(("note", msg.note, msg.channel), msg.velocity), loop
                    ).result()
                elif msg.type == "note_off":
                    asyncio.run_coroutine_threadsafe(
                        self.push_event(("note", msg.note, msg.channel), 0), loop
                    ).result()
                elif msg.type == "control_change":
                    asyncio.run_coroutine_threadsafe(
                        self.push_event(("cc", msg.control, msg.channel), msg.value), loop
                    ).result()
            except Exception as e:
                logger.exception("[%s] MIDI callback error: %s", self.device_name, e)

        inport = mido.open_input(port_name, callback=_cb)
        logger.info("[%s] Listening on MIDI input: %s", self.device_name, port_name)
        try:
            while True:
                await asyncio.sleep(1.0)  # keep task alive
        finally:
            inport.close()


class LaunchpadMiniController(MidiInputDevice):
    def __init__(self, event_queue, port_match="Launchpad"):
        super().__init__(event_queue, "launchpad", port_match)


class APC40MK2Controller(MidiInputDevice):
    def __init__(self, event_queue, port_match="APC40"):
        super().__init__(event_queue, "apc40", port_match)
