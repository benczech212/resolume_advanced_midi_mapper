from typing import Dict, Tuple, Any, List
from .callbacks import CallbackRegistry
from .devices import DeviceEvent

class InputMapper:
    """
    Bind DeviceEvent -> callback(deck, [value])
    Supports edge detection for digital and continuous for axes/CC.
    """
    def __init__(self, callbacks: CallbackRegistry, bindings: List[dict]):
        self.callbacks = callbacks
        self.bindings = bindings
        self._last_values: Dict[Tuple[str, Any], float] = {}

    def _match_control(self, control, pattern) -> bool:
        return control == pattern

    def _scale_to_01(self, control: Any, value: float, value_scale=None) -> float:
        if isinstance(control, str) and control.startswith("axis_"):
            value = (float(value) + 1.0) * 0.5  # [-1..1] -> [0..1]
        if isinstance(control, tuple) and control[0] == "cc":
            value = float(value) / 127.0        # 0..127  -> [0..1]
        if value_scale and isinstance(value_scale, (list, tuple)) and len(value_scale) == 2:
            lo, hi = float(value_scale[0]), float(value_scale[1])
            value = max(lo, min(hi, value))
            rng = (hi - lo) or 1.0
            value = (value - lo) / rng
        return value

    async def handle_event(self, ev: DeviceEvent):
        key = (ev.device, ev.control)
        last = self._last_values.get(key, 0)
        self._last_values[key] = ev.value

        for rule in self.bindings:
            if rule.get("device") != ev.device:
                continue
            if not self._match_control(ev.control, rule.get("control")):
                continue
            action = rule.get("action")
            deck_name = rule.get("deck")
            cb = self.callbacks.get(action)
            if not cb or not deck_name:
                continue

            edge = rule.get("edge", "both")
            fired = False

            # Digital edges (buttons, hats, notes)
            is_buttonish = isinstance(ev.control, str) and (ev.control.startswith("button_") or ev.control.startswith("hat_"))
            is_note = isinstance(ev.control, tuple) and ev.control[0] == "note"

            if is_buttonish or is_note:
                rising = (last == 0) and (ev.value != 0)
                falling = (last != 0) and (ev.value == 0)
                if edge == "press" and rising: fired = True
                elif edge == "release" and falling: fired = True
                elif edge == "both" and (rising or falling): fired = True
            else:
                # Continuous (axis/cc)
                fired = True

            if not fired:
                continue

            if action == "set_fill":
                v = self._scale_to_01(ev.control, ev.value, rule.get("value_scale"))
                cb(deck_name, v)
            else:
                cb(deck_name)
