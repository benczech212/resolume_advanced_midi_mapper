"""Configuration objects for multi‑device MIDI controller mappings.

The goal of this module is to provide a clean separation between the
"action mappings" (what callback to fire when a note or controller is
triggered) and the "location mappings" (where on the device a given
channel/note appears in an X/Y grid).

Other modules can import these dataclasses to build mapping tables for
different controllers (e.g. APC, Launchpad) and to modify them at
runtime without editing the core MIDI handling code.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple, Any


@dataclass
class ActionMapping:
    """Describe a mapping from a MIDI event to a callback.

    Attributes:
        name: Human‑readable name of the mapping.
        type: 'note' or 'cc'.
        channel: MIDI channel (0‑15) to which this mapping applies.
        note: Note number for note mappings, if applicable.
        controller: Controller number for CC mappings, if applicable.
        toggle: Whether this mapping toggles state on each press.
        callback: Callable invoked when the mapping is activated. The
            signature should be ``callback(state_or_value, midi_out, channel)``.
        hold_callback: Optional callable invoked when the note is held.
        hold_repeat_interval: Interval in seconds for repeating hold callbacks.
        easing: Optional easing function name or callable for scaling values.
    """
    
    name: str
    type: str = "note"
    channel: int = 0
    note: Optional[int] = None
    controller: Optional[int] = None
    toggle: bool = False
    callback: Optional[Callable[..., None]] = None
    hold_callback: Optional[Callable[..., None]] = None
    hold_repeat_interval: Optional[float] = None
    easing: Optional[Any] = None
    status_as_state: bool = False  # when True, use the status byte for ON/OFF


@dataclass
class ControllerConfig:
    """Holds mapping and layout definitions for a single controller type."""

    name: str
    midi_name: str
    action_mappings: List[ActionMapping] = field(default_factory=list)
    location_mappings: Dict[Tuple[int, int], Tuple[int, int]] = field(default_factory=dict)
    # If True, expand actions across Resolume channels via channel_group_mapping (APC behaviour).
    # If False, apply all actions to a single channel (e.g. Launchpad).
    use_channel_mapping: bool = True

    def add_action(self, mapping: ActionMapping) -> None:
        """Add a new action mapping to this controller config."""
        self.action_mappings.append(mapping)

    def set_location(self, channel: int, note: int, x: int, y: int) -> None:
        """Record an X/Y location for a channel/note combination."""
        self.location_mappings[(channel, note)] = (x, y)