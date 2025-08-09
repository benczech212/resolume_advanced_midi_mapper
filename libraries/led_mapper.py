import mido
from typing import Optional, Dict

class LEDMapper:
    """
    Device-agnostic LED API using per-device YAML mappings.

    YAML shape:
      device: launchpad|apc40
      defaults:
        colors: { off: 0, green: 60, ... }  # launchpad-style numeric velocities; APC may be filled by velocity_map
      velocity_map:                         # APC-only convenience (can be overridden per file)
        "6 color": { off: 0, green: 1, ... }
        "2 color": { off: 0, green: 1, green blink: 2 }
        "1 color": { off: 0, green: 1 }
      notes:
        "NN":
          led_type: "6 color"|"2 color"|"1 color"   # APC-only
          colors: { off: 0, green: 1, ... }         # optional overrides
      ccs:
        "CC": { colors: {...} }

    Public API:
      set_note_color(note, "green")
      set_note_onoff(note, True|False)
      set_cc_color(cc, "green")
    """
    def __init__(self, outport: Optional[mido.ports.BaseOutput], mapping: dict, device_kind: str):
        self.out = outport
        self.mapping = mapping or {}
        self.device_kind = device_kind

        self.defaults = self.mapping.get("defaults", {}) or {}
        self.note_map = {int(k): v for k, v in (self.mapping.get("notes") or {}).items()}
        self.cc_map = {int(k): v for k, v in (self.mapping.get("ccs") or {}).items()}
        # APC velocity map (per LED type) is configurable in YAML; provide a sane fallback
        self.velocity_map = self.mapping.get("velocity_map", {}) or {
            "6 color": { "off": 0, "green": 1, "green blink": 2, "red": 3, "red blink": 4, "yellow": 5, "yellow blink": 6 },
            "2 color": { "off": 0, "green": 1, "green blink": 2 },
            "1 color": { "off": 0, "green": 1 },
        }

    # --- Launchpad helper (unchanged) ---
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

    # --- Color resolution ---
    def _resolve_color_value_generic(self, domain: dict, color_name: str) -> int:
        """
        For Launchpad (or generic numeric devices): look up numeric velocity directly
        using per-note overrides, then defaults.
        """
        colors = (domain or {}).get("colors", {}) or {}
        if color_name in colors:
            return int(colors[color_name])
        dev_colors = (self.defaults or {}).get("colors", {}) or {}
        if color_name in dev_colors:
            return int(dev_colors[color_name])
        # simple on/off fallback
        if color_name == "on" and "green" in dev_colors:
            return int(dev_colors["green"])
        return int(dev_colors.get("off", 0))

    def _resolve_color_value_apc(self, note: int, color_name: str) -> int:
        """
        APC-specific: respect the note's led_type and translate color_name -> velocity.
        Falls back to per-note numeric 'colors' or device defaults when needed.
        """
        domain = self.note_map.get(note, {}) or {}
        led_type = (domain.get("led_type") or "").strip().lower()
        # Normalize color aliases
        cname = color_name.strip().lower()

        # APC: treat "on" as "green" by default
        if cname == "on":
            cname = "green"

        # If this note declares an LED type and the velocity_map has it:
        if led_type and led_type in self.velocity_map and cname in self.velocity_map[led_type]:
            return int(self.velocity_map[led_type][cname])

        # Else try per-note explicit numeric colors override
        colors = (domain.get("colors") or {})
        if cname in colors:
            return int(colors[cname])

        # Else try device defaults (may contain on/off/green numeric)
        dev_colors = (self.defaults or {}).get("colors", {}) or {}
        if cname in dev_colors:
            return int(dev_colors[cname])

        # Final fallback: off
        return int(dev_colors.get("off", 0))

    # --- Public ops ---
    def set_note_color(self, note: int, color_name: str):
        if not self.out:
            return
        if self.device_kind == "apc40":
            velocity = self._resolve_color_value_apc(note, color_name)
            self.out.send(mido.Message('note_on', note=note, velocity=velocity))
        else:
            # generic/launchpad path
            domain = self.note_map.get(note, {})
            velocity = self._resolve_color_value_generic(domain, color_name)
            self.out.send(mido.Message('note_on', note=note, velocity=velocity))

    def set_note_onoff(self, note: int, on: bool):
        # Map to "on"/"off" which will resolve appropriately (APC -> green/off)
        self.set_note_color(note, "on" if on else "off")

    def set_cc_color(self, cc: int, color_name: str):
        if not self.out:
            return
        domain = self.cc_map.get(cc, {})
        velocity = self._resolve_color_value_generic(domain, color_name)
        self.out.send(mido.Message('control_change', control=cc, value=velocity))
