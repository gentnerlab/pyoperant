from pyoperant import hwio, components, panels, utils
from pyoperant.interfaces import comedi_, pyaudio_
from pyoperant import InterfaceError
import time

_ZOG_MAP = {
    1: ('/dev/comedi0', 2, 0, 2, 8), # box_id:(subdevice,in_dev,in_chan,out_dev,out_chan)
    2: ('/dev/comedi0', 2, 4, 2, 16),
    3: ('/dev/comedi0', 2, 24, 2, 32),
    4: ('/dev/comedi0', 2, 28, 2, 40),
    5: ('/dev/comedi0', 2, 48, 2, 56),
    6: ('/dev/comedi0', 2, 52, 2, 64),
    7: ('/dev/comedi0', 2, 72, 2, 80),
    8: ('/dev/comedi0', 2, 76, 2, 88),
    9: ('/dev/comedi1', 2, 0, 2, 8),
    10: ('/dev/comedi1', 2, 4, 2, 16),
    11: ('/dev/comedi1', 2, 24, 2, 32),
    12: ('/dev/comedi1', 2, 28, 2, 40),
    13: ('/dev/comedi1', 2, 48, 2, 56),
    14: ('/dev/comedi1', 2, 52, 2, 64),
    15: ('/dev/comedi1', 2, 72, 2, 80),
    16: ('/dev/comedi1', 2, 76, 2, 88),
    }

dev_name_fmt = 'Adapter 1 (5316) - Output Stream %i'

class ZogAudioInterface(pyaudio_.PyAudioInterface):
    """docstring for ZogAudioInterface"""
    def __init__(self, *args, **kwargs):
        super(ZogAudioInterface, self).__init__(*args,**kwargs)
    def validate(self):
        super(ZogAudioInterface, self).validate()
        if self.wf.getframerate()==48000:
            return True
        else:
            raise InterfaceError('this wav file must be 48kHz')


class ZogPanel(panels.BasePanel):
    """class for zog boxes """
    def __init__(self,id=None, *args, **kwargs):
        super(ZogPanel, self).__init__(*args, **kwargs)
        self.id = id

        # define interfaces
        self.interfaces['comedi'] = comedi_.ComediInterface(device_name=_ZOG_MAP[self.id][0])
        self.interfaces['pyaudio'] = ZogAudioInterface(device_name= (dev_name_fmt % self.id))


        # define inputs
        for in_chan in [ii+_ZOG_MAP[self.id][2] for ii in range(4)]:
            self.inputs.append(hwio.BooleanInput(interface=self.interfaces['comedi'],
                                                 params = {'subdevice': _ZOG_MAP[self.id][1],
                                                           'channel': in_chan
                                                           },
                                                 )
                               )
        for out_chan in [ii+_ZOG_MAP[self.id][4] for ii in range(8)]:
            self.outputs.append(hwio.BooleanOutput(interface=self.interfaces['comedi'],
                                                 params = {'subdevice': _ZOG_MAP[self.id][3],
                                                           'channel': out_chan
                                                           },
                                                   )
                                )
        self.speaker = hwio.AudioOutput(interface=self.interfaces['pyaudio'])

        # assemble inputs into components
        self.left = components.PeckPort(IR=self.inputs[0],LED=self.outputs[0],name='l')
        self.center = components.PeckPort(IR=self.inputs[1],LED=self.outputs[1],name='c')
        self.right = components.PeckPort(IR=self.inputs[2],LED=self.outputs[2],name='r')
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
        # self.speaker.stop()

    def test(self):
        self.reset()
        dur = 2.0
        for output in self.outputs:
            output.write(True)
            utils.wait(dur)
            output.write(False)
        self.reset()
        self.reward(value=dur)
        self.punish(value=dur)
        self.speaker.queue('/usr/local/stimuli/test48k.wav')
        self.speaker.play()
        time.sleep(1.0)
        self.speaker.stop()
        return True



class Zog1(ZogPanel):
    """Zog1 panel"""
    def __init__(self):
        super(Zog1, self).__init__(id=1)

class Zog2(ZogPanel):
    """Zog2 panel"""
    def __init__(self):
        super(Zog2, self).__init__(id=2)

class Zog3(ZogPanel):
    """Zog3 panel"""
    def __init__(self):
        super(Zog3, self).__init__(id=3)

class Zog4(ZogPanel):
    """Zog4 panel"""
    def __init__(self):
        super(Zog4, self).__init__(id=4)

class Zog6(ZogPanel):
    """Zog6 panel"""
    def __init__(self):
        super(Zog6, self).__init__(id=6)

class Zog8(ZogPanel):
    """Zog8 panel"""
    def __init__(self):
        super(Zog8, self).__init__(id=8)

class Zog10(ZogPanel):
    """Zog10 panel"""
    def __init__(self):
        super(Zog10, self).__init__(id=10)

class Zog12(ZogPanel):
    """Zog12 panel"""
    def __init__(self):
        super(Zog12, self).__init__(id=12)

class Zog13(ZogPanel):
    """Zog13 panel"""
    def __init__(self):
        super(Zog13, self).__init__(id=13)

class Zog14(ZogPanel):
    """Zog14 panel"""
    def __init__(self):
        super(Zog14, self).__init__(id=14)

class Zog15(ZogPanel):
    """Zog15 panel"""
    def __init__(self):
        super(Zog15, self).__init__(id=15)

class Zog16(ZogPanel):
    """Zog16 panel"""
    def __init__(self):
        super(Zog16, self).__init__(id=16)


# define the panels with cue lights
class ZogCuePanel(ZogPanel):
    """ZogCuePanel panel"""
    def __init__(self,id=None):
        super(ZogCuePanel, self).__init__(id=id)

        for out_chan in [ii+_ZOG_MAP[self.id][4] for ii in range(5,8)]:
            self.outputs.append(hwio.BooleanOutput(interface=self.interfaces['comedi'],
                                                 params = {'subdevice': _ZOG_MAP[self.id][3],
                                                           'channel': out_chan
                                                           },
                                                   )
                                )
        self.cue = components.RGBLight(red=self.outputs[7],
                                       green=self.outputs[5],
                                       blue=self.outputs[6],
                                       name='cue')

class Zog5(ZogCuePanel):
    """Zog5 panel"""
    def __init__(self):
        super(Zog5, self).__init__(id=5)

class Zog7(ZogCuePanel):
    """Zog7 panel"""
    def __init__(self):
        super(Zog7, self).__init__(id=7)

class Zog9(ZogCuePanel):
    """Zog9 panel"""
    def __init__(self):
        super(Zog9, self).__init__(id=9)

class Zog11(ZogCuePanel):
    """Zog11 panel"""
    def __init__(self):
        super(Zog11, self).__init__(id=11)

class Zog10(ZogCuePanel):
    """Zog10 panel"""
    def __init__(self):
        super(Zog10, self).__init__(id=10)

class Zog12(ZogCuePanel):
    """Zog12 panel"""
    def __init__(self):
        super(Zog12, self).__init__(id=12)


# in the end, 'PANELS' should contain each operant panel available for use

PANELS = {
          "1": Zog1,
          "2": Zog2,
          "3": Zog3,
          "4": Zog4,
          "5": Zog5,
          "6": Zog6,
          "7": Zog7,
          "8": Zog8,
          "9": Zog9,
          "10": Zog10,
          "11": Zog11,
          "12": Zog12,
          "13": Zog13,
          "14": Zog14,
          "15": Zog15,
          "16": Zog16,
          }

BEHAVIORS = ['pyoperant.behavior',
             'glab_behaviors'
            ]

DATA_PATH = '/home/bird/opdat/'

# SMTP_CONFIG

DEFAULT_EMAIL = 'justin.kiggins@gmail.com'

SMTP_CONFIG = {'mailhost': 'localhost',
               'toaddrs': [DEFAULT_EMAIL],
               'fromaddr': 'Zog <bird@zog.ucsd.edu>',
               'subject': '[pyoperant notice] on zog',
               'credentials': None,
               'secure': None,
               }
