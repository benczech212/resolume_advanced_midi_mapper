"""Simple OSC receiver that prints all incoming messages.

This script uses ``python-osc``'s :class:`Dispatcher` and
:class:`~pythonosc.osc_server.BlockingOSCUDPServer` to listen for OSC
messages on a specified address and port.  It can be used to test
communication with an OSC sender.  Run this script first, then run
``osc_basic_sender.py`` in another terminal to send test messages.
"""

from pythonosc.dispatcher import Dispatcher
from pythonosc import osc_server


def default_handler(address: str, *args) -> None:
    """Print all received OSC messages.

    Parameters
    ----------
    address : str
        The OSC address pattern of the incoming message.
    *args
        The arguments associated with the OSC message.
    """
    print(f"Received message on {address}: {args}")


def main() -> None:
    """Set up and run the OSC receiver."""
    dispatcher = Dispatcher()
    # Route all messages to the default handler
    dispatcher.set_default_handler(default_handler)

    ip = "127.0.0.1"
    port = 7001
    print(f"Starting OSC receiver on {ip}:{port}…")
    server = osc_server.BlockingOSCUDPServer((ip, port), dispatcher)
    # This will block and handle messages forever
    server.serve_forever()


if __name__ == "__main__":
    main()