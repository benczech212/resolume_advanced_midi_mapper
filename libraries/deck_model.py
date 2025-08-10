import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class LayerInfo:
    index: int
    name: str
    types: List[str]  # e.g., ["fills", "effects", "colors", "transforms"]
    clips: List[int] = field(default_factory=list)          # 1-based clip columns that are NOT stop clips
    stop_clip: Optional[int] = None                         # 1-based first stop clip column, if present

@dataclass
class GroupInfo:
    index: int
    name: str
    layers: Dict[int, LayerInfo] = field(default_factory=dict)

@dataclass
class DeckState:
    name: str
    playing: bool = False
    effects: bool = False
    colors: bool = False
    transform: bool = False
    fill: float = 0.0       # 0..1
    opacity: float = 1.0    # 0..1
    last_changed: float = field(default_factory=time.time)

    def set_playing(self, value: bool):
        if self.playing != value:
            self.playing = value
            self.last_changed = time.time()

    def set_effects(self, value: bool):
        if self.effects != value:
            self.effects = value
            self.last_changed = time.time()

    def set_colors(self, value: bool):
        if self.colors != value:
            self.colors = value
            self.last_changed = time.time()

    def set_transform(self, value: bool):
        if self.transform != value:
            self.transform = value
            self.last_changed = time.time()

    def set_fill(self, value: float):
        v = max(0.0, min(1.0, float(value)))
        if abs(self.fill - v) > 1e-6:
            self.fill = v
            self.last_changed = time.time()

    def set_opacity(self, value: float):
        v = max(0.0, min(1.0, float(value)))
        if abs(self.opacity - v) > 1e-6:
            self.opacity = v
            self.last_changed = time.time()

class DeckManager:
    """
    - Exact match group_to_deck
    - Holds deck states
    - Holds a live model of groups/layers/types (and now clips/stop_clip) from HTTP
    """
    def __init__(self, group_to_deck: Dict[str, str]):
        self.group_to_deck = group_to_deck
        self.decks: Dict[str, DeckState] = {d: DeckState(d) for d in set(group_to_deck.values())}
        self.groups_by_index: Dict[int, GroupInfo] = {}
        self.groups_by_name: Dict[str, GroupInfo] = {}

    # Decks
    def get_deck(self, deck_name: str) -> Optional[DeckState]:
        return self.decks.get(deck_name)

    def all_decks(self):
        return self.decks.values()

    def resolve_group_to_deck(self, group_name: str) -> Optional[str]:
        return self.group_to_deck.get(group_name)

    # Groups/Layers
    @staticmethod
    def _layer_types_from_name(name: str) -> List[str]:
        t: List[str] = []
        n = (name or "").lower()
        if "fills" in n: t.append("fills")
        if "effects" in n: t.append("effects")
        if "colors" in n: t.append("colors")
        if "transforms" in n: t.append("transforms")
        if "opacity" in n: t.append("opacity")
        return t

    def upsert_group(self, group_index: int, group_name: str):
        gi = self.groups_by_index.get(group_index)
        if gi is None:
            gi = GroupInfo(index=group_index, name=group_name)
            self.groups_by_index[group_index] = gi
        else:
            gi.name = group_name
        self.groups_by_name[group_name] = gi

    def upsert_layer(
        self,
        group_index: int,
        layer_index: int,
        layer_name: str,
        *,
        clips: Optional[List[int]] = None,
        stop_clip: Optional[int] = None,
    ):
        gi = self.groups_by_index.get(group_index)
        if gi is None:
            gi = GroupInfo(index=group_index, name=f"Group {group_index}")
            self.groups_by_index[group_index] = gi

        types = self._layer_types_from_name(layer_name)
        li = gi.layers.get(layer_index)
        if li is None:
            li = LayerInfo(
                index=layer_index,
                name=layer_name,
                types=types,
                clips=list(clips or []),
                stop_clip=stop_clip,
            )
            gi.layers[layer_index] = li
        else:
            li.name = layer_name
            li.types = types
            li.clips = list(clips or [])
            li.stop_clip = stop_clip

    def get_group_layers_by_type(self, group_name: str, layer_type: str) -> List[LayerInfo]:
        gi = self.groups_by_name.get(group_name)
        if not gi:
            return []
        return [li for li in gi.layers.values() if layer_type in li.types]
