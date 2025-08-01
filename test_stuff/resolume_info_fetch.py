import requests
import json
import pandas as pd
# import ace_tools as tools

# === Config ===
RESOLUME_HOST = "192.168.4.71"
RESOLUME_HTTP_PORT = 8080



# === Fetch Composition Info ===
def fetch_composition(resolume_url):
    print(f"Fetching composition from {resolume_url}/api/v1/composition")
    try:
        headers = {"Content-Type": "application/json"}
        url = f"{resolume_url}/api/v1/composition"
        response = requests.get(url, headers=headers, timeout=2)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"⚠️ Failed to fetch composition: {response.status_code}")
            return None
    except Exception as e:
        print(f"⚠️ Error fetching composition: {e}")
        return None

def extract_groups(data):
    layergroups = data.get("layergroups", [])
    all_layers = {layer["id"]: layer for layer in data.get("layers", [])}

    groups = []
    layer_id_map = {}
    all_layer_ids = list(all_layers.keys())
    for layer_index, lid in enumerate(all_layer_ids):
        layer_id_map[lid] = layer_index + 1 # Start from 1 for resolume compatibility

    for group_index, group in enumerate(layergroups):
        group_index += 1 # Start from 1 for resolume compatibility
        name = group.get("name", {}).get("value", f"Group {group_index}")
        layer_ids = [layer.get("id") for layer in group.get("layers", [])]
        layer_details = [(name, group_index, layer_id_map[lid], lid, all_layers[lid]["name"]["value"]) for lid in layer_ids if lid in all_layers]
        for group_name, group_idx, layer_index, lid, lname in layer_details:
            groups.append({
                "group": group_name,
                "group_index": group_idx,
                "layer_index": layer_index,
                "layer_id": lid,
                "layer_name": lname
            })
    return groups

def classify_layer(name):
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

def get_composition_info(resolume_host,port=8080):
    resolume_url = f"http://{RESOLUME_HOST}:{port}"
    data = fetch_composition(resolume_url)
    if not data:
        return None

    groups = extract_groups(data)
    for entry in groups:
        ltype, emoji = classify_layer(entry["layer_name"])
        entry["type"] = ltype
        entry["emoji"] = emoji

    df = pd.DataFrame(groups)
    df = df[["group", "group_index", "layer_name", "layer_index", "layer_id", "type", "emoji"]]
    
    # tools.display_dataframe_to_user(name="Grouped Layer Table", dataframe=df)
    return df
