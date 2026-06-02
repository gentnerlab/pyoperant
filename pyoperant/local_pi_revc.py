# -*- coding: utf-8 -*-
"""
local_pi_revc.py -- Panel configuration for Magpi client Rev C boards.

Rev C boards use a solenoid-driven hopper on GPIO 16. The single PCA9685
at address 0x55 drives all LED and house light outputs at 1000 Hz.

Do not use this file on Rev D boards. The board revision is detected
automatically by local.py reading /etc/magpi_revision.
"""
from pyoperant import hwio, components, panels, utils
from pyoperant.interfaces import raspi_gpio_, pyaudio_
from pyoperant import InterfaceError
import time

# PCA9685 I2C address — must match hardware address pin wiring on the board.
# Rev C has one PCA9685 (lights only). No servo chip.
LIGHTS_PCA9685_ADDRESS = 0x55  # U1: A0, A2, A4 pulled high

INPUTS = [5,   # Hopper IR
          6,   # Left IR
          13,  # Center IR
          26,  # Right IR
          23,  # AUX IR 1
          24,  # AUX IR 2
          25,  # AUX IR 3
          9,   # AUX IR 4
          11,  # AUX IR 5
          10,  # AUX IR 6
          ]

OUTPUTS = [16,  # Hopper solenoid trigger
           ]

PWM_OUTPUTS = [0,   # HOUSELIGHT_R
               1,   # HOUSELIGHT_G
               2,   # HOUSELIGHT_B
               3,   # HOUSELIGHT_W
               4,   # LFT_LED
               5,   # CTR_LED
               6,   # RGT_LED
               7,   # AUX_LED_1
               8,   # AUX_LED_2
               9,   # AUX_LED_3
               10,  # AUX_LED_4
               11,  # AUX_LED_5
               12,  # AUX_LED_6
               13,  # RGB_CUE_R
               14,  # RGB_CUE_G
               15,  # RGB_CUE_B
               ]


class PiPanel(panels.BasePanel):
    """Panel class for Rev C Magpi clients (solenoid hopper)."""
    def __init__(self, id=None, *args, **kwargs):
        super(PiPanel, self).__init__(*args, **kwargs)
        self.id = id
        self.pwm_outputs = []

        # define interfaces
        self.interfaces['raspi_gpio_'] = raspi_gpio_.RaspberryPiInterface(
            device_name='pi',
            lights_address=LIGHTS_PCA9685_ADDRESS)
        # servo_address not passed — Rev C has no servo chip
        self.interfaces['pyaudio'] = pyaudio_.PyAudioInterface()

        # define inputs
        for in_chan in INPUTS:
            self.inputs.append(hwio.BooleanInput(interface=self.interfaces['raspi_gpio_'],
                                                 params={'channel': in_chan}))
        # solenoid output
        for out_chan in OUTPUTS:
            self.outputs.append(hwio.BooleanOutput(interface=self.interfaces['raspi_gpio_'],
                                                   params={'channel': out_chan}))
        # PWM outputs (lights chip only — no servo chip on Rev C)
        for pwm_out_chan in PWM_OUTPUTS:
            self.pwm_outputs.append(hwio.PWMOutput(interface=self.interfaces['raspi_gpio_'],
                                                   params={'channel': pwm_out_chan}))

        self.speaker = hwio.AudioOutput(interface=self.interfaces['pyaudio'])

        # assemble inputs into components
        # pwm_outputs indices: 0=HOUSELIGHT_R, 1=G, 2=B, 3=W,
        #                      4=LFT_LED, 5=CTR_LED, 6=RGT_LED,
        #                      7=AUX_LED_1 .. 12=AUX_LED_6,
        #                      13=RGB_CUE_R, 14=RGB_CUE_G, 15=RGB_CUE_B
        self.left   = components.PeckPort(IR=self.inputs[1], LED=self.pwm_outputs[4],
                                          name='l', inverted=True)
        self.center = components.PeckPort(IR=self.inputs[2], LED=self.pwm_outputs[5],
                                          name='c', inverted=True)
        self.right  = components.PeckPort(IR=self.inputs[3], LED=self.pwm_outputs[6],
                                          name='r', inverted=True)

        # Solenoid hopper on GPIO 16
        self.hopper = components.Hopper(IR=self.inputs[0],
                                        solenoid=self.outputs[0],
                                        inverted=True)

        # House Light (RGBW LED strip via PWM channels 0-3)
        self.house_light = components.LEDStripHouseLight(
            lights=[self.pwm_outputs[0],
                    self.pwm_outputs[1],
                    self.pwm_outputs[2],
                    self.pwm_outputs[3]])

        # RGB cue light (PWM channels 13/14/15 = indices 13/14/15)
        self.cue = components.RGBLight(red=self.pwm_outputs[13],
                                       green=self.pwm_outputs[14],
                                       blue=self.pwm_outputs[15],
                                       name='cue')

        # define reward & punishment methods
        self.reward = self.hopper.reward
        self.punish = self.house_light.punish

    def reset(self):
        self.hopper.down()
        self.house_light.on()

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
    """Panel 1 — Rev C."""
    def __init__(self):
        super(Pi1, self).__init__(id=1)


PANELS = {
    "1": Pi1,
}

BEHAVIORS = ['pyoperant.behavior',
             'glab_behaviors',
             ]

DATAPATH = '/home/pi/opdat/'

DEFAULT_EMAIL = 'bradtheilman@gmail.com'

SMTP_CONFIG = {'mailhost': 'localhost',
               'toaddrs': [DEFAULT_EMAIL],
               'fromaddr': 'bird@magpi.ucsd.edu',
               'subject': '[pyoperant notice] on magpi',
               'credentials': None,
               'secure': None,
               }
