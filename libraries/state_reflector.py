import asyncio
from typing import Dict
from .deck_model import DeckManager
from .osc_bus import OSCBus
from .led_mapper import LEDMapper

class StateReflector:
    """
    Periodically pushes deck state to Resolume via OSC
    and updates MIDI LEDs according to simple policy.
    """
    def __init__(self, deck_mgr: DeckManager, oscbus: OSCBus,
                 lp_leds: LEDMapper = None, apc_leds: LEDMapper = None,
                 hz: float = 30.0):
        self.deck_mgr = deck_mgr
        self.osc = oscbus
        self.lp_leds = lp_leds
        self.apc_leds = apc_leds
        self.period = 1.0 / hz
        self.lp_note_map: Dict[str, int] = {}
        self.apc_note_map: Dict[str, int] = {}

    async def run(self):
        while True:
            for deck in self.deck_mgr.all_decks():
                self.osc.send_play(deck.name, deck.playing)
                self.osc.send_effects_toggle(deck.name, deck.effects)
                self.osc.send_colors_toggle(deck.name, deck.colors)
                self.osc.send_fill(deck.name, deck.fill)

                lp_note = self.lp_note_map.get(deck.name)
                if lp_note is not None and self.lp_leds:
                    color = "off"
                    if deck.playing: color = "green"
                    if deck.effects: color = "yellow"
                    if deck.colors:  color = "red"
                    self.lp_leds.set_note_color(lp_note, color)

                apc_note = self.apc_note_map.get(deck.name)
                if apc_note is not None and self.apc_leds:
                    self.apc_leds.set_note_onoff(apc_note, deck.playing)

            await asyncio.sleep(self.period)
