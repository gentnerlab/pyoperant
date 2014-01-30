from pyoperant import hwio, components, panels
from pyoperant.interfaces import comedi, pyaudio

_VOGEL_MAP = {
    1: ('/dev/comedi0', 2, 00, 2, 08), # box_id:(subdevice,in_dev,in_chan,out_dev,out_chan)
    2: ('/dev/comedi0', 2, 04, 2, 16),
    3: ('/dev/comedi0', 2, 24, 2, 32),
    4: ('/dev/comedi0', 2, 28, 2, 40),
    5: ('/dev/comedi0', 2, 48, 2, 56),
    6: ('/dev/comedi0', 2, 52, 2, 64),
    7: ('/dev/comedi0', 2, 72, 2, 80),
    8: ('/dev/comedi0', 2, 76, 2, 88),
    }

class VogelBox(panels.BasePanel):
    """docstring for Vogel1"""
    def __init__(self,id, *args, **kwargs):
        super(VogelBox, self).__init__(*args, **kwargs)
        self.id = id

        # define interfaces
        self.interfaces = {'comedi': comedi.ComediInterface(device_name=_VOGEL_MAP[self.id][0]),
                           'pyaudio': pyaudio.PyAudioInterface(device_name='dac%i'%self.id),
                           }

        # define inputs
        for in_chan in [ii+VOGEL_MAP[self.id][2] for ii in range(4)]:
            self.inputs.append(hwio.BooleanInput(interface=self.interfaces['comedi'],
                                                 params = {'subdevice': VOGEL_MAP[self.id][1],
                                                           'channel': in_chan
                                                           },
                                                 )
                               )
        for out_chan in [ii+VOGEL_MAP[self.id][4] for ii in range(5)]:
            self.outputs.append(hwio.BooleanOutput(interface=self.interfaces['comedi'],
                                                 params = {'subdevice': VOGEL_MAP[self.id][3],
                                                           'channel': out_chan
                                                           },
                                                   )
                                )
        self.speaker = hwio.AudioOutput(interface=self.interfaces['pyaudio'])

        # assemble inputs into components
        self.left = components.PeckPort(IR=self.inputs[0],LED=self.outputs[0])
        self.center = components.PeckPort(IR=self.inputs[1],LED=self.outputs[1])
        self.right = components.PeckPort(IR=self.inputs[2],LED=self.outputs[2])
        self.house_light = components.HouseLight(light=self.outputs[3])
        self.hopper = components.Hopper(IR=self.inputs[3],solenoid=self.outputs[4])

        # define reward & punishment methods
        self.reward = self.hopper.reward
        self.punish = self.house_light.punish

    def reset(self):
        for output in self.outputs:
            output.set(False)
        self.house_light.write(True)
        return True


class Vogel1(VogelBox):
    """docstring for Vogel1"""
    def __init__(self):
        super(Vogel1, self).__init__(id=1)

class Vogel2(VogelBox):
    """docstring for Vogel2"""
    def __init__(self):
        super(Vogel2, self).__init__(id=2)

class Vogel3(VogelBox):
    """docstring for Vogel1"""
    def __init__(self):
        super(Vogel3, self).__init__(id=3)

class Vogel4(VogelBox):
    """docstring for Vogel4"""
    def __init__(self):
        super(Vogel4, self).__init__(id=4)

class Vogel7(VogelBox):
    """docstring for Vogel7"""
    def __init__(self):
        super(Vogel7, self).__init__(id=7)

class Vogel8(VogelBox):
    """docstring for Vogel8"""
    def __init__(self):
        super(Vogel8, self).__init__(id=8)


# in the end, 'PANELS' should contain each operant panel available for use

PANELS = {"Vogel1": Vogel1,
          "Vogel2": Vogel2,
          "Vogel3": Vogel3,
          "Vogel4": Vogel4,
          "Vogel7": Vogel7,
          "Vogel8": Vogel8,
          }

