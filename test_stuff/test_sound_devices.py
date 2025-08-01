import sounddevice as sd

def list_input_devices():
    devices = sd.query_devices()
    for idx, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            print(f"{idx}: {device['name']} (Input channels: {device['max_input_channels']})")

list_input_devices()
