import pygame
import sys

# === Initialize pygame and joystick ===
pygame.init()
pygame.joystick.init()

# Check for joysticks
if pygame.joystick.get_count() == 0:
    print("No joystick detected.")
    sys.exit()

joystick = pygame.joystick.Joystick(0)
joystick.init()
print(f"Joystick connected: {joystick.get_name()}")

# === Main loop ===
try:
    while True:
        pygame.event.pump()  # Process event queue

        # Axes
        axes = joystick.get_numaxes()
        for i in range(axes):
            print(f"Axis {i}: {joystick.get_axis(i):.3f}")

        # Buttons
        buttons = joystick.get_numbuttons()
        for i in range(buttons):
            print(f"Button {i}: {'Pressed' if joystick.get_button(i) else 'Released'}")

        # Hat (D-Pad)
        hats = joystick.get_numhats()
        for i in range(hats):
            hat = joystick.get_hat(i)
            print(f"Hat {i}: x={hat[0]}, y={hat[1]}")

        print("-" * 40)
        pygame.time.wait(200)  # Wait 200ms between reads

except KeyboardInterrupt:
    print("Exiting...")
    pygame.quit()
    sys.exit()
