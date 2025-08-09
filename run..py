"""
This script reads input from a Logitech Extreme 3D Pro joystick using ``pygame``
and forwards those values as Open Sound Control (OSC) messages for consumption
by Resolume Wire or other OSC‑aware tools.  It depends on the helper
modules added in the ``logitech_3d_pro_stuff`` branch of the
``resolume_advanced_midi_mapper`` repository:

* ``libraries/logitech_3d_pro.py`` – provides a ``JoystickInput`` class that
  handles deadzones and per‑axis envelope curves (linear, sine, exponential,
  etc.)【519963677954088†L17-L46】.
* ``libraries/resolume_osc_manager.py`` – exposes an ``OSCSender`` class
  wrapping ``pythonosc`` to send axis, button and hat messages to a given
  host/port.  It defines default OSC address patterns of the form
  ``/czechb/joystick/axis/{axis_id}``, ``/czechb/joystick/button/{button_id}``
  and ``/czechb/joystick/hat``【749634091509401†L13-L26】.

To use this script, make sure ``pygame`` and ``python-osc`` are installed and
the joystick is connected.  You can customise the OSC destination by
adjusting the ``OSC_IP`` and ``OSC_PORT`` constants below.  When run, the
script will send an OSC message whenever an axis moves beyond its deadzone
or a button/hat state changes.
"""

import sys
import time
import pygame

# Import helper classes from the ``libraries`` package.  These modules live
# inside the ``logitech_3d_pro_stuff`` branch of ``resolume_advanced_midi_mapper``.
from libraries.logitech_3d_pro import JoystickInput
from libraries.resolume_osc_manager import OSCSender

# ----------------------------------------------------------------------------
# Configuration
#
# Adjust these values as needed for your network.  Resolume Arena/Avenue
# defaults to listening for OSC messages on port 7000 on localhost.  If
# you're running Resolume on a different machine or port, update these
# accordingly.

OSC_IP: str = "127.0.0.1"
OSC_PORT: int = 8000

# Minimum axis change required to send an update.  The built‑in
# ``JoystickInput`` already enforces a deadzone and envelope; this threshold
# simply reduces OSC traffic for tiny movements.  Set to 0 to always
# transmit.
AXIS_EPSILON: float = 0.01

def init_joystick() -> pygame.joystick.Joystick:
    """Initialise Pygame and return the first available joystick.

    Exits the program if no joystick is detected.
    """
    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        print("No joystick detected.  Connect a joystick and try again.")
        sys.exit(1)
    joy = pygame.joystick.Joystick(0)
    joy.init()
    print(f"Connected joystick: {joy.get_name()}")
    return joy


def main() -> None:
    """Entry point for joystick → OSC forwarding.

    Continuously polls the joystick for axis, button and hat state changes.
    Axis values are pre‑processed via ``JoystickInput`` which applies
    deadzones and envelope curves.  When a value changes beyond
    ``AXIS_EPSILON``, or when a button/hat state toggles, an OSC message is
    sent via ``OSCSender``.
    """
    # Set up joystick and helpers.
    joy = init_joystick()
    js_input = JoystickInput(joy)
    osc_sender = OSCSender(ip=OSC_IP, port=OSC_PORT)

    # Configure deadzones/envelopes per axis if desired.  For example,
    # alternate between sine‑out and exponential‑in on even/odd axes.  You can
    # call js_input.set_deadzone(index, value) and js_input.set_envelope(index,
    # name) before entering the loop.
    for i in range(joy.get_numaxes()):
        js_input.set_deadzone(i, 0.1)  # 10% deadzone
        js_input.set_envelope(i, "sine_out" if i % 2 == 0 else "expo_in")

    # Track previous button and hat states to detect changes.
    prev_buttons = [joy.get_button(i) for i in range(joy.get_numbuttons())]
    prev_hat = joy.get_hat(0) if joy.get_numhats() > 0 else (0, 0)

    try:
        while True:
            # Pump Pygame event queue to update joystick state.
            pygame.event.pump()

            # Update axes via JoystickInput and send OSC for changes.
            for axis_index in range(joy.get_numaxes()):
                new_val = js_input.process_axis(axis_index)
                # Only send if the processed value changed beyond the threshold.
                if abs(new_val - js_input.state[axis_index]) > AXIS_EPSILON:
                    osc_sender.send_axis(axis_index, new_val)
                    js_input.state[axis_index] = new_val

            # Check button state changes.
            for btn_index in range(joy.get_numbuttons()):
                current = joy.get_button(btn_index)
                if current != prev_buttons[btn_index]:
                    osc_sender.send_button(btn_index, current)
                    prev_buttons[btn_index] = current

            # Check hat (D‑pad) changes.  Many joysticks only have one hat.
            if joy.get_numhats() > 0:
                current_hat = joy.get_hat(0)
                if current_hat != prev_hat:
                    osc_sender.send_hat(*current_hat)
                    prev_hat = current_hat

            # Sleep briefly to avoid hogging CPU.
            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\nExiting…")
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()