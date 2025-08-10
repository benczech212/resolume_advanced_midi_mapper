# test/joystick_probe.py
import time
import pygame

pygame.init()
pygame.joystick.init()

count = pygame.joystick.get_count()
print(f"Joysticks found: {count}")
if count == 0:
    print("No joystick detected.")
    raise SystemExit(1)

joy = pygame.joystick.Joystick(0)
joy.init()
print("Using:", joy.get_name())
print("Axes:", joy.get_numaxes(), "Buttons:", joy.get_numbuttons(), "Hats:", joy.get_numhats())

print("Move axes / press buttons. Ctrl+C to exit.")
try:
    while True:
        pygame.event.pump()

        for a in range(joy.get_numaxes()):
            val = joy.get_axis(a)
            if abs(val) > 0.01:
                print(f"AXIS {a}: {val:.3f}")

        for b in range(joy.get_numbuttons()):
            state = joy.get_button(b)
            if state:
                print(f"BUTTON {b}: {state}")

        for h in range(joy.get_numhats()):
            x, y = joy.get_hat(h)
            if (x, y) != (0, 0):
                print(f"HAT {h}: ({x},{y})")

        time.sleep(0.01)
except KeyboardInterrupt:
    print("\nExiting.")
finally:
    pygame.quit()
