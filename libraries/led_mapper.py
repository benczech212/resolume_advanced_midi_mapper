import mido
from typing import Optional, Dict

class LEDMapper:
    """
    Device-agnostic LED API using per-device YAML mappings.

    YAML shape:
      device: launchpad|apc40
      defaults:
        colors: { off: 0, green: 60, yellow: 100, red: 127, on: 127 }
      notes:
        "64": { colors: { off: 0, green: 21, red: 5 } }
      ccs:
        "21": { colors: { off: 0, green: 127 } }
    """
    def __init__(self, outport: Optional[mido.ports.BaseOutput], mapping: dict, device_kind: str):
        self.out = outport
        self.mapping = mapping or {}
        self.device_kind = device_kind
        self.defaults = self.mapping.get("defaults", {})
        self.note_map = {int(k): v for k, v in (self.mapping.get("notes") or {}).items()}
        self.cc_map = {int(k): v for k, v in (self.mapping.get("ccs") or {}).items()}

    @staticmethod
    def launchpad_led_color(red=0, green=0, copy=True, clear=True, flash=False) -> int:
        flags = 0
        if flash:
            flags |= 8
        elif copy and clear:
            flags |= 12
        elif copy:
            flags |= 4
        elif clear:
            flags |= 8
        return (16 * int(green)) + int(red) + flags

    def _resolve_color_value(self, domain: dict, color_name: str) -> int:
        colors = domain.get("colors", {})
        if color_name in colors:
            return int(colors[color_name])
        dev_colors = (self.defaults or {}).get("colors", {})
        if color_name in dev_colors:
            return int(dev_colors[color_name])
        return int(dev_colors.get("off", 0)) if dev_colors else 0

    # Public ops
    def set_note_color(self, note: int, color_name: str):
        if not self.out: return
        domain = self.note_map.get(note, {})
        velocity = self._resolve_color_value(domain, color_name)
        self.out.send(mido.Message('note_on', note=note, velocity=velocity))

    def set_note_onoff(self, note: int, on: bool):
        self.set_note_color(note, "on" if on else "off")

    def set_cc_color(self, cc: int, color_name: str):
        if not self.out: return
        domain = self.cc_map.get(cc, {})
        velocity = self._resolve_color_value(domain, color_name)
        self.out.send(mido.Message('control_change', control=cc, value=velocity))
