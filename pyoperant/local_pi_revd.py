# -*- coding: utf-8 -*-
"""
local_pi_revd.py -- Panel configuration for Magpi client Rev D boards.

Rev D boards use a servo-driven hopper on PCA9685 U7 (I2C address 0x45).
The hopper servo channel is defined by HOPPER_SERVO_CHANNEL (channel 0,
HOPPER_CTL). The second PCA9685 runs at 50 Hz. The lights PCA9685 (U1) is
at address 0x55 and runs at 1000 Hz as before.

up_angle and down_angle must be tuned empirically for each physical panel
and updated here. See Section 6.4 of the lab manual for the tuning procedure.

Do not use this file on Rev C boards. The board revision is detected
automatically by local.py reading /etc/magpi_revision.
"""
from pyoperant import hwio, components, panels, utils
from pyoperant.interfaces import raspi_gpio_, pyaudio_
from pyoperant import InterfaceError
import time

# PCA9685 I2C addresses — must match hardware address pin wiring on the board
LIGHTS_PCA9685_ADDRESS = 0x55  # U1: A0, A2, A4 pulled high
SERVO_PCA9685_ADDRESS  = 0x45  # U7: A0, A2 pulled high

INPUTS = [5,   # Hopper IR
          6,   # Left IR
          13,  # Center IR
          26,  # Right IR
          23,  # IR 1
          24,  # IR 2
          25,  # IR 3
          9,   # IR 4
          11,  # IR 5
          10,  # IR 6
          ]

HOPPER_SERVO_CHANNEL = 0  # HOPPER_CTL — PCA9685 U7 channel 0

AUX_SERVO_OUTPUTS = [1,  # AUX_SERVO_1 — PCA9685 U7 channel 1
                     2,  # AUX_SERVO_2 — PCA9685 U7 channel 2
                     3,  # AUX_SERVO_3 — PCA9685 U7 channel 3
                     4,  # AUX_SERVO_4 — PCA9685 U7 channel 4
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
               # channels 11 and 12 are not connected on Rev D
               13,  # RGB_CUE_R
               14,  # RGB_CUE_G
               15,  # RGB_CUE_B
               ]


class PiPanel(panels.BasePanel):
    """Panel class for Rev D Magpi clients (servo hopper)."""
    def __init__(self, id=None, *args, **kwargs):
        super(PiPanel, self).__init__(*args, **kwargs)
        self.id = id
        self.pwm_outputs = []

        # define interfaces
        # RaspberryPiInterface initialises both PCA9685 chips on Rev D:
        #   self.pwm       — U1 at 0x55, 1000 Hz (lights)
        #   self.pwm_servo — U7 at 0x45, 50 Hz  (servo)
        self.interfaces['raspi_gpio_'] = raspi_gpio_.RaspberryPiInterface(
            device_name='pi',
            lights_address=LIGHTS_PCA9685_ADDRESS,
            servo_address=SERVO_PCA9685_ADDRESS)
        self.interfaces['pyaudio'] = pyaudio_.PyAudioInterface()

        # define inputs
        for in_chan in INPUTS:
            self.inputs.append(hwio.BooleanInput(interface=self.interfaces['raspi_gpio_'],
                                                 params={'channel': in_chan}))

        # PWM outputs (lights chip)
        for pwm_out_chan in PWM_OUTPUTS:
            self.pwm_outputs.append(hwio.PWMOutput(interface=self.interfaces['raspi_gpio_'],
                                                   params={'channel': pwm_out_chan}))

        # Servo output — hopper on HOPPER_SERVO_CHANNEL, routed to U7 at 0x45 via servo=True
        self.hopper_servo = hwio.PWMOutput(interface=self.interfaces['raspi_gpio_'],
                                           params={'channel': HOPPER_SERVO_CHANNEL, 'servo': True})

        # Auxiliary servo outputs on channels 1-4 (AUX_SERVO_1 through AUX_SERVO_4)
        self.aux_servos = []
        for ch in AUX_SERVO_OUTPUTS:
            self.aux_servos.append(hwio.PWMOutput(interface=self.interfaces['raspi_gpio_'],
                                                  params={'channel': ch, 'servo': True}))

        self.speaker = hwio.AudioOutput(interface=self.interfaces['pyaudio'])

        # assemble inputs into components
        # pwm_outputs indices: 0=HOUSELIGHT_R, 1=G, 2=B, 3=W,
        #                      4=LFT_LED, 5=CTR_LED, 6=RGT_LED,
        #                      7=AUX_LED_1, 8=AUX_LED_2, 9=AUX_LED_3, 10=AUX_LED_4,
        #                      11=RGB_CUE_R, 12=RGB_CUE_G, 13=RGB_CUE_B
        self.left = components.PeckPort(IR=self.inputs[1], LED=self.pwm_outputs[4],
                                          name='l', inverted=False)
        self.center = components.PeckPort(IR=self.inputs[2], LED=self.pwm_outputs[5],
                                          name='c', inverted=False)
        self.right  = components.PeckPort(IR=self.inputs[3], LED=self.pwm_outputs[6],
                                          name='r', inverted=False)

        # Servo hopper — up_angle and down_angle must be tuned per panel
        self.hopper = components.Hopper(IR=self.inputs[0],
                                        servo=self.hopper_servo,
                                        up_angle=45,
                                        down_angle=10,
                                        inverted=False)

        # House Light (RGBW LED strip via PWM channels 0-3)
        self.house_light = components.LEDStripHouseLight(
            lights=[self.pwm_outputs[0],
                    self.pwm_outputs[1],
                    self.pwm_outputs[2],
                    self.pwm_outputs[3]])

        # RGB cue light (pwm_outputs[11]=RGB_CUE_R, [12]=RGB_CUE_G, [13]=RGB_CUE_B — PCA9685 channels 13/14/15)
        self.cue = components.RGBLight(red=self.pwm_outputs[11],
                                       green=self.pwm_outputs[12],
                                       blue=self.pwm_outputs[13],
                                       name='cue')

        # define reward & punishment methods
        self.reward = self.hopper.reward
        self.punish = self.house_light.punish

    def reset(self):
        self.hopper.down()
        self.house_light.on()



class Pi1(PiPanel):
    """Panel 1 — Rev D."""
    def __init__(self):
        super(Pi1, self).__init__(id=1)


PANELS = {
    "1": Pi1,
}

BEHAVIORS = ['pyoperant.behavior',
             'glab_behaviors',
             ]

DATAPATH = '/home/bird/opdat/'

DEFAULT_EMAIL = 'bradtheilman@gmail.com'

SMTP_CONFIG = {'mailhost': '192.168.1.100',
               'toaddrs': [DEFAULT_EMAIL],
               'fromaddr': 'bird@magpi.ucsd.edu',
               'subject': '[pyoperant notice] on magpi',
               'credentials': None,
               'secure': None,
               }
