import requests
from typing import Dict, List, Tuple, Any, Optional
import logging

log = logging.getLogger(__name__)

def fetch_composition(resolume_host: str, resolume_port: int, timeout: float = 2.0) -> Optional[Dict]:
    url = f"http://{resolume_host}:{resolume_port}/api/v1/composition"
    try:
        headers = {"Content-Type": "application/json"}
        resp = requests.get(url, headers=headers, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
        else:
            log.warning("Failed to fetch composition: %s", resp.status_code)
            return None
    except Exception as e:
        log.warning("Error fetching composition from %s: %s", url, e)
        return None

def _classify_types(layer_name: str) -> List[str]:
    t: List[str] = []
    n = (layer_name or "").lower()
    if "fills" in n:
        t.append("fills")
    if "effects" in n:
        t.append("effects")
    if "colors" in n:
        t.append("colors")
    if "transforms" in n:
        t.append("transforms")
    return t

def extract_groups_layers(api_json: Dict) -> List[Dict[str, Any]]:
    """
    Returns rows of:
      {
        "group": str, "group_index": int, "layer_index": int, "layer_id": str,
        "layer_name": str, "types": [...], "clips": [int], "stop_clip": Optional[int]
      }
    """
    if not api_json:
        return []

    layergroups = api_json.get("layergroups", [])
    all_layers_by_id: Dict[str, Dict] = {layer["id"]: layer for layer in api_json.get("layers", [])}

    # global 1-based index across all layers in order
    all_layer_ids = list(all_layers_by_id.keys())
    layer_id_to_index: Dict[str, int] = {lid: i + 1 for i, lid in enumerate(all_layer_ids)}

    results: List[Dict[str, Any]] = []
    for group_idx_0, group in enumerate(layergroups):
        group_index = group_idx_0 + 1
        group_name = group.get("name", {}).get("value", f"Group {group_index}")
        layer_ids = [l.get("id") for l in group.get("layers", [])]
        for lid in layer_ids:
            if lid not in all_layers_by_id:
                continue
            layer_obj = all_layers_by_id[lid]
            layer_name = layer_obj.get("name", {}).get("value", f"Layer {layer_id_to_index.get(lid, 0)}")

            clips: List[int] = []
            stop_clip_consecutive = 0
            first_stop_clip_index: Optional[int] = None
            for idx, clip in enumerate(layer_obj.get("clips", [])):
                name = (clip.get("name") or {}).get("value", "")
                if name == "":
                    # stop clip
                    if first_stop_clip_index is None:
                        first_stop_clip_index = idx + 1  # 1-based
                    stop_clip_consecutive += 1
                    if stop_clip_consecutive >= 3:
                        break
                    continue
                # real clip
                stop_clip_consecutive = 0
                clips.append(idx + 1)

            results.append({
                "group": group_name,
                "group_index": group_index,
                "layer_index": layer_id_to_index.get(lid, 0),
                "layer_id": lid,
                "layer_name": layer_name,
                "types": _classify_types(layer_name),
                "clips": clips,
                "stop_clip": first_stop_clip_index
            })

    return results

def populate_deck_manager(deck_mgr, api_json: Dict) -> None:
    rows = extract_groups_layers(api_json)

    by_group_key: Dict[Tuple[int, str], List[Dict]] = {}
    for r in rows:
        key = (r["group_index"], r["group"])
        by_group_key.setdefault(key, []).append(r)

    for (g_index, g_name), items in by_group_key.items():
        deck_mgr.upsert_group(g_index, g_name)
        for it in items:
            deck_mgr.upsert_layer(
                g_index,
                it["layer_index"],
                it["layer_name"],
                clips=it.get("clips") or [],
                stop_clip=it.get("stop_clip"),
            )
