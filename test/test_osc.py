import asyncio
import yaml
from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer
import sys
import os
# Add parent directory to sys.path to allow imports from the folder above
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load config
def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

# Handler to print any incoming OSC messages
def print_handler(address, *args):
    print(f"[OSC-IN] {address} {args}")

async def main():
    cfg = load_config("config.yml")
    osc_cfg = cfg["osc"]

    # Create OSC client (to Resolume's OSC-in)
    client = SimpleUDPClient(osc_cfg["tx_host"], osc_cfg["tx_port"])

    # Set up OSC server (listening to Resolume's OSC-out)
    dispatcher = Dispatcher()
    dispatcher.set_default_handler(print_handler)

    server = AsyncIOOSCUDPServer((osc_cfg["rx_host"], osc_cfg["rx_port"]), dispatcher, asyncio.get_event_loop())
    transport, protocol = await server.create_serve_endpoint()

    print(f"Listening for OSC on {osc_cfg['rx_host']}:{osc_cfg['rx_port']}")
    print(f"Sending test message to {osc_cfg['tx_host']}:{osc_cfg['tx_port']}")

    # Send a test OSC message to Resolume
    client.send_message("/test/message", "Hello, Resolume!")

    print("Press Ctrl+C to exit.")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        transport.close()

if __name__ == "__main__":
    asyncio.run(main())
