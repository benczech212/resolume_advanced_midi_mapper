"""Simple OSC sender for testing the OSC receiver.

This script creates a :class:`~pythonosc.udp_client.SimpleUDPClient` and
sends a series of test messages to ``127.0.0.1:7001``.  It can be used in
conjunction with ``osc_basic_receiver.py`` to verify that OSC messages
are transmitted and received correctly.  Adjust the IP address and
port as needed to target a different receiver.
"""

from pythonosc.udp_client import SimpleUDPClient
import time


def main() -> None:
    """Send a handful of test OSC messages."""
    ip = "127.0.0.1"
    port = 7001
    client = SimpleUDPClient(ip, port)
    print(f"Sending test messages to {ip}:{port}…")

    for i in range(5):
        # Send a list of arguments; python-osc will handle packing
        client.send_message("/test", [i, "hello"])
        print(f"Sent /test message {i}")
        time.sleep(1)


if __name__ == "__main__":
    main()