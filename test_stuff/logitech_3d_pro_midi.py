"""
logitech_3d_pro_midi.py
==========================

This module provides a drop‑in replacement for the OSC‑based joystick
forwarder contained in the ``logitech_3d_pro_stuff`` branch.  Instead of
sending values over Open Sound Control, it transmits them as MIDI
messages to a virtual device called ``To Resolume`` (or any other
user‑specified output).  It relies on the ``mido`` package (which in
turn depends on ``python‑rtmidi``) to interface with the MIDI
subsystem.

The basic strategy is as follows:

1. Each joystick axis is mapped to a MIDI **control change** (CC)
   number.  By default, axis ``0`` is sent on CC ``0``, axis ``1`` on
   CC ``1``, and so on.  Axis values in the range ``[-1.0, 1.0]`` are
   scaled to the MIDI CC range ``0–127``.  You can customise this
   mapping via the ``cc_map`` dictionary when instantiating
   ``MIDISender``.
2. Button presses generate MIDI **note on/off** messages.  Button
   ``n`` triggers note ``60 + n`` (middle C plus the button index), with
   velocity ``127`` for a press and ``0`` for a release.  The ``note_map``
   dictionary lets you override which notes are used for each button.
3. The joystick’s hat (D‑pad) sends a pair of CC messages
   (numbers ``100`` and ``101`` by default) representing the ``x`` and
   ``y`` directions.  Values are mapped from ``-1, 0, 1`` to ``0, 64, 127``.

To use this module, install the ``mido`` package (and its underlying
``python‑rtmidi`` dependency) and make sure a virtual or hardware MIDI
port named ``To Resolume`` exists on your system.  On macOS and
Windows, you can create a virtual output with LoopMIDI or the MIDI
utilities built into the OS.  On Linux, ALSA’s ``virmidi`` or
``a2jmidid`` can provide a similar loopback device.

Example usage:

.. code-block:: python

   import pygame
   from libraries.logitech_3d_pro import JoystickInput
   from logitech_3d_pro_midi import MIDISender

   # configure and start joystick
   pygame.init()
   joy = pygame.joystick.Joystick(0)
   joy.init()
   js = JoystickInput(joy)
   midi = MIDISender(port_name="To Resolume")

   # in your event loop
   js.update()  # process axis deadzones/envelopes
   midi.send_axis_updates(js.state)
   midi.send_button_updates(joy)
   midi.send_hat_update(joy)

See the ``main()`` function at the bottom of this file for a complete
stand‑alone joystick→MIDI forwarder.
"""

from __future__ import annotations

import logging
from typing import Dict, Iterable, List, Tuple

import mido  # type: ignore

logger = logging.getLogger(__name__)


class MIDISender:
    """Send joystick values as MIDI messages.

    Parameters
    ----------
    port_name:
        The name of the MIDI output port to send messages to.  If the
        port is not found, an exception will be raised.
    cc_map:
        Optional mapping of joystick axis index to MIDI CC number.  If
        omitted, axis ``i`` will be mapped to CC ``i``.
    note_map:
        Optional mapping of joystick button index to MIDI note number.
        Defaults to ``60 + index`` (C4 plus button index).
    hat_cc:
        Tuple of two CC numbers for the hat x and y axes.  The first
        value controls the x direction, the second the y direction.
    channel:
        MIDI channel to send on (0–15).  Defaults to 0.
    """

    def __init__(
        self,
        port_name: str = "To Resolume",
        cc_map: Dict[int, int] | None = None,
        note_map: Dict[int, int] | None = None,
        hat_cc: Tuple[int, int] = (100, 101),
        channel: int = 0,
    ) -> None:
        self.port_name = port_name
        self.cc_map = cc_map or {}
        self.note_map = note_map or {}
        self.hat_cc = hat_cc
        self.channel = channel

        # Attempt to open the specified MIDI output port.  Use an exact
        # match to avoid accidentally connecting to the wrong device.
        available = mido.get_output_names()
        if self.port_name not in available:
            raise ValueError(
                f"MIDI output port '{self.port_name}' not found. Available ports: {available}"
            )
        self.output = mido.open_output(self.port_name)
        logger.info("Opened MIDI output port %s", self.port_name)

        # Track previous state to avoid sending duplicate messages.
        self._prev_axis: List[int] = []
        self._prev_buttons: List[int] = []
        self._prev_hat: Tuple[int, int] | None = None

    # ------------------------------------------------------------------
    # Conversion helpers
    #
    def _scale_axis(self, value: float) -> int:
        """Convert a joystick axis value (−1.0–1.0) to a MIDI CC value (0–127).

        A value of −1.0 becomes 0, 0.0 becomes 64, and 1.0 becomes 127.
        Values outside this range are clamped.
        """
        scaled = int(round((value + 1.0) * 63.5))
        return max(0, min(127, scaled))

    def _scale_hat(self, value: int) -> int:
        """Convert a hat direction (−1, 0, 1) to a MIDI value (0, 64, 127)."""
        if value < 0:
            return 0
        elif value > 0:
            return 127
        return 64

    # ------------------------------------------------------------------
    # Sending methods
    #
    def send_axis_updates(self, axes: Iterable[float]) -> None:
        """Send CC messages for axes that changed.

        Parameters
        ----------
        axes:
            An iterable of processed joystick axis values (typically from
            ``JoystickInput.state``).  Each value should be in the range
            −1.0–1.0 after applying deadzones and envelopes.
        """
        axis_values = list(axes)
        # Initialise previous state on first call
        if not self._prev_axis:
            self._prev_axis = [self._scale_axis(v) for v in axis_values]
        for i, val in enumerate(axis_values):
            cc = self.cc_map.get(i, i)
            midi_val = self._scale_axis(val)
            if i >= len(self._prev_axis) or midi_val != self._prev_axis[i]:
                msg = mido.Message(
                    "control_change",
                    channel=self.channel,
                    control=cc,
                    value=midi_val,
                )
                self.output.send(msg)
                self._prev_axis[i : i + 1] = [midi_val]

    def send_button_updates(self, joy) -> None:
        """Send note on/off messages for button state changes.

        The ``joy`` object must have a ``get_numbuttons()`` and
        ``get_button(index)`` methods (as provided by ``pygame.joystick.Joystick``).
        """
        num_buttons = joy.get_numbuttons()
        if not self._prev_buttons:
            self._prev_buttons = [0] * num_buttons
        for i in range(num_buttons):
            state = joy.get_button(i)
            if i >= len(self._prev_buttons) or state != self._prev_buttons[i]:
                note = self.note_map.get(i, 60 + i)
                velocity = 127 if state else 0
                msg = mido.Message(
                    "note_on" if state else "note_off",
                    channel=self.channel,
                    note=note,
                    velocity=velocity,
                )
                self.output.send(msg)
                self._prev_buttons[i : i + 1] = [state]

    def send_hat_update(self, joy) -> None:
        """Send CC messages when the hat (D‑pad) changes.

        Expects ``joy.get_hat(0)`` to return a tuple ``(x, y)`` with values
        −1, 0 or 1.  Sends two control change messages: one for ``x`` and
        one for ``y``.
        """
        if joy.get_numhats() == 0:
            return
        current = joy.get_hat(0)
        if self._prev_hat is None:
            self._prev_hat = current
        if current != self._prev_hat:
            cc_x, cc_y = self.hat_cc
            val_x = self._scale_hat(current[0])
            val_y = self._scale_hat(current[1])
            # send both CC messages
            self.output.send(
                mido.Message(
                    "control_change",
                    channel=self.channel,
                    control=cc_x,
                    value=val_x,
                )
            )
            self.output.send(
                mido.Message(
                    "control_change",
                    channel=self.channel,
                    control=cc_y,
                    value=val_y,
                )
            )
            self._prev_hat = current


def _log_available_ports() -> None:
    """Helper function to log available MIDI output ports.

    If ``To Resolume`` isn’t found, call this to discover the correct
    port name.  On Windows and macOS the list will include any virtual
    loopback devices you have configured.
    """
    ports = mido.get_output_names()
    if not ports:
        logger.warning("No MIDI output ports found. Make sure your system has a loopback device.")
    else:
        logger.info("Available MIDI output ports: %s", ports)


def main() -> None:
    """Stand‑alone joystick to MIDI forwarder.

    This function recreates the logic of ``logitech_3d_pro_osc_script.py`` but
    outputs MIDI messages instead of OSC.  It uses ``JoystickInput`` from
    ``libraries.logitech_3d_pro`` to process deadzones and envelope curves,
    and ``MIDISender`` to transmit the resulting values.  Run it directly
    (``python logitech_3d_pro_midi.py``) after connecting your joystick
    and ensuring the ``To Resolume`` MIDI device is available.
    """
    import sys
    import time
    import pygame
    import os
    # Add parent directory to sys.path to allow imports from folder above
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

    from libraries.logitech_3d_pro import JoystickInput
    
    import os

    # Configure logging to stderr
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    pygame.init()
    pygame.joystick.init()
    if pygame.joystick.get_count() == 0:
        print("No joystick detected. Connect a joystick and try again.")
        sys.exit(1)
    joy = pygame.joystick.Joystick(0)
    joy.init()
    print(f"Connected joystick: {joy.get_name()}")

    js_input = JoystickInput(joy)
    # Configure axis deadzones and envelopes here if desired
    for i in range(joy.get_numaxes()):
        js_input.set_deadzone(i, 0.1)
        js_input.set_envelope(i, "sine_out" if i % 2 == 0 else "expo_in")

    # Attempt to connect to the To Resolume MIDI port
    try:
        midi_sender = MIDISender(port_name="To Resolume 2")
    except ValueError as e:
        print(e)
        _log_available_ports()
        sys.exit(1)

    # Set thresholds for axis change detection
    axis_epsilon = 0.01

    prev_js_state = js_input.state.copy()
    prev_buttons = [joy.get_button(i) for i in range(joy.get_numbuttons())]
    prev_hat = joy.get_hat(0) if joy.get_numhats() > 0 else (0, 0)

    try:
        while True:
            pygame.event.pump()
            # Process axis values through JoystickInput
            # js_input.update_and_send_midi(midi_sender)
            # Send axis CC messages if changed
            for i, val in enumerate(js_input.state):
                if abs(val - prev_js_state[i]) > axis_epsilon:
                    midi_sender.send_axis_updates([val if j == i else prev_js_state[j] for j in range(len(js_input.state))])
                    prev_js_state[i] = val
            # Send button note messages if changed
            for i in range(joy.get_numbuttons()):
                current = joy.get_button(i)
                if current != prev_buttons[i]:
                    midi_sender.send_button_updates(joy)
                    prev_buttons[i] = current
            # Send hat CC messages if changed
            if joy.get_numhats() > 0:
                current_hat = joy.get_hat(0)
                if current_hat != prev_hat:
                    midi_sender.send_hat_update(joy)
                    prev_hat = current_hat
            time.sleep(0.01)
    except KeyboardInterrupt:
        print("\nExiting…")
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()