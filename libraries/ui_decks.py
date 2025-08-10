# libraries/ui_decks.py
import asyncio
import logging
from typing import Iterable, Tuple, List, Any, Dict, Optional
import pygame

log = logging.getLogger(__name__)

# ---- styling knobs (easy to tweak) ----
CARD_W   = 320
CARD_H   = 300          # taller deck
MARGIN   = 16
TITLE_PAD = 14          # more space under title
BAR_H    = 136          # taller bar
BAR_W    = 22           # wider bar
BTN_H    = 28           # taller buttons
ROW_GAP  = 32           # a bit more spacing between rows

ON_COLOR_MAP = {
    "effects":   (210, 60, 60),   # red
    "colors":    (0, 160, 220),   # blue
    "transforms": (60, 200, 120),
}
OFF_CHIP = (70, 70, 70)


def _named_decks_map(deck_mgr) -> Dict[str, Any]:
    """Return {name: deck_obj} regardless of DeckManager internals."""
    d = getattr(deck_mgr, "decks", None)
    if isinstance(d, dict):
        return dict(d)
    decks: Iterable[Any] = []
    if hasattr(deck_mgr, "all_decks"):
        try:
            decks = deck_mgr.all_decks()
        except Exception:
            decks = []
    elif isinstance(d, (list, tuple)):
        decks = d
    out: Dict[str, Any] = {}
    for idx, deck in enumerate(decks):
        name = getattr(deck, "name", f"deck_{idx+1}")
        out[name] = deck
    return out


class DeckStateUI:
    """
    One-row visualizer (8 columns by default).
    Provide slot_order=list of deck names (or None) of length total_slots to pin positions.
    Any name not found in DeckManager becomes a placeholder.
    """
    def __init__(
        self,
        deck_mgr,
        title: str = "Deck State Visualizer",
        fps: int = 30,
        total_slots: int = 8,
        slot_order: Optional[List[Optional[str]]] = None,
    ):
        self.deck_mgr = deck_mgr
        self.title = title
        self.fps = max(1, int(fps))
        self.total_slots = max(1, int(total_slots))
        self.slot_order = list(slot_order or [None] * self.total_slots)

        self.card_w, self.card_h = CARD_W, CARD_H
        self.margin = MARGIN

        self._screen = None
        self._font_title = None
        self._font_body = None
        self._running = False

    # ---------- drawing helpers ----------

    def _status_dot(self, x, y, on, on_color=(0, 200, 0), off_color=(120, 30, 30)):
        pygame.draw.circle(self._screen, (20, 20, 20), (x, y), 10)
        pygame.draw.circle(self._screen, on_color if on else off_color, (x, y), 8)

    def _vbar_centered(self, cx, top_y, w, h, frac, color):
        """Vertical bar centered at cx (bottom→top). Returns percent (int)."""
        try:
            f = float(frac)
        except Exception:
            f = 0.0
        f = max(0.0, min(1.0, f))
        x = int(cx - w // 2)
        # frame
        pygame.draw.rect(self._screen, (45, 45, 45), (x, top_y, w, h), border_radius=6)
        pygame.draw.rect(self._screen, (30, 30, 30), (x, top_y, w, h), width=1, border_radius=6)
        # fill
        if f > 0:
            filled_h = int((h - 4) * f)
            pygame.draw.rect(
                self._screen,
                color,
                (x + 2, top_y + (h - 2 - filled_h), w - 4, filled_h),
                border_radius=6,
            )
        return int(round(f * 100))

    def _row_button(self, x, y, w, label, active):
        key = label.strip().lower()
        bg_on = ON_COLOR_MAP.get(key, (210, 60, 60))
        rect = pygame.Rect(x, y, w, BTN_H)
        pygame.draw.rect(self._screen, bg_on if active else OFF_CHIP, rect, border_radius=8)
        pygame.draw.rect(self._screen, (30, 30, 30), rect, width=1, border_radius=8)
        fg = (245, 245, 245) if active else (200, 200, 200)
        text = self._font_body.render(label, True, fg)
        # center the label inside the button
        text_rect = text.get_rect(center=(x + w / 2, y + BTN_H / 2))
        self._screen.blit(text, text_rect)

    # ---------- layout ----------

    def _positions_and_window(self):
        cols = self.total_slots
        w = self.margin + cols * (self.card_w + self.margin)
        h = self.margin + self.card_h + self.margin
        positions = [(self.margin + i * (self.card_w + self.margin), self.margin) for i in range(cols)]
        return positions, (w, h)

    # ---------- main drawing ----------

    def _draw_cards(self):
        self._screen.fill((18, 18, 18))

        # Map of existing decks by name
        deck_by_name = _named_decks_map(self.deck_mgr)

        # Build slot list of (name, deck) or None
        slots: List[Optional[Tuple[str, Any]]] = []
        for name in (self.slot_order + [None] * self.total_slots)[: self.total_slots]:
            if name is None:
                slots.append(None)
            else:
                deck = deck_by_name.get(name)
                slots.append((name, deck) if deck is not None else None)

        positions, (win_w, win_h) = self._positions_and_window()
        if self._screen.get_size() != (win_w, win_h):
            pygame.display.set_mode((win_w, win_h))

        for slot, (x, y) in zip(slots, positions):
            if slot is None:
                continue

            name, deck = slot
            # Card shell
            pygame.draw.rect(self._screen, (28, 28, 28), (x, y, self.card_w, self.card_h), border_radius=16)
            pygame.draw.rect(self._screen, (50, 50, 50), (x, y, self.card_w, self.card_h), width=1, border_radius=16)

            # Title + play dot
            name_surf = self._font_title.render(name, True, (230, 230, 230))
            self._screen.blit(name_surf, (x + 16, y + 12))
            self._status_dot(x + self.card_w - 24, y + 22, bool(getattr(deck, "playing", False)))

            # Top row area
            inner_x = x + 16
            inner_w = self.card_w - 32
            top_y  = y + 12 + name_surf.get_height() + TITLE_PAD  # extra padding under title
            half_w = inner_w // 2
            gap_between_halves = 12

            # Left half (Fill) — center bar & % within half
            left_cx = inner_x + (half_w // 2)
            pct_fill = self._vbar_centered(left_cx, top_y, BAR_W, BAR_H, getattr(deck, "fill", 0.0), color=(60, 200, 120))
            # centered % above bar with safe padding
            pct_text = self._font_body.render(f"{pct_fill}%", True, (200, 200, 200))
            pct_y = int(top_y - (pct_text.get_height() + 6))
            self._screen.blit(pct_text, (int(left_cx - pct_text.get_width() / 2), pct_y))

            # Right half (Opacity)
            right_origin_x = inner_x + half_w + gap_between_halves
            right_cx = right_origin_x + (half_w - gap_between_halves) // 2
            pct_op = self._vbar_centered(right_cx, top_y, BAR_W, BAR_H, getattr(deck, "opacity", 1.0), color=(170, 170, 170))
            pct_text2 = self._font_body.render(f"{pct_op}%", True, (200, 200, 200))
            pct2_y = int(top_y - (pct_text2.get_height() + 6))
            self._screen.blit(pct_text2, (int(right_cx - pct_text2.get_width() / 2), pct2_y))

            # Bottom rows: Transform, Colors, Effects (labels centered)
            row_x = inner_x
            row_w = inner_w
            row1_y = top_y + BAR_H + 16  # tiny bit more space here too

            transform_on = bool(getattr(deck, "transform", getattr(deck, "transforms", False)))
            self._row_button(row_x, row1_y + 0 * ROW_GAP, row_w, "Transforms",   transform_on)
            self._row_button(row_x, row1_y + 1 * ROW_GAP, row_w, "Colors",  bool(getattr(deck, "colors", 0)))
            self._row_button(row_x, row1_y + 2 * ROW_GAP, row_w, "Effects", bool(getattr(deck, "effects", 0)))

    # ---------- loop ----------

    async def run(self):
        pygame.init()
        try:
            # Wider & taller initial window; will resize on first draw to exact size
            self._screen = pygame.display.set_mode((1850, 360))
            pygame.display.set_caption(self.title)
            self._font_title = pygame.font.SysFont(None, 26)
            self._font_body  = pygame.font.SysFont(None, 18)
            self._running = True
            log.info("DeckStateUI started (fps=%s, slots=%s)", self.fps, self.total_slots)

            interval = 1.0 / self.fps
            while self._running:
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self._running = False
                    elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                        self._running = False
                self._draw_cards()
                pygame.display.flip()
                await asyncio.sleep(interval)
        finally:
            try: pygame.quit()
            except Exception: pass
            log.info("DeckStateUI stopped")

    def stop(self):
        self._running = False
