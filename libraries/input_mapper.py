# libraries/input_mapper.py

from typing import Dict, Tuple, Any, List
from .callbacks import CallbackRegistry
from .devices import DeviceEvent

class InputMapper:
    """
    Map normalized DeviceEvent -> callbacks.

    Bindings (examples):
      - device: "apc40"
        control: ["note", 48, 1]      # note 48 on MIDI channel 2 (mido channel = 1)
        action: "toggle_effects"
        deck: "stage"
        edge: "press"

      - device: "apc40"
        control: ["note", 57, 1]
        action: "set_fill"
        deck: "stage"
        fixed_value: 0.0               # use exact value (no scaling), e.g., 0%, 25%, ...

      - device: "joystick"
        control: "axis_2"
        action: "set_fill"
        deck: "stage"
        value_scale: [0.0, 1.0]        # optional clamp after normalization

    Notes:
      • Button-ish controls (notes, buttons, hats) use edge detection: press | release | both
      • Continuous controls (axes, CC) fire each change
      • MIDI channel matching is supported when control is ["note"|"cc", number, channel]
      • set_fill supports either fixed_value or scaled value from the event
    """

    def __init__(self, callbacks: CallbackRegistry, bindings: List[dict]):
        self.callbacks = callbacks
        self.bindings = bindings or []
        # For edge detection
        self._last_values: Dict[Tuple[str, Any], float] = {}

    # ---------- matching helpers ----------

    def _match_control(self, control: Any, pattern: Any) -> bool:
        """
        control and pattern can be:
          - exact strings (e.g., "button_0", "axis_2", "hat_0_x")
          - tuples/lists for MIDI  ("note", num[, channel]) or ("cc", num[, channel])
        """
        # string exact match
        if isinstance(pattern, str):
            return control == pattern

        # tuple/list MIDI pattern
        if isinstance(pattern, (list, tuple)) and isinstance(control, (list, tuple)):
            pc = tuple(pattern)
            cc = tuple(control)
            # must share kind + number
            if len(pc) >= 2 and len(cc) >= 2 and pc[0] == cc[0] and pc[1] == cc[1]:
                # if pattern specifies a channel, require an exact match
                if len(pc) >= 3:
                    return len(cc) >= 3 and pc[2] == cc[2]
                return True
        return False

    def _scale_to_01(self, control: Any, value: float, value_scale=None) -> float:
        """
        Normalize continuous sources:
          - joystick axis: [-1..1] -> [0..1]
          - MIDI CC: [0..127] -> [0..1]
        Then apply optional clamp/rescale via value_scale [lo, hi] in the normalized domain.
        """
        v = float(value)

        # Joystick axis
        if isinstance(control, str) and control.startswith("axis_"):
            v = (v + 1.0) * 0.5

        # MIDI CC
        if isinstance(control, tuple) and len(control) >= 1 and control[0] == "cc":
            v = v / 127.0

        # Optional clamp/rescale
        if value_scale and isinstance(value_scale, (list, tuple)) and len(value_scale) == 2:
            lo, hi = float(value_scale[0]), float(value_scale[1])
            v = max(lo, min(hi, v))
            rng = (hi - lo) or 1.0
            v = (v - lo) / rng

        # Finally clamp to [0,1]
        if v < 0.0: v = 0.0
        if v > 1.0: v = 1.0
        return v

    def _is_buttonish(self, control: Any) -> bool:
        """Return True for digital controls that should use edge detection."""
        if isinstance(control, str):
            return control.startswith("button_") or control.startswith("hat_")
        if isinstance(control, tuple):
            return len(control) >= 1 and control[0] == "note"
        return False

    # ---------- main entry ----------

    async def handle_event(self, ev: DeviceEvent):
        """
        Consume a DeviceEvent and trigger matching bindings.
        DeviceEvent fields:
          ev.device  -> "apc40" | "launchpad" | "joystick" | ...
          ev.control -> "button_0" | "axis_2" | ("note", 48, 1) | ("cc", 21, 1) | ...
          ev.value   -> numeric (velocity, cc value, axis float, etc.)
        """
        key = (ev.device, ev.control)
        last = self._last_values.get(key, 0)
        self._last_values[key] = ev.value

        for rule in self.bindings:
            if rule.get("device") != ev.device:
                continue
            if not self._match_control(ev.control, rule.get("control")):
                continue

            action = rule.get("action")
            deck   = rule.get("deck")  # may be None for global actions
            edge   = rule.get("edge", "both")

            cb = self.callbacks.get(action)
            if not cb:
                continue

            # Edge detection for digital; continuous always fires
            fired = False
            if self._is_buttonish(ev.control):
                rising  = (last == 0) and (ev.value != 0)
                falling = (last != 0) and (ev.value == 0)
                if edge == "press"   and rising:            fired = True
                elif edge == "release" and falling:         fired = True
                elif edge == "both" and (rising or falling): fired = True
            else:
                fired = True

            if not fired:
                continue

            # Callbacks:
            #  - set_fill: supports "fixed_value" or scaled value
            #  - deck-specific toggles: pass deck
            #  - global actions: no deck
            if action == "set_fill":
                if "fixed_value" in rule:
                    v = float(rule["fixed_value"])
                else:
                    v = self._scale_to_01(ev.control, ev.value, rule.get("value_scale"))
                if deck is not None:
                    cb(deck, v)         # callbacks.set_fill(deck, fixed_value)
                else:
                    # If a global fill is ever desired (unlikely), call without deck
                    cb(v)
            else:
                if deck is not None:
                    cb(deck)           # e.g., toggle_effects(deck)
                else:
                    cb()               # e.g., stop_all_decks(), tempo_tap(), etc.
