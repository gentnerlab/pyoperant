from pyoperant import hwio, components, panels, utils
from pyoperant.interfaces import comedi_, pyaudio_

_VOGEL_MAP = {
    1: ('/dev/comedi0', 2, 0, 2, 8), # box_id:(subdevice,in_dev,in_chan,out_dev,out_chan)
    2: ('/dev/comedi0', 2, 4, 2, 16),
    3: ('/dev/comedi0', 2, 24, 2, 32),
    4: ('/dev/comedi0', 2, 28, 2, 40),
    5: ('/dev/comedi0', 2, 48, 2, 56),
    6: ('/dev/comedi0', 2, 52, 2, 64),
    7: ('/dev/comedi0', 2, 72, 2, 80),
    8: ('/dev/comedi0', 2, 76, 2, 88),
    }

class VogelPanel(panels.BasePanel):
    """class for vogel boxes """
    def __init__(self,id=None, *args, **kwargs):
        super(VogelPanel, self).__init__(*args, **kwargs)
        self.id = id

        # define interfaces
        self.interfaces['comedi'] = comedi_.ComediInterface(device_name=_VOGEL_MAP[self.id][0])
        self.interfaces['pyaudio'] = pyaudio_.PyAudioInterface(device_name='dac%i'%self.id)


        # define inputs
        for in_chan in [ii+_VOGEL_MAP[self.id][2] for ii in range(4)]:
            self.inputs.append(hwio.BooleanInput(interface=self.interfaces['comedi'],
                                                 params = {'subdevice': _VOGEL_MAP[self.id][1],
                                                           'channel': in_chan
                                                           },
                                                 )
                               )
        for out_chan in [ii+_VOGEL_MAP[self.id][4] for ii in range(8)]:
            self.outputs.append(hwio.BooleanOutput(interface=self.interfaces['comedi'],
                                                 params = {'subdevice': _VOGEL_MAP[self.id][3],
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
            output.write(False)
        self.house_light.on()
        self.hopper.down()

    def test(self):
        print ('reset')
        self.reset()
        dur = 2.0
        for output in self.outputs:
            print ('output %s on' % output)
            output.write(True)
            utils.wait(dur)
            print ('output %s off' % output)
            output.write(False)
        print ('reset')
        self.reset()
        print ('feed')
        self.reward(value=dur)
        print ('timeout')
        self.punish(value=dur)
        print ('queue file')
        self.speaker.queue('/usr/local/stimuli/A1.wav')
        print ('play file')
        self.speaker.play()
        return True


class Vogel1(VogelPanel):
    """Vogel1 panel"""
    def __init__(self):
        super(Vogel1, self).__init__(id=1)

class Vogel2(VogelPanel):
    """Vogel2 panel"""
    def __init__(self):
        super(Vogel2, self).__init__(id=2)

class Vogel3(VogelPanel):
    """Vogel3 panel"""
    def __init__(self):
        super(Vogel3, self).__init__(id=3)

class Vogel4(VogelPanel):
    """Vogel4 panel"""
    def __init__(self):
        super(Vogel4, self).__init__(id=4)

class Vogel6(VogelPanel):
    """Vogel6 panel"""
    def __init__(self):
        super(Vogel6, self).__init__(id=6)

class Vogel7(VogelPanel):
    """Vogel7 panel"""
    def __init__(self):
        super(Vogel7, self).__init__(id=7)

class Vogel8(VogelPanel):
    """Vogel8 panel"""
    def __init__(self):
        super(Vogel8, self).__init__(id=8)


# in the end, 'PANELS' should contain each operant panel available for use

PANELS = {"1": Vogel1,
          "2": Vogel2,
          "3": Vogel3,
          "4": Vogel4,
          "6": Vogel6,
          "7": Vogel7,
          "8": Vogel8,
          }

BEHAVIORS = ['pyoperant.behavior',
             'glab_behaviors',
            ]

DATA_PATH = '/home/bird/opdat/'

# SMTP_CONFIG

DEFAULT_EMAIL = 'justin.kiggins@gmail.com'

SMTP_CONFIG = {'mailhost': 'localhost',
               'toaddrs': [DEFAULT_EMAIL],
               'fromaddr': 'Vogel <bird@vogel.ucsd.edu>',
               'subject': '[pyoperant notice] on vogel',
               'credentials': None,
               'secure': None,
               }
