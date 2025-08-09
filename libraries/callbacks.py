# libraries/callbacks.py

import logging

class CallbackRegistry:
    def __init__(self, deck_mgr, osc):
        """
        deck_mgr: instance of DeckManager that manages deck state
        osc: instance of OSCBus for sending OSC messages to Resolume
        """
        self.deck_mgr = deck_mgr
        self.osc = osc

        # Map action name -> function
        self.callbacks = {
            # Deck-specific actions
            "toggle_effects": self.toggle_effects,
            "toggle_colors": self.toggle_colors,
            "toggle_transform": self.toggle_transform,
            "set_fill": self.set_fill,
            "stop_deck": self.stop_deck,
            "random_fills": self.random_fills,

            # Global APC actions
            "stop_all_decks": self.stop_all_decks,
            "start_autopilot": self.start_autopilot,
            "stop_autopilot": self.stop_autopilot,
            "toggle_record": self.toggle_record,
            "tempo_tap": self.tempo_tap,
            "nudge_minus": self.nudge_minus,
            "nudge_plus": self.nudge_plus,
            "bpm_resync": self.bpm_resync,
            "toggle_metronome": self.toggle_metronome,
        }

    def get(self, action_name):
        """Return the callback function for the given action name."""
        return self.callbacks.get(action_name)

    # === Deck-specific callbacks ===

    def toggle_effects(self, deck):
        d = self.deck_mgr.get(deck)
        if not d:
            logging.warning(f"Deck '{deck}' not found for toggle_effects")
            return
        d.effects = not d.effects
        logging.info(f"[{deck}] Effects -> {d.effects}")
        self._send_deck_state(deck)

    def toggle_colors(self, deck):
        d = self.deck_mgr.get(deck)
        if not d:
            logging.warning(f"Deck '{deck}' not found for toggle_colors")
            return
        d.colors = not d.colors
        logging.info(f"[{deck}] Colors -> {d.colors}")
        self._send_deck_state(deck)

    def toggle_transform(self, deck):
        d = self.deck_mgr.get(deck)
        if not d:
            logging.warning(f"Deck '{deck}' not found for toggle_transform")
            return
        d.transform = not d.transform
        logging.info(f"[{deck}] Transform -> {d.transform}")
        self._send_deck_state(deck)

    def set_fill(self, deck, fixed_value):
        d = self.deck_mgr.get(deck)
        if not d:
            logging.warning(f"Deck '{deck}' not found for set_fill")
            return
        d.fill = fixed_value
        logging.info(f"[{deck}] Fill -> {d.fill}")
        self._send_deck_state(deck)

    def stop_deck(self, deck):
        d = self.deck_mgr.get(deck)
        if not d:
            logging.warning(f"Deck '{deck}' not found for stop_deck")
            return
        d.playing = False
        logging.info(f"[{deck}] STOPPED")
        self._send_deck_state(deck)

    def random_fills(self, deck):
        import random
        d = self.deck_mgr.get(deck)
        if not d:
            logging.warning(f"Deck '{deck}' not found for random_fills")
            return
        d.fill = random.choice([0.0, 0.25, 0.5, 0.75, 1.0])
        logging.info(f"[{deck}] Random Fill -> {d.fill}")
        self._send_deck_state(deck)

    # === Global APC actions ===

    def stop_all_decks(self):
        logging.info("Stopping all decks")
        for d in self.deck_mgr.all_decks():
            d.playing = False
            self._send_deck_state(d.name)
        self.osc.client.send_message("/czechb/control/stop_all_decks", 1)

    def start_autopilot(self):
        logging.info("Autopilot START")
        self.osc.client.send_message("/czechb/control/autopilot/start", 1)

    def stop_autopilot(self):
        logging.info("Autopilot STOP")
        self.osc.client.send_message("/czechb/control/autopilot/stop", 1)

    def toggle_record(self):
        logging.info("Record TOGGLE")
        self.osc.client.send_message("/czechb/control/record/toggle", 1)

    def tempo_tap(self):
        logging.info("Tempo TAP")
        self.osc.client.send_message("/czechb/control/tempo/tap", 1)

    def nudge_minus(self):
        logging.info("Tempo NUDGE-")
        self.osc.client.send_message("/czechb/control/tempo/nudge_minus", 1)

    def nudge_plus(self):
        logging.info("Tempo NUDGE+")
        self.osc.client.send_message("/czechb/control/tempo/nudge_plus", 1)

    def bpm_resync(self):
        logging.info("BPM RESYNC")
        self.osc.client.send_message("/czechb/control/tempo/resync", 1)

    def toggle_metronome(self):
        logging.info("Metronome TOGGLE")
        self.osc.client.send_message("/czechb/control/metronome/toggle", 1)

    # === Internal ===

    def _send_deck_state(self, deck):
        """Push the current state of a deck to Resolume via OSC."""
        d = self.deck_mgr.get(deck)
        if not d:
            return
        # Example OSC paths — adjust to match your Resolume OSC map
        self.osc.client.send_message(f"/deck/{deck}/effects", int(d.effects))
        self.osc.client.send_message(f"/deck/{deck}/colors", int(d.colors))
        self.osc.client.send_message(f"/deck/{deck}/transform", int(d.transform))
        self.osc.client.send_message(f"/deck/{deck}/fill", float(d.fill))
