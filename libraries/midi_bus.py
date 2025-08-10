# libraries/midi_bus.py
import logging
from typing import Iterable, Optional, Sequence

import mido

try:
    # Optional, but present in your repo; used by StateReflector
    from .led_mapper import LEDMapper
except Exception:  # pragma: no cover
    LEDMapper = None  # type: ignore

logger = logging.getLogger(__name__)


class MidiBus:
    """
    Simple MIDI OUT helper.

    Usage:
        bus = MidiBus(port_match="APC40", led_map=apc_led_map, device_name="apc40")
        bus.all_notes_off(channels=range(16))         # clear LEDs on startup
        bus.note_on(48, velocity=127, channel=1)      # human ch 2 -> mido ch 1
        bus.send_cc(7, 101, channel=4)                # set opacity fader, etc.

    Notes:
    - On APC/Launchpad, turning an LED off is usually `note_on` with velocity 0.
    - Standard MIDI "All Notes Off" is CC#123 with value 0 per channel; some
      controllers ignore it for LEDs, so we also brute-force note_on vel=0.
    """

    def __init__(self, port_match: str, led_map: Optional[dict], device_name: str):
        self.port_match = port_match or ""
        self.device_name = device_name
        self.port_name: Optional[str] = None
        self.outport: Optional[mido.ports.BaseOutput] = None

        # Expose mapper so StateReflector can use it (matches your App wiring)
        self.mapper = LEDMapper(led_map, device_name) if (LEDMapper and led_map) else None

        try:
            self.port_name = self._find_port(self.port_match)
            if self.port_name:
                self.outport = mido.open_output(self.port_name)
                logger.info("[midi:%s] Opened OUT: %s", self.device_name, self.port_name)
            else:
                logger.warning("[midi:%s] No matching MIDI OUT for '%s'. Outputs seen: %s",
                               self.device_name, self.port_match, mido.get_output_names())
        except Exception as e:
            logger.exception("[midi:%s] Failed to open MIDI OUT: %s", self.device_name, e)

    # -------------------- Port discovery --------------------

    @staticmethod
    def _find_port(match: str) -> Optional[str]:
        """Return the first output port name containing `match` (case-insensitive)."""
        if not match:
            return None
        wanted = match.lower()
        for name in mido.get_output_names():
            if wanted in name.lower():
                return name
        return None

    # -------------------- Low-level send --------------------

    def _send(self, msg: mido.Message) -> None:
        if not self.outport:
            logger.debug("[midi:%s] drop (no outport): %s", self.device_name, msg)
            return
        try:
            self.outport.send(msg)
        except Exception as e:
            logger.exception("[midi:%s] send failed: %s (%s)", self.device_name, msg, e)

    # -------------------- Helpers --------------------

    def note_on(self, note: int, velocity: int = 127, channel: int = 0) -> None:
        """Send note_on (APC LEDs use velocity for color/ON; 0 = off)."""
        self._send(mido.Message("note_on", note=int(note), velocity=int(velocity), channel=int(channel)))

    def note_off(self, note: int, channel: int = 0) -> None:
        """
        For many controllers, LED off is implemented as note_on with velocity 0.
        We still provide note_off for completeness.
        """
        # Prefer the 'vel 0' convention to ensure LEDs turn off on devices like APC/Launchpad
        self._send(mido.Message("note_on", note=int(note), velocity=0, channel=int(channel)))
        # Also send a formal note_off (harmless if ignored)
        self._send(mido.Message("note_off", note=int(note), velocity=0, channel=int(channel)))

    def send_cc(self, control: int, value: int, channel: int = 0) -> None:
        """Send a control change (0..127)."""
        v = max(0, min(127, int(value)))
        self._send(mido.Message("control_change", control=int(control), value=v, channel=int(channel)))

    # -------------------- Resets --------------------

    def all_notes_off(
        self,
        channels: Optional[Iterable[int]] = None,
        notes: Optional[Iterable[int]] = None,
        send_cc123: bool = True,
    ) -> None:
        """
        Reset LEDs / voices by forcing note_on velocity=0 for each note in each channel.
        Optionally also send CC#123 (All Notes Off) per channel.

        channels: iterable of 0..15 (default: all 16 channels)
        notes:    iterable of 0..127 (default: all 128 notes)
        """
        if not self.outport:
            logger.warning("[midi:%s] all_notes_off skipped: no outport", self.device_name)
            return

        ch_iter: Sequence[int] = list(channels) if channels is not None else range(16)
        note_iter: Sequence[int] = list(notes) if notes is not None else range(128)

        count = 0
        for ch in ch_iter:
            if send_cc123:
                # MIDI standard "All Notes Off"; some controllers ignore it for LEDs.
                self._send(mido.Message("control_change", control=123, value=0, channel=int(ch)))
            for n in note_iter:
                # Brute-force LED reset: note_on with velocity 0
                self._send(mido.Message("note_on", note=int(n), velocity=0, channel=int(ch)))
                count += 1

        logger.info("[midi:%s] all_notes_off sent: %d note clears across %d channel(s)",
                    self.device_name, count, len(ch_iter))

    def panic(self) -> None:
        """Convenience: CC123 and velocity-0 for all notes/all channels."""
        self.all_notes_off(channels=range(16), notes=range(128), send_cc123=True)

    # -------------------- Teardown --------------------

    def close(self) -> None:
        if self.outport:
            try:
                self.outport.close()
                logger.info("[midi:%s] Closed OUT: %s", self.device_name, self.port_name)
            except Exception:
                logger.exception("[midi:%s] error while closing outport", self.device_name)
            finally:
                self.outport = None

    def __del__(self):  # pragma: no cover
        try:
            self.close()
        except Exception:
            pass
