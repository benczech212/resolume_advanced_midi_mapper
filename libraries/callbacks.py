import math
import time
from typing import Dict, Callable, Optional
from .deck_model import DeckManager

class CallbackRegistry:
    def __init__(self, deck_mgr: DeckManager, oscbus):
        self.deck_mgr = deck_mgr
        self.osc = oscbus
        self.callbacks: Dict[str, Callable[..., None]] = {
            "toggle_effects": self.toggle_effects,
            "toggle_colors": self.toggle_colors,
            "toggle_playing": self.toggle_playing,
            "set_fill": self.set_fill,
            "stop_deck": self.stop_deck,
            "random_fills": self.random_fills,
        }

    def get(self, name: str) -> Optional[Callable[..., None]]:
        return self.callbacks.get(name)

    def toggle_effects(self, deck_name: str):
        d = self.deck_mgr.get_deck(deck_name)
        if d: d.set_effects(not d.effects)

    def toggle_colors(self, deck_name: str):
        d = self.deck_mgr.get_deck(deck_name)
        if d: d.set_colors(not d.colors)

    def toggle_playing(self, deck_name: str):
        d = self.deck_mgr.get_deck(deck_name)
        if d: d.set_playing(not d.playing)

    def set_fill(self, deck_name: str, value: float):
        d = self.deck_mgr.get_deck(deck_name)
        if d: d.set_fill(value)

    def stop_deck(self, deck_name: str):
        d = self.deck_mgr.get_deck(deck_name)
        if d: d.set_playing(False)  # keep fill as-is per spec

    def random_fills(self, deck_name: str):
        d = self.deck_mgr.get_deck(deck_name)
        if d:
            t = time.time()
            v = 0.5 + 0.5 * math.sin(t * 2.0)
            d.set_fill(v)
