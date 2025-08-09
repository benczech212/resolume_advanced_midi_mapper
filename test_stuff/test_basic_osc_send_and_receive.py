import sys
import os
import time
import threading

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..',)))

from libraries.resolume_osc_manager import *

osc_manager = ResolumeOSCManager(host="127.0.0.1", send_port=7000, receive_port=7001)
sender = osc_manager.sender
receiver = osc_manager.receiver
test_number = 0

def listen_for_messages():
    receiver.start()
    while True:
        time.sleep(0.1)
        messages = receiver.get_received_messages()
        for message in messages:
            print(f"Received OSC message: {message}")

listener_thread = threading.Thread(target=listen_for_messages, daemon=True)
listener_thread.start()

while True:
    sender.send_message("/test", f"Hello, OSC! {test_number}", test_number)
    test_number += 1
    time.sleep(1)