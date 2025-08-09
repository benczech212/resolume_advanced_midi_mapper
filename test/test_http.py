# test_http_composition.py
import yaml
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from libraries.resolume_http import fetch_composition, extract_groups_layers



def load_cfg(path="config.yml"):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

if __name__ == "__main__":
    cfg = load_cfg()
    http_cfg = cfg.get("http_api", {})
    host = http_cfg.get("host", "127.0.0.1")
    port = int(http_cfg.get("port", 8080))
    timeout = float(http_cfg.get("timeout", 2.0))

    data = fetch_composition(host, port, timeout=timeout)
    if not data:
        print("Failed to fetch composition JSON.")
        raise SystemExit(1)

    rows = extract_groups_layers(data)
    print(f"Found {len(rows)} layers across {len(set((r['group_index'], r['group']) for r in rows))} groups.\n")
    for r in rows:
        print(f"[G{r['group_index']}] {r['group']}  |  "
              f"[L{r['layer_index']}] {r['layer_name']}  |  types={r['types']}")
