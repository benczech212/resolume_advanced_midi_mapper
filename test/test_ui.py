# visualize_decks.py
# Simple live UI to visualize deck states (playing/effects/colors/transform/fill)
# Runs your full App (OSC, HTTP refresh, MIDI/joystick) + a Pygame UI task.

import asyncio
import logging
import os
import sys
import math
import time

import pygame
import yaml
sys.path.append(os.path.dirname(os.path.dirname(__file__)))  # add repo root to sys.path


# Reuse your App + config loader from deck_router.py
from run import App, load_yaml, DEFAULT_CONFIG


# ---------- UI drawing helpers ----------

def _deck_cards_layout(num_decks: int, card_w=280, card_h=140, margin=16, max_cols=3):
    """Compute a grid for N cards; yields (x, y) per index and the window size."""
    cols = min(max_cols, max(1, num_decks))
    rows = math.ceil(num_decks / cols) if num_decks else 1
    width = margin + cols * (card_w + margin)
    height = margin + rows * (card_h + margin)
    positions = []
    for i in range(num_decks):
        r = i // cols
        c = i % cols
        x = margin + c * (card_w + margin)
        y = margin + r * (card_h + margin)
        positions.append((x, y))
    return positions, (max(width, 640), max(height, 480))


def _chip(surface, x, y, label, active, color_active, color_inactive, font):
    bg = color_active if active else color_inactive
    rect = pygame.Rect(x, y, 88, 22)
    pygame.draw.rect(surface, bg, rect, border_radius=8)
    pygame.draw.rect(surface, (30, 30, 30), rect, width=1, border_radius=8)
    text = font.render(label, True, (12, 12, 12) if active else (200, 200, 200))
    surface.blit(text, (x + 8, y + 3))


def _status_dot(surface, x, y, on, on_color=(0, 200, 0), off_color=(120, 30, 30)):
    color = on_color if on else off_color
    pygame.draw.circle(surface, (20, 20, 20), (x, y), 10)
    pygame.draw.circle(surface, color, (x, y), 8)


def _fill_bar(surface, x, y, w, h, frac):
    frac = max(0.0, min(1.0, float(frac)))
    pygame.draw.rect(surface, (45, 45, 45), (x, y, w, h), border_radius=6)
    pygame.draw.rect(surface, (30, 30, 30), (x, y, w, h), width=1, border_radius=6)
    if frac > 0:
        pygame.draw.rect(surface, (0, 160, 220), (x + 2, y + 2, int((w - 4) * frac), h - 4), border_radius=6)


def draw_decks(surface, deck_mgr, font_title, font_body):
    surface.fill((18, 18, 18))

    decks = list(deck_mgr.all_decks())
    positions, (win_w, win_h) = _deck_cards_layout(len(decks))
    # Resize window if needed (rare)
    current_size = surface.get_size()
    if current_size != (win_w, win_h):
        pygame.display.set_mode((win_w, win_h))

    card_w, card_h = 280, 140
    for (deck, (x, y)) in zip(decks, positions):
        # Card
        pygame.draw.rect(surface, (28, 28, 28), (x, y, card_w, card_h), border_radius=16)
        pygame.draw.rect(surface, (50, 50, 50), (x, y, card_w, card_h), width=1, border_radius=16)

        # Title + status dot
        name_surf = font_title.render(deck.name, True, (230, 230, 230))
        surface.blit(name_surf, (x + 16, y + 12))
        _status_dot(surface, x + card_w - 24, y + 22, deck.playing)

        # Chips row
        chip_y = y + 50
        _chip(surface, x + 16, chip_y, "Effects", deck.effects, (220, 190, 0), (70, 70, 70), font_body)
        _chip(surface, x + 118, chip_y, "Colors", deck.colors, (210, 60, 60), (70, 70, 70), font_body)
        _chip(surface, x + 220, chip_y, "Xform", deck.transform, (90, 180, 220), (70, 70, 70), font_body)

        # Fill bar + text
        bar_y = y + 90
        _fill_bar(surface, x + 16, bar_y, card_w - 32, 18, deck.fill)
        pct = int(round(deck.fill * 100))
        pct_surf = font_body.render(f"{pct}%", True, (200, 200, 200))
        surface.blit(pct_surf, (x + card_w - 16 - pct_surf.get_width(), bar_y - 22))


async def ui_loop(deck_mgr, fps=30):
    pygame.init()
    # initial window; will auto-resize after first draw if needed
    screen = pygame.display.set_mode((960, 600))
    pygame.display.set_caption("Deck State Visualizer")
    font_title = pygame.font.SysFont(None, 26)
    font_body = pygame.font.SysFont(None, 20)

    try:
        while True:
            # Handle window events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    raise SystemExit
                if event.type == pygame.KEYDOWN and event.key in (pygame.K_q, pygame.K_ESCAPE):
                    raise SystemExit

            draw_decks(screen, deck_mgr, font_title, font_body)
            pygame.display.flip()
            await asyncio.sleep(1.0 / fps)
    finally:
        pygame.quit()


async def run_with_ui(app):
    loop = asyncio.get_event_loop()
    await app.osc.start_server(loop)
    logging.info("OSC server started on %s:%s", app.cfg["osc"]["rx_host"], app.cfg["osc"]["rx_port"])

    # Start everything your App normally runs, plus the UI
    tasks = [
        asyncio.create_task(app._pump_events()),
        asyncio.create_task(app._run_devices()),
        asyncio.create_task(app.reflector.run()),
        asyncio.create_task(app._refresh_composition_http()),
        asyncio.create_task(ui_loop(app.deck_mgr, fps=30)),
    ]
    await asyncio.gather(*tasks)


def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )
    logging.info("Booting deck visualizer")

    # Load your existing config and optional LED maps
    cfg_path = "config.yml"
    lp_map_path = "launchpad_led_map.yml"
    apc_map_path = "apc_led_map.yml"

    cfg = load_yaml(cfg_path, DEFAULT_CONFIG)
    # LED maps not directly used in UI, but App init needs them if devices enabled
    def _safe_load(path):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}
    lp_map = _safe_load(lp_map_path) if cfg.get("enable_launchpad", False) else {}
    apc_map = _safe_load(apc_map_path) if cfg.get("enable_apc40", True) else {}

    # Build and run the app + UI
    app = App(cfg, lp_map, apc_map)
    try:
        asyncio.run(run_with_ui(app))
    except SystemExit:
        logging.info("Exiting visualizer")
    except KeyboardInterrupt:
        logging.info("Shutting down (KeyboardInterrupt)")
    except Exception as e:
        logging.exception("Fatal error: %s", e)


if __name__ == "__main__":
    main()
