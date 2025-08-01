import requests
import json
import pandas as pd
import logging



def fetch_composition(resolume_host, resolume_port):
    url = f"http://{resolume_host}:{resolume_port}/api/v1/composition"
    print(f"Fetching composition from {url}")
    try:
        headers = {"Content-Type": "application/json"}
        
        response = requests.get(url, headers=headers, timeout=2)
        if response.status_code == 200:
            return response.json()
        else:
            print(f"⚠️ Failed to fetch composition: {response.status_code}")
            print("Please check if Resolume is running and the API is accessible.")
            return None
    except Exception as e:
        print(f"⚠️ Error fetching composition: {e}")
        print("Please check if Resolume is running and the API is accessible.")
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

def process_composition(resolume_host, resolume_port):
    data = fetch_composition(resolume_host, resolume_port)
    groups = extract_groups(data)

    processed_data = []
    for group in groups:
        layer_name = group["layer_name"]
        layer_type, emoji = classify_layer(layer_name)
        processed_data.append({
            "group": group["group"],
            "group_index": group["group_index"],
            "layer_index": group["layer_index"],
            "layer_name": layer_name,
            "layer_type": layer_type,
            "emoji": emoji
        })
    
    return processed_data