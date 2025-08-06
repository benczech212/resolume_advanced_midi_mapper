from pythonosc.udp_client import SimpleUDPClient


class ResolumeOSCManager:
    def __init__(self, host="127.0.0.1", send_port=7000, receive_port=7001):
        self.host = host
        self.send_port = send_port
        self.receive_port = receive_port
        self.sender = OSCSender(ip=host, port=send_port)
        # self.receiver = OSCReceiver(ip=host, port=port)


class OSCSender:
    def __init__(self, ip="127.0.0.1", port=7000):
        self.ip = ip
        self.port = port
        self.client = SimpleUDPClient(ip, port)

    def send_axis(self, axis_id, value):
        self.client.send_message(f"/czechb/joystick/axis/{axis_id}", value)

    def send_button(self, button_id, pressed):
        self.client.send_message(f"/czechb/joystick/button/{button_id}", int(pressed))

    def send_hat(self, x, y):
        self.client.send_message("/czechb/joystick/hat", [x, y])

class OSCReceiver:
    def __init__(self, ip="127.0.0.1", port=7001):
        self.ip = ip
        self.port = port
        self.client = SimpleUDPClient(ip, port)

    def start(self):
        self.client.start()

    def stop(self):
        self.client.stop()  