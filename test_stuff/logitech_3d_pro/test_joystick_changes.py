import pygame
import sys

def init_joystick():
    pygame.init()
    pygame.joystick.init()

    if pygame.joystick.get_count() == 0:
        print("No joystick detected.")
        sys.exit()

    joy = pygame.joystick.Joystick(0)
    joy.init()
    print(f"Joystick connected: {joy.get_name()}")
    return joy

def get_joystick_state(joy):
    state = {
        "axes": [round(joy.get_axis(i), 3) for i in range(joy.get_numaxes())],
        "buttons": [joy.get_button(i) for i in range(joy.get_numbuttons())],
        "hats": [joy.get_hat(i) for i in range(joy.get_numhats())],
    }
    return state

def print_state_changes(prev, current):
    for i, (old, new) in enumerate(zip(prev["axes"], current["axes"])):
        if old != new:
            print(f"Axis {i} changed: {old:.3f} → {new:.3f}")

    for i, (old, new) in enumerate(zip(prev["buttons"], current["buttons"])):
        if old != new:
            state = "Pressed" if new else "Released"
            print(f"Button {i} {state}")

    for i, (old, new) in enumerate(zip(prev["hats"], current["hats"])):
        if old != new:
            print(f"Hat {i} changed: {old} → {new}")

def main():
    joy = init_joystick()
    prev_state = get_joystick_state(joy)

    try:
        while True:
            pygame.event.pump()
            current_state = get_joystick_state(joy)
            print_state_changes(prev_state, current_state)
            prev_state = current_state
            pygame.time.wait(50)

    except KeyboardInterrupt:
        print("Exiting...")
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    main()
