# libraries/input_mapper.py
import inspect
import logging
from typing import Dict, Tuple, Any, List
from .callbacks import CallbackRegistry
from .devices import DeviceEvent

class InputMapper:
    """
    Map normalized DeviceEvent -> callbacks.

    Bindings (examples):
      - device: "apc40"
        control: ["note", 48, 1]
        action: "toggle_effects"
        deck: "stage"
        edge: "press"

      - device: "apc40"
        control: ["cc", 7, 4]
        action: "set_opacity"
        deck: "merkaba"

      - device: "apc40"
        control: ["note", 99, 0]
        action: "tempo_tap"         # GLOBAL (no deck arg)
        # no 'deck' key here

    Notes:
      • Button-ish controls (notes, buttons, hats) use edge detection: press | release
      • Continuous controls (axes, CC) fire each change
      • MIDI channel matching is supported when control is ["note"|"cc", number, channel]
      • set_* actions pass values; global actions without 'deck' pass no deck param
    """

    def __init__(self, callbacks: CallbackRegistry, bindings: List[dict]):
        self.callbacks = callbacks
        self.bindings = bindings or []
        self._last_values: Dict[Tuple[str, Any], float] = {}

    # ---------- matching helpers ----------

    def _match_control(self, control: Any, pattern: Any) -> bool:
        if isinstance(pattern, str):
            return control == pattern

        if isinstance(pattern, (list, tuple)) and isinstance(control, (list, tuple)):
            pc = tuple(pattern)
            cc = tuple(control)
            if len(pc) >= 2 and len(cc) >= 2 and pc[0] == cc[0] and pc[1] == cc[1]:
                if len(pc) >= 3:
                    return len(cc) >= 3 and pc[2] == cc[2]
                return True
        return False

    def _scale_to_01(self, control: Any, value: float, value_scale=None) -> float:
        v = float(value)

        if isinstance(control, str) and control.startswith("axis_"):
            v = (v + 1.0) * 0.5

        if isinstance(control, tuple) and len(control) >= 1 and control[0] == "cc":
            v = v / 127.0

        if value_scale and isinstance(value_scale, (list, tuple)) and len(value_scale) == 2:
            lo, hi = float(value_scale[0]), float(value_scale[1])
            v = max(lo, min(hi, v))
            rng = (hi - lo) or 1.0
            v = (v - lo) / rng

        if v < 0.0: v = 0.0
        if v > 1.0: v = 1.0
        return v

    def _is_buttonish(self, control: Any) -> bool:
        if isinstance(control, str):
            return control.startswith("button_") or control.startswith("hat_")
        if isinstance(control, tuple):
            return len(control) >= 1 and control[0] == "note"
        return False

    def _call_cb(self, cb, deck, needs_value, value):
        """
        Flexible callback invocation:
          - if no deck in rule: call cb() or cb(value)
          - if deck set: call cb(deck) or cb(deck, value)
        """
        if deck is None:
            if needs_value:
                return cb(value)
            return cb()
        else:
            if needs_value:
                return cb(deck, value)
            return cb(deck)

    # ---------- main entry ----------

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
            deck   = rule.get("deck")  # may be None for global actions
            edge   = rule.get("edge")  # "press" | "release" | None

            cb = self.callbacks.get(action)
            if not cb:
                logging.warning("[mapper] action '%s' not found for %s", action, ev.control)
                continue

            is_cc   = isinstance(ev.control, tuple) and len(ev.control) >= 1 and ev.control[0] == "cc"
            is_axis = isinstance(ev.control, str) and ev.control.startswith("axis_")
            pass_value_flag = bool(rule.get("pass_value", False))
            needs_value = is_cc or is_axis or action.startswith("set_") or pass_value_flag

            # Edge gating for discrete (button/note/hat) only
            if not needs_value and self._is_buttonish(ev.control) and edge:
                is_press = False
                is_release = False

                if isinstance(ev.control, tuple) and ev.control[0] == "note":
                    is_press   = (ev.value and ev.value > 0)
                    is_release = (not ev.value) or (ev.value == 0)
                elif isinstance(ev.control, str) and ev.control.startswith("button_"):
                    is_press   = (ev.value == 1)
                    is_release = (ev.value == 0)
                elif isinstance(ev.control, str) and ev.control.startswith("hat_"):
                    is_press   = bool(ev.value)
                    is_release = not bool(ev.value)

                if (edge == "press" and not is_press) or (edge == "release" and not is_release):
                    continue  # ignore due to edge gating

            # Value normalization (only used if needs_value)
            val = ev.value
            if needs_value:
                val = self._scale_to_01(ev.control, ev.value, rule.get("value_scale"))

            # Invoke callback with appropriate args
            try:
                res = self._call_cb(cb, deck, needs_value, val)
                if inspect.isawaitable(res):
                    await res
            except TypeError as te:
                logging.exception("[mapper] bad callback signature for action '%s': %s", action, te)
            except Exception:
                logging.exception("[mapper] error running action '%s'", action)
