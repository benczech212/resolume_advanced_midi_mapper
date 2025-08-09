from pythonosc.udp_client import SimpleUDPClient
from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import ThreadingOSCUDPServer
import threading


class ResolumeOSCManager:
    def __init__(self, host="127.0.0.1", send_port=7000, receive_port=7001):
        self.host = host
        self.send_port = send_port
        self.receive_port = receive_port
        self.sender = OSCSender(ip=host, port=send_port)
        self.receiver = OSCReceiver(ip=host, port=receive_port)


class OSCSender:
    def __init__(self, ip="127.0.0.1", port=7000):
        self.ip = ip
        self.port = port
        self.client = SimpleUDPClient(ip, port)
    
    def send_message(self, address, *args):
        self.client.send_message(address, args)

    def send_axis(self, axis_id, value):
        self.send_message(f"/czechb/joystick/axis/{axis_id}", value)

    def send_button(self, button_id, pressed):
        self.send_message(f"/czechb/joystick/button/{button_id}", int(pressed))

    def send_hat(self, x, y):
        self.send_message("/czechb/joystick/hat", [x, y])

from pythonosc.dispatcher import Dispatcher
from pythonosc import osc_server
import threading

class OSCReceiver:
    def __init__(self, ip="127.0.0.1", port=7001):
        self.ip = ip
        self.port = port
        # Create a dispatcher and map handlers
        self.dispatcher = Dispatcher()
        self.dispatcher.set_default_handler(self._default_handler)
        # Create a threading OSC server
        self.server = osc_server.ThreadingOSCUDPServer((ip, port), self.dispatcher)
        self.thread = None

    def _default_handler(self, address, *args):
        print(f"Received {address}: {args}")

    def start(self):
        # Start server in a separate thread
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        print(f"Receiver listening on {self.ip}:{self.port}")

    def stop(self):
        self.server.shutdown()
        if self.thread:
            self.thread.join()


    