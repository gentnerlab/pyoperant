from pyoperant import hwio, components, panels, utils
from pyoperant.interfaces import raspi_gpio_, pyaudio_ 
from pyoperant import InterfaceError
import time

"""_ZOG_MAP = {
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
"""
INPUTS = [5,  # Hopper IR
          6,  # Left IR
          13, # Center IR
          26,  # Right IR
          23, # IR 1
          24, # IR 2
          25, # IR 3
          9,  # IR 4
          11, # IR 5
          10, # IR 6
          ]

OUTPUTS = [16, # Hopper Trigger
          ]


PWM_OUTPUTS = [0,  #Red
               1,  #Green
               2,  #Blue
               3,  #Whitek
               4,  #White
               5
               ]
class PiPanel(panels.BasePanel):
    """class for zog boxes """
    def __init__(self,id=None, *args, **kwargs):
        super(PiPanel, self).__init__(*args, **kwargs)
        self.id = id
        self.pwm_outputs = []

        # define interfaces
        self.interfaces['raspi_gpio_'] = raspi_gpio_.RaspberryPiInterface(device_name='GLOperant000')
        self.interfaces['pyaudio'] =  pyaudio_.PyAudioInterface()



        # define inputs
        for in_chan in INPUTS:
            self.inputs.append(hwio.BooleanInput(interface=self.interfaces['raspi_gpio_'],
                                                 params = {'channel': in_chan
                                                           },
                                                 )
                               )
        for out_chan in OUTPUTS:
            self.outputs.append(hwio.BooleanOutput(interface=self.interfaces['raspi_gpio_'],
                                                 params = {'channel': out_chan
                                                           },
                                                   )
                                )

        for pwm_out_chan in PWM_OUTPUTS:
            self.pwm_outputs.append(hwio.PWMOutput(interface=self.interfaces['raspi_gpio_'],
                                                  params = {'channel': pwm_out_chan}))

        self.speaker = hwio.AudioOutput(interface=self.interfaces['pyaudio'])

        # assemble inputs into components
        self.left = components.PeckPort(IR=self.inputs[1],LED=self.outputs[0],name='l')
        self.center = components.PeckPort(IR=self.inputs[2],LED=self.outputs[0],name='c')
        self.right = components.PeckPort(IR=self.inputs[3],LED=self.outputs[0],name='r')
        #self.house_light = components.HouseLight(light=self.outputs[3])
        self.hopper = components.Hopper(IR=self.inputs[0],solenoid=self.outputs[0])


        self.house_light = components.LEDStripHouseLight(lights=[self.pwm_outputs[0],
                                                                 self.pwm_outputs[1],
                                                                 self.pwm_outputs[2],
                                                                 self.pwm_outputs[3]])
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
        self.speaker.queue('/home/pi/bird_chirp.wav')
        self.speaker.play()
        time.sleep(1.0)
        self.speaker.stop()
        return True



class Pi1(PiPanel):
    """Zog1 panel"""
    def __init__(self):
        super(Pi1, self).__init__(id=1)


PANELS = {
          "1": Pi1,
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
