import pygame
import math
import sys

# === Joystick Input Class ===
class JoystickInput:
    def __init__(self, joystick):
        self.joystick = joystick
        self.num_axes = joystick.get_numaxes()
        self.deadzone = [0.05] * self.num_axes
        self.envelopes = ["linear"] * self.num_axes
        self.state = [0.0] * self.num_axes

    def set_deadzone(self, axis, value):
        self.deadzone[axis] = value

    def set_envelope(self, axis, envelope_name):
        if envelope_name in envelopes:
            self.envelopes[axis] = envelope_name
        else:
            raise ValueError(f"Envelope '{envelope_name}' not recognized")

    def process_axis(self, axis_index):
        raw = self.joystick.get_axis(axis_index)
        dz = self.deadzone[axis_index]

        # Apply deadzone
        if abs(raw) < dz:
            return 0.0

        # Normalize between 0–1 (excluding deadzone)
        norm = (abs(raw) - dz) / (1 - dz)
        norm = max(0.0, min(norm, 1.0))

        # Apply envelope
        transformed = envelopes[self.envelopes[axis_index]](norm)
        return math.copysign(transformed, raw)

    def update(self):
        for i in range(self.num_axes):
            self.state[i] = self.process_axis(i)

    def get_state(self):
        return self.state.copy()

# === Axis Visualization ===
def draw_axes(screen, joystick_input, raw_vals, width, height):
    axis_height = 30
    bar_width = width - 100
    offset_y = 50

    for i, (raw, processed) in enumerate(zip(raw_vals, joystick_input.get_state())):
        y = offset_y + i * (axis_height + 30)

        # Background bar
        pygame.draw.rect(screen, (60, 60, 60), (50, y, bar_width, axis_height))

        # Raw value (gray)
        raw_px = int((raw + 1) / 2 * bar_width)
        pygame.draw.rect(screen, (150, 150, 150), (50, y, raw_px, axis_height))

        # Processed value (cyan)
        proc_px = int((processed + 1) / 2 * bar_width)
        pygame.draw.rect(screen, (0, 255, 255), (50, y + 10, proc_px, 10))

        # Deadzone (red range)
        dz = joystick_input.deadzone[i]
        dz_min_px = int((0.5 - dz / 2) * bar_width)
        dz_max_px = int((0.5 + dz / 2) * bar_width)
        pygame.draw.rect(screen, (200, 60, 60), (50 + dz_min_px, y, dz_max_px - dz_min_px, axis_height), 2)

        label = f"Axis {i}: raw={raw:.2f}, processed={processed:.2f}, envelope={joystick_input.envelopes[i]}"
        font = pygame.font.SysFont(None, 20)
        text = font.render(label, True, (255, 255, 255))
        screen.blit(text, (50, y - 20))

# === Button Visualization ===
def draw_buttons(screen, joystick, screen_width, screen_height):
    num_buttons = joystick.get_numbuttons()
    radius = 15
    spacing = 40
    start_x = 60
    start_y = screen_height - 160

    font = pygame.font.SysFont(None, 20)
    for i in range(num_buttons):
        x = start_x + (i % 16) * spacing
        y = start_y + (i // 16) * (radius * 2 + 10)

        pressed = joystick.get_button(i)
        color = (0, 255, 0) if pressed else (100, 100, 100)
        pygame.draw.circle(screen, color, (x, y), radius)

        label = font.render(str(i), True, (0, 0, 0))
        label_rect = label.get_rect(center=(x, y))
        screen.blit(label, label_rect)

# === Hat Switch (D-Pad) Visualization ===
def draw_hat(screen, joystick, screen_width, screen_height):
    if joystick.get_numhats() == 0:
        return

    x, y = joystick.get_hat(0)  # Usually only 1 hat on Logitech 3D Pro
    pad_size = 100
    cx = screen_width - 150
    cy = screen_height - 150
    arrow_color = (255, 255, 0)
    box_color = (80, 80, 80)
    border = 3

    # Draw pad
    pygame.draw.rect(screen, box_color, (cx - pad_size // 2, cy - pad_size // 2, pad_size, pad_size), border)

    font = pygame.font.SysFont(None, 20)
    label = font.render(f"Hat: x={x}, y={y}", True, (255, 255, 255))
    screen.blit(label, (cx - 40, cy + pad_size // 2 + 10))

    # Draw active arrows
    if y == 1:
        pygame.draw.polygon(screen, arrow_color, [(cx, cy - 40), (cx - 10, cy - 20), (cx + 10, cy - 20)])
    if y == -1:
        pygame.draw.polygon(screen, arrow_color, [(cx, cy + 40), (cx - 10, cy + 20), (cx + 10, cy + 20)])
    if x == -1:
        pygame.draw.polygon(screen, arrow_color, [(cx - 40, cy), (cx - 20, cy - 10), (cx - 20, cy + 10)])
    if x == 1:
        pygame.draw.polygon(screen, arrow_color, [(cx + 40, cy), (cx + 20, cy - 10), (cx + 20, cy + 10)])

# === Main Loop ===
def main():
    pygame.init()
    pygame.joystick.init()
    width, height = 1000, 700
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("Logitech 3D Pro - Visualizer")

    if pygame.joystick.get_count() == 0:
        print("No joystick found.")
        sys.exit()

    joy = pygame.joystick.Joystick(0)
    joy.init()
    joystick_input = JoystickInput(joy)

    for i in range(joy.get_numaxes()):
        joystick_input.set_deadzone(i, 0.1)
        joystick_input.set_envelope(i, "sine_out" if i % 2 == 0 else "expo_in")

    clock = pygame.time.Clock()

    try:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    raise KeyboardInterrupt

            pygame.event.pump()
            raw_vals = [joy.get_axis(i) for i in range(joy.get_numaxes())]
            joystick_input.update()

            screen.fill((30, 30, 30))
            draw_axes(screen, joystick_input, raw_vals, width, height)
            draw_buttons(screen, joy, width, height)
            draw_hat(screen, joy, width, height)

            pygame.display.flip()
            clock.tick(60)

    except KeyboardInterrupt:
        print("Exiting...")
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    main()
