from pyoperant import hwio, components, panels, utils
from pyoperant.interfaces import raspi_gpio_, pyaudio_ 
from pyoperant import InterfaceError
import time

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
               3,  #White
               4,  #Left
               5,  #Center
               6,  #Right
               7,  #LED 1
               8,  #LED 2
               9,  #LED 3
               10, #LED 4
               11, #LED 5
               12, #LED 6
               13, #RGB Cue R
               14, #RGB Cue G
               15  #RGB Cue B
               ]

class PiPanel(panels.BasePanel):
    """class for zog boxes """
    def __init__(self,id=None, *args, **kwargs):
        super(PiPanel, self).__init__(*args, **kwargs)
        self.id = id
        self.pwm_outputs = []

        # define interfaces
        self.interfaces['raspi_gpio_'] = raspi_gpio_.RaspberryPiInterface(device_name='zog0')
        self.interfaces['pyaudio'] =  pyaudio_.PyAudioInterface()

        # define inputs
        for in_chan in INPUTS:
            self.inputs.append(hwio.BooleanInput(interface=self.interfaces['raspi_gpio_'],
                                                 params = {'channel': in_chan}))
        for out_chan in OUTPUTS:
            self.outputs.append(hwio.BooleanOutput(interface=self.interfaces['raspi_gpio_'],
                                                 params = {'channel': out_chan}))

        for pwm_out_chan in PWM_OUTPUTS:
            self.pwm_outputs.append(hwio.PWMOutput(interface=self.interfaces['raspi_gpio_'],
                                                  params = {'channel': pwm_out_chan}))

        self.speaker = hwio.AudioOutput(interface=self.interfaces['pyaudio'])

        # assemble inputs into components
        # Standard Peckports
        self.left = components.PeckPort(IR=self.inputs[1],LED=self.pwm_outputs[4],name='l', inverted=False)
        self.center = components.PeckPort(IR=self.inputs[2],LED=self.pwm_outputs[5],name='c', inverted=False)
        self.right = components.PeckPort(IR=self.inputs[3],LED=self.pwm_outputs[6],name='r', inverted=False)
        
        # Hopper
        self.hopper = components.Hopper(IR=self.inputs[0],solenoid=self.outputs[0], inverted=True)


        # House Light
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
        self.speaker.queue('/home/pi/test.wav')
        self.speaker.play()
        time.sleep(1.0)
        self.speaker.stop()
        return True



class Pi1(PiPanel):
    """ Pi1panel"""
    def __init__(self):
        super(Pi1, self).__init__(id=1)


PANELS = {
          "1": Pi1,
          }

BEHAVIORS = ['pyoperant.behavior',
             'glab_behaviors'
            ]

DATA_PATH = '/home/pi/opdat/'

# SMTP_CONFIG

DEFAULT_EMAIL = 'bradtheilman@gmail.com'

SMTP_CONFIG = {'mailhost': 'localhost',
               'toaddrs': [DEFAULT_EMAIL],
               'fromaddr': 'bird@magpi.ucsd.edu',
               'subject': '[pyoperant notice] on magpi',
               'credentials': None,
               'secure': None,
               }
