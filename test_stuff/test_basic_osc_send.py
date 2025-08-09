# import from folder above in libraries folder
import sys
import os
import time
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..',)))

from libraries.resolume_osc_manager import *

sender = OSCSender(ip="127.0.0.1", port=7000)


while True:
    sender.send_message("/test", "Hello, OSC!")
    time.sleep(1)  # Send a message every second
