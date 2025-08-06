import math

# === Envelope Functions ===
def linear(x): return x
def sine_in(x): return 1 - math.cos((x * math.pi) / 2)
def sine_out(x): return math.sin((x * math.pi) / 2)
def expo_in(x): return x ** 2
def expo_out(x): return 1 - (1 - x) ** 2

envelopes = {
    "linear": linear,
    "sine_in": sine_in,
    "sine_out": sine_out,
    "expo_in": expo_in,
    "expo_out": expo_out,
}



class JoystickInput:
    
    def __init__(self, joystick):
        self.joystick = joystick
        self.num_axes = joystick.get_numaxes()
        self.deadzone = [0.05] * self.num_axes
        self.envelopes = ["linear"] * self.num_axes
        self.state = [0.0] * self.num_axes

    def set_deadzone(self, axis, value):
        self.deadzone[axis] = value

    def set_envelope(self, axis, envelope_name):
        if envelope_name in envelopes:
            self.envelopes[axis] = envelope_name

    def process_axis(self, axis_index):
        raw = self.joystick.get_axis(axis_index)
        dz = self.deadzone[axis_index]
        if abs(raw) < dz:
            return 0.0
        norm = (abs(raw) - dz) / (1 - dz)
        norm = max(0.0, min(norm, 1.0))
        transformed = envelopes[self.envelopes[axis_index]](norm)
        return math.copysign(transformed, raw)

    def update_and_send_osc(self, osc_sender):
        for i in range(self.num_axes):
            new_val = self.process_axis(i)
            if abs(new_val - self.state[i]) > 0.01:
                osc_sender.send_axis(i, new_val)
                self.state[i] = new_val
