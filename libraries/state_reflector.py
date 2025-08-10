# libraries/state_reflector.py
import asyncio
import logging
import time
from typing import Dict, Optional

from .deck_model import DeckManager, DeckState
from .midi_bus import MidiBus

logger = logging.getLogger(__name__)

# APC velocity map (we're doing our own blink by toggling on/off)
APC_VEL = {
    "off": 0,
    "green": 1,
    "red": 3,
    "yellow": 5,
}

# Button notes
NEXT_CLIP_NOTE = 57            # function button
STOP_NOTE      = 52            # stop deck (2-color on APC; we'll blink green when playing)
FILL_GREEN_NOTES = [56, 55, 54, 53]  # green stack for 25/50/75/100

class StateReflector:
    """
    APC fills (56..53):
      0%  -> no green
      25% -> 56 green
      50% -> 56,55 green
      75% -> 56,55,54 green
      100%-> 56,55,54,53 green

    Note 57 ('Next Clip'):
      • SOLID GREEN when playing
      • BLINK (YELLOW/OFF) when NOT playing

    Note 52 ('Stop'):
      • BLINK (GREEN/OFF) when playing
      • OFF when NOT playing

    Blinks are slightly phase-shifted per channel so they "ripple" gently.
    """

    def __init__(
        self,
        deck_mgr: DeckManager,
        osc_bus,
        *,
        hz: float = 30.0,
        apc_bus: Optional[MidiBus] = None,
        deck_to_channel: Optional[Dict[str, int]] = None,
        blink_hz: float = 2.0,
        blink_phase_per_channel_sec: float = -0.06,  # slight offset per channel
    ):
        self.deck_mgr = deck_mgr
        self.osc = osc_bus
        self.hz = max(1.0, float(hz))
        self.apc_bus = apc_bus
        self.deck_to_channel: Dict[str, int] = deck_to_channel or {}
        self.channel_to_deck: Dict[int, str] = {ch: name for name, ch in self.deck_to_channel.items()}

        self.blink_hz = max(0.1, float(blink_hz))
        self.blink_phase_per_channel_sec = float(blink_phase_per_channel_sec)

        # cache last "signature" per deck to avoid redundant traffic
        self._last_apc_sig: Dict[str, str] = {}
        self._warned_no_apc = False

    async def run(self):
        interval = 1.0 / self.hz
        logger.info(
            "StateReflector running at %.1f Hz (blink_hz=%.2f, phase_per_ch=%.3fs)",
            self.hz, self.blink_hz, self.blink_phase_per_channel_sec
        )
        while True:
            try:
                self._tick()
            except Exception:
                logger.exception("StateReflector tick failure")
            await asyncio.sleep(interval)

    # -------- public refresh helpers --------

    def refresh_deck(self, deck_name: str):
        if not deck_name:
            return
        d = self.deck_mgr.get_deck(deck_name)
        if not d:
            return
        self._last_apc_sig.pop(deck_name, None)
        self._reflect_apc_leds(d, force=True)

    def refresh_deck_by_channel(self, ch: int):
        name = self.channel_to_deck.get(int(ch))
        if name:
            self.refresh_deck(name)

    # -------- internal --------

    def _tick(self):
        for d in self.deck_mgr.all_decks():
            self._reflect_apc_leds(d)

    def _blink_on(self, ch: int, duty: float = 0.5) -> bool:
        """Square-wave blink with per-channel phase offset."""
        period = 1.0 / self.blink_hz
        t = (time.monotonic() + ch * self.blink_phase_per_channel_sec) % period
        return t < (period * duty)

    def _reflect_apc_leds(self, deck: DeckState, force: bool = False):
        if not self.apc_bus:
            if not self._warned_no_apc:
                logger.debug("[reflector] APC bus not available; skipping LED reflection")
                self._warned_no_apc = True
            return

        ch = self.deck_to_channel.get(deck.name)
        if ch is None:
            return

        # Greens from fill 0..1 -> 0..4
        greens_count = int(round(max(0.0, min(1.0, float(deck.fill))) * 4.0))
        greens_count = max(0, min(4, greens_count))

        # 57: solid GREEN if playing; blink YELLOW when not playing
        if deck.playing:
            note57_vel = APC_VEL["yellow"]
            blink_flag_57 = 0
        else:
            note57_vel = APC_VEL["red"]
            blink_flag_57 = 0

        # 52: blink GREEN when playing; off when not
        if deck.playing:
            blink_on_52 = self._blink_on(ch)  # same phase offset as 57 for subtle sync
            note52_vel = APC_VEL["green"] if blink_on_52 else APC_VEL["off"]
            blink_flag_52 = int(blink_on_52)
        else:
            note52_vel = APC_VEL["off"]
            blink_flag_52 = 0

        sig = f"ch{ch}|57:{note57_vel}|52:{note52_vel}|greens:{greens_count}|b57:{blink_flag_57}|b52:{blink_flag_52}"
        if not force and self._last_apc_sig.get(deck.name) == sig:
            return  # unchanged

        # Render 57
        try:
            self.apc_bus.note_on(NEXT_CLIP_NOTE, note57_vel, channel=ch)
        except Exception:
            logger.exception("[reflector] failed to set note 57 for deck=%s ch=%s", deck.name, ch)

        # Render 52
        try:
            self.apc_bus.note_on(STOP_NOTE, note52_vel, channel=ch)
        except Exception:
            logger.exception("[reflector] failed to set note 52 for deck=%s ch=%s", deck.name, ch)

        # Fill greens + offs
        for i, note in enumerate(FILL_GREEN_NOTES):
            try:
                vel = APC_VEL["green"] if i < greens_count else APC_VEL["off"]
                self.apc_bus.note_on(note, vel, channel=ch)
            except Exception:
                logger.exception("[reflector] failed to set fill note=%s deck=%s ch=%s", note, deck.name, ch)

        self._last_apc_sig[deck.name] = sig


def build_deck_to_channel_from_cfg(cfg: dict) -> Dict[str, int]:
    out: Dict[str, int] = {}
    try:
        ch2d = (cfg.get("devices", {}) or {}).get("apc40", {}) or {}
        ch2d = ch2d.get("channel_to_deck", {}) or {}
        for hk, deck in ch2d.items():
            try:
                human_ch = int(hk)
            except Exception:
                continue
            mido_ch = max(0, min(15, human_ch - 1))
            if isinstance(deck, str) and deck:
                out[deck] = mido_ch
    except Exception:
        logger.exception("Failed to build deck_to_channel from cfg")
    return out
