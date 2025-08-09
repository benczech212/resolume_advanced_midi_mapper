import mido
from typing import Optional
from .led_mapper import LEDMapper

class MidiBus:
    def __init__(self, out_match: str, mapping: dict, device_kind: str):
        self.out = self._open_output_matching(out_match)
        self.mapper = LEDMapper(self.out, mapping, device_kind)
        self.device_kind = device_kind

    def _open_output_matching(self, substr: str) -> Optional[mido.ports.BaseOutput]:
        try:
            for name in mido.get_output_names():
                if substr.lower() in name.lower():
                    return mido.open_output(name)
        except Exception:
            pass
        return None
