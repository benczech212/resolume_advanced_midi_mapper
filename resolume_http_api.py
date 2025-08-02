import requests
import logging


def fetch_composition(resolume_host, resolume_port):
    """Retrieve the full composition structure from the Resolume HTTP API.

    Returns a dict on success or ``None`` on failure.
    """
    url = f"http://{resolume_host}:{resolume_port}/api/v1/composition"
    logging.info(f"Fetching composition from {url}")
    try:
        headers = {"Content-Type": "application/json"}
        response = requests.get(url, headers=headers, timeout=2)
        if response.status_code == 200:
            return response.json()
        else:
            logging.warning(f"⚠️ Failed to fetch composition: {response.status_code}")
            return None
    except Exception as e:
        logging.error(f"⚠️ Error fetching composition: {e}")
        return None


def extract_groups(data):
    """Flatten the Resolume layer/group structure into a list of dicts.

    Each entry contains group name, group index, layer index and layer name.
    """
    layergroups = data.get("layergroups", [])
    all_layers = {layer["id"]: layer for layer in data.get("layers", [])}
    groups = []
    layer_id_map = {}
    all_layer_ids = list(all_layers.keys())
    for layer_index, lid in enumerate(all_layer_ids):
        layer_id_map[lid] = layer_index + 1  # Start from 1 for Resolume compatibility
    for group_index, group in enumerate(layergroups):
        group_index += 1
        name = group.get("name", {}).get("value", f"Group {group_index}")
        layer_ids = [layer.get("id") for layer in group.get("layers", [])]
        layer_details = [
            (
                name,
                group_index,
                layer_id_map[lid],
                lid,
                all_layers[lid]["name"]["value"],
            )
            for lid in layer_ids
            if lid in all_layers
        ]
        for group_name, group_idx, layer_index, lid, lname in layer_details:
            groups.append(
                {
                    "group": group_name,
                    "group_index": group_idx,
                    "layer_index": layer_index,
                    "layer_id": lid,
                    "layer_name": lname,
                }
            )
    return groups


def classify_layer(name):
    """Classify a layer name into one or more types (Fill/Effects/Color/Transform)."""
    lname_lower = name.lower()
    layer_type = []
    emoji = []
    if "fills" in lname_lower:
        layer_type.append("Fill Layer")
        emoji.append("🔴")
    if "effects" in lname_lower:
        layer_type.append("Effects Layer")
        emoji.append("🟣")
    if "colors" in lname_lower:
        layer_type.append("Color Layer")
        emoji.append("🟡")
    if "transforms" in lname_lower:
        layer_type.append("Transform Layer")
        emoji.append("🟢")
    return ", ".join(layer_type), " ".join(emoji)


def process_composition(resolume_host, resolume_port):
    """Fetch and process composition info into a list of layer dicts.

    Each entry includes group, group_index, layer_index, layer_name,
    layer_type and emoji representing the type.
    """
    data = fetch_composition(resolume_host, resolume_port)
    if not data:
        return []
    groups = extract_groups(data)
    processed_data = []
    for group in groups:
        layer_name = group["layer_name"]
        layer_type, emoji = classify_layer(layer_name)
        processed_data.append(
            {
                "group": group["group"],
                "group_index": group["group_index"],
                "layer_index": group["layer_index"],
                "layer_name": layer_name,
                "layer_type": layer_type,
                "emoji": emoji,
            }
        )
    return processed_data
