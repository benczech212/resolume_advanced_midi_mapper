# libraries/binding_templates.py
from typing import Dict, List, Any, Iterable, Tuple, Union
import copy

def _human_to_mido_channel(human_ch: int) -> int:
    """Convert human channel 1..16 to mido 0..15. Clamp for safety."""
    return max(0, min(15, int(human_ch) - 1))

def _iter_device_decks(dev_key: str, dev_cfg: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any], int, str]]:
    """
    Yield (device_key, device_cfg, mido_channel, deck_name) for each channel_to_deck pair.
    If a device doesn't have channel_to_deck, yield nothing for per_deck expansion.
    """
    c2d = (dev_cfg or {}).get("channel_to_deck") or {}
    for human_ch, deck_name in c2d.items():
        yield dev_key, dev_cfg, _human_to_mido_channel(human_ch), str(deck_name)

def _render_placeholders(obj: Any, channel: Union[int, None], deck: Union[str, None]) -> Any:
    """
    Recursively replace "{channel}" and "{deck}" placeholders in lists/tuples/dicts/strings.
    For control tuples with channel placeholder, ensure the substituted channel is an int.
    """
    if isinstance(obj, str):
        if obj == "{deck}":
            return deck
        if obj == "{channel}":
            return channel
        # allow inline e.g., "deck:{deck}" if ever needed
        return obj.replace("{deck}", deck or "").replace("{channel}", str(channel) if channel is not None else "")
    elif isinstance(obj, list):
        return [_render_placeholders(x, channel, deck) for x in obj]
    elif isinstance(obj, tuple):
        return tuple(_render_placeholders(list(obj), channel, deck))
    elif isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            new[_render_placeholders(k, channel, deck)] = _render_placeholders(v, channel, deck)
        return new
    else:
        return obj

def expand_templates(cfg: Dict[str, Any]) -> List[dict]:
    """
    Expand config templates into concrete InputMapper bindings.
    - devices: { device_key: { kind, in_match, out_match, channel_to_deck? } }
    - templates.per_deck: [ { device: <key>, rules: [binding-like dicts with placeholders] } ]
    - templates.global:   [ binding-like dicts (no placeholders required) ]

    Returns a flat list of binding dicts.
    """
    out: List[dict] = []

    devices = cfg.get("devices", {}) or {}
    templates = cfg.get("templates", {}) or {}
    per_deck = templates.get("per_deck", []) or []
    global_rules = templates.get("global", []) or []

    # 1) Expand per-deck templates across channel_to_deck for the specified device
    for block in per_deck:
        dev_key = block.get("device")
        rules = block.get("rules", []) or []
        if not dev_key or dev_key not in devices:
            continue
        for _dev_key, dev_cfg, mido_ch, deck_name in _iter_device_decks(dev_key, devices[dev_key]):
            for rule in rules:
                r = copy.deepcopy(rule)
                # Ensure device is set on each rule (used by InputMapper)
                r["device"] = dev_key
                # Replace placeholders in control/deck/any nested field
                r = _render_placeholders(r, mido_ch, deck_name)
                out.append(r)

    # 2) Add global rules as-is (but ensure they have a device field)
    for rule in global_rules:
        r = copy.deepcopy(rule)
        if "device" not in r:
            # Optional: allow a default device—better to be explicit in config
            pass
        out.append(r)

    # 3) Merge with classic 'bindings' section if present (user overrides)
    static_bindings = cfg.get("bindings", []) or []
    out.extend(static_bindings)

    return out
