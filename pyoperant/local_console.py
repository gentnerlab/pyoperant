from pyoperant import hwio, components, panels
from pyoperant.interface.console import ConsoleInterface



class ConsolePanel(panels.BasePanel):
    """docstring for Console"""
    def __init__(self, *args, **kwargs):
        super(VogelBox, self).__init__(*args, **kwargs)

        self.interfaces = {'console': ConsoleInterface()}

        self.inputs = [hwio.InputChannel(interface=self.interfaces['console'])]
        self.outputs = [hwio.InputChannel(interface=self.interfaces['console'])]

        self.speaker = components.Audio(device_name='dac%i'%self.id)

        self.left = components.PeckPort(IR=self.inputs[0],LED=self.outputs[0])
        self.center = components.PeckPort(IR=self.inputs[0],LED=self.outputs[0])
        self.right = components.PeckPort(IR=self.inputs[0],LED=self.outputs[0])
        self.house_light = components.HouseLight(light=self.outputs[0])
        self.hopper = components.Hopper(IR=self.inputs[0],solenoid=self.outputs[0])

        self.register(self.hopper,'reward')
        self.register(self.house_light,'punish')
        self.register(self.speaker,'play_wav')

PANELS = {"console": Console,
          }

