# libraries/callbacks.py
import logging
import random
import asyncio

class CallbackRegistry:
    def __init__(self, deck_mgr, osc):
        """
        deck_mgr: DeckManager (groups/layers + deck states)
        osc: OSCBus (has .client.send_message(path, value))
        """
        self.deck_mgr = deck_mgr
        self.osc = osc

        self.callbacks = {
            # Deck-specific actions
            "toggle_effects": self.toggle_effects,
            "toggle_colors": self.toggle_colors,
            "toggle_transform": self.toggle_transform,
            "set_fill": self.set_fill,
            "set_opacity": self.set_opacity,
            "stop_deck": self.stop_deck,
            "random_fills": self.random_fills,
            "next_clip": self.next_clip,
            "next_or_random": self.next_or_random,

            # Global APC actions (some are async pulses)
            "stop_all_decks": self.stop_all_decks,
            "start_autopilot": self.start_autopilot,
            "stop_autopilot": self.stop_autopilot,
            "toggle_record": self.toggle_record,
            "tempo_tap": self.tempo_tap,           # async pulse
            "nudge_minus": self.nudge_minus,
            "nudge_plus": self.nudge_plus,
            "bpm_resync": self.bpm_resync,         # async pulse
            "toggle_metronome": self.toggle_metronome,  # async pulse
        }

    def get(self, action_name):
        return self.callbacks.get(action_name)

    # -------------------------------------------------
    # Helpers for group/layer lookup + OSC fire
    # -------------------------------------------------
    def _groups_for_deck(self, deck_name: str):
        """Which Resolume group names map to this deck? (usually 1)"""
        return [g for g, d in self.deck_mgr.group_to_deck.items() if d == deck_name]

    def _layers_of_type_for_deck(self, deck_name: str, layer_type: str):
        """Return List[LayerInfo] for all groups of this deck with the given type."""
        lis = []
        for g in self._groups_for_deck(deck_name):
            lis.extend(self.deck_mgr.get_group_layers_by_type(g, layer_type))
        return lis

    def _all_layers_for_deck(self, deck_name: str):
        """
        Return ALL layers (any type) that belong to the group(s) mapped to this deck.
        """
        layers = []
        for g in self._groups_for_deck(deck_name):
            gi = self.deck_mgr.groups_by_name.get(g)
            if gi:
                layers.extend(gi.layers.values())
        return layers

    def _fire_for_layer_type(self, deck_name: str, layer_type: str, enabled: bool):
        """
        When enabled: pick a RANDOM column from each layer_type's discovered clips.
        When disabled: pick the layer's stop_clip if present, else 1.
        """
        layers = self._layers_of_type_for_deck(deck_name, layer_type)
        if not layers:
            logging.info("[callbacks] toggle_%s: no %s layers for deck '%s'",
                         layer_type, layer_type, deck_name)
            return

        for li in layers:
            clips = getattr(li, "clips", []) or []
            stop_col = getattr(li, "stop_clip", None)

            if enabled:
                column = random.choice(clips) if clips else random.randint(2, 10)
            else:
                if stop_col is None:
                    logging.warning("[callbacks] %s: layer %s has no stop_clip; using 1", layer_type, li.index)
                column = stop_col if (stop_col is not None) else 1

            path = f"/composition/layers/{li.index}/clips/{column}/connect"
            try:
                self.osc.client.send_message(path, 1)
                logging.debug("[callbacks] %s %s -> %s (layer %s, col %s)",
                              layer_type, "ON" if enabled else "OFF", path, li.index, column)
            except Exception:
                logging.exception("[callbacks] failed to send OSC: %s 1", path)

    def _fire_fills_for_deck(self, deck_name: str, fill_value: float):
        """
        Exclusive fill selection per percentage:

          0%:   send STOP CLIP to ALL fill layers (use each layer's stop_clip; if missing, fallback to 1)
          25%:  select ~25% (>=1) random layers → random clip; others → STOP CLIP
          50%:  select ~50% random layers → random clip; others → STOP CLIP
          75%:  select ~75% random layers → random clip; others → STOP CLIP
          100%: ALL fill layers → random clip

        Called only on discrete steps {0, .25, .5, .75, 1}.
        """
        layers = self._layers_of_type_for_deck(deck_name, "fills")
        n = len(layers)
        if n == 0:
            logging.info("[callbacks] set_fill: no fill layers for deck '%s'", deck_name)
            return

        f = max(0.0, min(1.0, float(fill_value)))

        def _stop_layer(li):
            stop_col = getattr(li, "stop_clip", None)
            if stop_col is None:
                logging.warning("[callbacks] fills: layer %s has no stop_clip; using 1", li.index)
            column = stop_col if (stop_col is not None) else 1
            path = f"/composition/layers/{li.index}/clips/{column}/connect"
            try:
                self.osc.client.send_message(path, 1)
            except Exception:
                logging.exception("[callbacks] fill stop failed: %s", path)

        if f == 0.0:
            for li in layers:
                _stop_layer(li)
            logging.debug("[callbacks] fill 0%% -> stop ALL (%d layers)", n)
            return

        ratio_map = {0.25: 0.25, 0.5: 0.50, 0.75: 0.75, 1.0: 1.0}
        ratio = ratio_map.get(f, None)
        if ratio is None:
            logging.debug("[callbacks] fill %.3f not a discrete step; ignoring clip fire", f)
            return

        if ratio >= 1.0:
            selected = list(layers)
        else:
            k = max(1, round(ratio * n))
            selected = random.sample(layers, k) if k < n else list(layers)

        selected_ids = {li.index for li in selected}

        for li in layers:
            if li.index in selected_ids:
                clips = getattr(li, "clips", []) or []
                column = random.choice(clips) if clips else random.randint(2, 10)
                path = f"/composition/layers/{li.index}/clips/{column}/connect"
                try:
                    self.osc.client.send_message(path, 1)
                except Exception:
                    logging.exception("[callbacks] fill fire failed: %s", path)
            else:
                _stop_layer(li)

        logging.debug("[callbacks] fill %.0f%% -> fired %d/%d layers (others stopped)",
                      f * 100.0, len(selected), n)

    def _connect_next_for_layers(self, layers, tag: str):
        """Send /composition/layers/{index}/connectnextclip 1 for each provided layer."""
        if not layers:
            logging.debug("[callbacks] next_clip: no %s layers to advance", tag)
            return
        for li in layers:
            path = f"/composition/layers/{li.index}/connectnextclip"
            try:
                self.osc.client.send_message(path, 1)
                logging.debug("[callbacks] next_clip -> %s (layer %s)", path, li.index)
            except Exception:
                logging.exception("[callbacks] next_clip failed: %s 1", path)

    # -------------------------------------------------
    # Deck-specific callbacks
    # -------------------------------------------------
    def toggle_effects(self, deck):
        d = self.deck_mgr.get_deck(deck)
        if not d:
            logging.warning(f"Deck '{deck}' not found for toggle_effects")
            return
        d.effects = not d.effects
        logging.info(f"[{deck}] Effects -> {d.effects}")
        self._fire_for_layer_type(deck, "effects", d.effects)
        self._send_deck_state(deck)

    def toggle_colors(self, deck):
        d = self.deck_mgr.get_deck(deck)
        if not d:
            logging.warning(f"Deck '{deck}' not found for toggle_colors")
            return
        d.colors = not d.colors
        logging.info(f"[{deck}] Colors -> {d.colors}")
        self._fire_for_layer_type(deck, "colors", d.colors)
        self._send_deck_state(deck)

    def toggle_transform(self, deck):
        d = self.deck_mgr.get_deck(deck)
        if not d:
            logging.warning(f"Deck '{deck}' not found for toggle_transform")
            return
        d.transform = not d.transform
        logging.info(f"[{deck}] Transform -> {d.transform}")
        self._fire_for_layer_type(deck, "transforms", d.transform)
        self._send_deck_state(deck)

    def set_fill(self, deck, value):
        d = self.deck_mgr.get_deck(deck)
        if not d:
            logging.warning(f"Deck '{deck}' not found for set_fill")
            return
        try:
            v = float(value)
        except (TypeError, ValueError):
            logging.warning("[callbacks] set_fill: non-numeric value=%r", value)
            return
        if v > 1.0:
            v = v / 127.0
        v = max(0.0, min(1.0, v))

        changed = False
        if abs(d.fill - v) > 1e-6:
            d.fill = v
            changed = True

        if not d.playing:
            d.playing = True
            changed = True

        DISCRETE = (0.0, 0.25, 0.5, 0.75, 1.0)
        is_step = any(abs(v - s) < 1e-4 for s in DISCRETE)
        if is_step:
            self._fire_fills_for_deck(deck, v)

        if changed:
            logging.info(f"[{deck}] Fill -> {d.fill:.3f} (playing={d.playing})")
            self._send_deck_state(deck)

    def set_opacity(self, deck: str, value):
        """
        Send group master to /composition/groups/{group_index}/master with float 0..1.
        """
        d = self.deck_mgr.get_deck(deck)
        if not d:
            logging.warning("[callbacks] set_opacity: deck '%s' not found", deck)
            return
        try:
            v = float(value)
        except (TypeError, ValueError):
            logging.warning("[callbacks] set_opacity: non-numeric value=%r", value)
            return
        if v > 1.0:
            v = v / 127.0
        v = max(0.0, min(1.0, v))

        # find group indices for this deck
        idxs = []
        for gname in self._groups_for_deck(deck):
            gi = self.deck_mgr.groups_by_name.get(gname)
            if gi:
                idxs.append(int(gi.index))
            else:
                logging.warning("[callbacks] opacity: group '%s' not in groups_by_name", gname)

        if not idxs:
            logging.warning("[callbacks] set_opacity: no groups mapped for deck '%s'", deck)

        for gi in idxs:
            path = f"/composition/groups/{gi}/master"
            try:
                self.osc.client.send_message(path, float(v))
                logging.debug("[callbacks] opacity -> %s %.3f", path, v)
            except Exception:
                logging.exception("[callbacks] failed to send OSC: %s %.3f", path, v)

        if d.opacity != v:
            d.opacity = v
            logging.info(f"[{deck}] Opacity -> {d.opacity:.3f}")
        self._send_deck_state(deck)

    def stop_deck(self, deck):
        """
        Stop the deck AND send the stop clip for every layer in its group(s).
        Uses each layer's stop_clip (if known), otherwise column 1.
        """
        d = self.deck_mgr.get_deck(deck)
        if not d:
            logging.warning(f"Deck '{deck}' not found for stop_deck")
            return

        layers = self._all_layers_for_deck(deck)
        if not layers:
            logging.info("[callbacks] stop_deck: no layers found for deck '%s'", deck)
        else:
            for li in layers:
                stop_col = getattr(li, "stop_clip", None)
                if stop_col is None:
                    logging.warning("[callbacks] stop_deck: layer %s has no stop_clip; using 1", li.index)
                column = stop_col if (stop_col is not None) else 1
                path = f"/composition/layers/{li.index}/clips/{column}/connect"
                try:
                    self.osc.client.send_message(path, 1)
                    logging.debug("[callbacks] stop_deck -> %s (layer %s, col %s)", path, li.index, column)
                except Exception:
                    logging.exception("[callbacks] stop_deck failed to send OSC: %s 1", path)

        d.playing = False
        d.fill = 0.0
        logging.info(f"[{deck}] STOPPED (all layers -> stop clip, fill=0)")
        self._send_deck_state(deck)

    def random_fills(self, deck):
        d = self.deck_mgr.get_deck(deck)
        if not d:
            logging.warning(f"Deck '{deck}' not found for random_fills")
            return
        v = random.choice([0.0, 0.25, 0.5, 0.75, 1.0])

        d.fill = v
        d.playing = True
        logging.info(f"[{deck}] Random Fill -> {d.fill:.3f} (playing={d.playing})")

        self._fire_fills_for_deck(deck, v)
        self._send_deck_state(deck)

    def next_clip(self, deck):
        """
        Advance clips by layer type:
          - Always advance all FILL layers
          - Additionally advance COLORS layers if deck.colors is True
          - Additionally advance TRANSFORMS layers if deck.transform is True
          - Additionally advance EFFECTS layers if deck.effects is True

        Uses /composition/layers/{layer_index}/connectnextclip with value 1.
        """
        d = self.deck_mgr.get_deck(deck)
        if not d:
            logging.warning(f"Deck '{deck}' not found for next_clip")
            return

        # Always: fills
        fill_layers = self._layers_of_type_for_deck(deck, "fills")
        self._connect_next_for_layers(fill_layers, "fills")

        # Conditionally: colors / transforms / effects
        if d.colors:
            self._connect_next_for_layers(self._layers_of_type_for_deck(deck, "colors"), "colors")
        if d.transform:
            self._connect_next_for_layers(self._layers_of_type_for_deck(deck, "transforms"), "transforms")
        if d.effects:
            self._connect_next_for_layers(self._layers_of_type_for_deck(deck, "effects"), "effects")

    def next_or_random(self, deck):
        d = self.deck_mgr.get_deck(deck)
        if not d:
            logging.warning(f"Deck '{deck}' not found for next_or_random")
            return
        if d.playing:
            self.next_clip(deck)
        else:
            self.random_fills(deck)

    # -------------------------------------------------
    # Global APC actions (tempo control)
    # -------------------------------------------------
    async def _pulse(self, path: str, on: float = 1.0, off: float = 0.0, delay: float = 0.2):
        """Send a momentary pulse: on, wait, off."""
        try:
            self.osc.client.send_message(path, on)
            await asyncio.sleep(delay)
            self.osc.client.send_message(path, off)
            logging.debug("[callbacks] pulse %s (%.2f -> %.2f)", path, on, off)
        except Exception:
            logging.exception("[callbacks] pulse failed for %s", path)

    async def tempo_tap(self):
        # /composition/tempocontroller/tempotap : pulse
        await self._pulse("/composition/tempocontroller/tempotap", 1, 0, 0.2)

    async def bpm_resync(self):
        # /composition/tempocontroller/resync : pulse
        await self._pulse("/composition/tempocontroller/resync", 1, 0, 0.2)

    async def toggle_metronome(self):
        # /composition/tempocontroller/metronome : pulse
        await self._pulse("/composition/tempocontroller/metronome", 1, 0, 0.2)

    def nudge_minus(self):
        # /composition/tempocontroller/tempo/dec : single trigger
        try:
            self.osc.client.send_message("/composition/tempocontroller/tempo/dec", 1)
            logging.debug("[callbacks] tempo dec -> 1")
        except Exception:
            logging.exception("[callbacks] failed to send tempo dec")

    def nudge_plus(self):
        # /composition/tempocontroller/tempo/inc : single trigger
        try:
            self.osc.client.send_message("/composition/tempocontroller/tempo/inc", 1)
            logging.debug("[callbacks] tempo inc -> 1")
        except Exception:
            logging.exception("[callbacks] failed to send tempo inc")

    def stop_all_decks(self):
        logging.info("Stopping all decks")
        for d in self.deck_mgr.all_decks():
            d.playing = False
            d.fill = 0.0
            self._send_deck_state(d.name)
        # Keep this general control if you still want it, or remove
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

    def tempo_tap_legacy(self):  # keep if anything still bound here
        logging.info("Tempo TAP (legacy)")
        self.osc.client.send_message("/czechb/control/tempo/tap", 1)

    # -------------------------------------------------
    # Internal
    # -------------------------------------------------
    def _send_deck_state(self, deck):
        """Push the current state of a deck to Resolume via OSC (status bus)."""
        d = self.deck_mgr.get_deck(deck)
        if not d:
            return
        self.osc.client.send_message(f"/deck/{deck}/effects",   int(d.effects))
        self.osc.client.send_message(f"/deck/{deck}/colors",    int(d.colors))
        self.osc.client.send_message(f"/deck/{deck}/transform", int(d.transform))
        self.osc.client.send_message(f"/deck/{deck}/fill",      float(d.fill))
        self.osc.client.send_message(f"/deck/{deck}/opacity",   float(d.opacity))
