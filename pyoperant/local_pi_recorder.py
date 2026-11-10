# -*- coding: utf-8 -*-
"""
local_pi_recorder.py -- Panel configuration for standalone recording boxes.

A recorder box is a bare Raspberry Pi (4 or newer) with a USB microphone and
an AC relay outlet for the chamber light. It has no operant hardware (no
hopper, ports or speaker); it only runs pyoperant.behavior.lights, which
controls the light schedule and song recording. It otherwise joins the fleet
like any other box.

Select it with `echo 'recorder' | sudo tee /etc/magpi_revision` (see
local.py). Requires pigpiod (the same daemon the Rev D boards use).

The relay is a Digital Loggers-style IoT relay whose control input is wired
to RELAY_PIN and whose lamp is plugged into a NORMALLY-ON outlet. The control
signal is asserted only while the light is off, so a Pi crash or power loss
leaves the light on. See pyoperant.interfaces.gpio_relay_.
"""
import socket

from pyoperant import hwio, components, panels
from pyoperant.interfaces import gpio_relay_, pyaudio_

# BCM numbering. Not used by the Rev D board or the I2C/USB hardware here.
RELAY_PIN = 17

AUDIO_INPUT_DEVICE = 'UMIK-1'


class PiPanel(panels.BasePanel):
    """Panel class for standalone recorder boxes."""
    def __init__(self, id=None, *args, mic_serial=None, relay_pin=RELAY_PIN,
                 **kwargs):
        super(PiPanel, self).__init__(*args, **kwargs)
        self.id = id
        self.mic_serial = mic_serial

        self.interfaces['relay'] = gpio_relay_.GpioRelayInterface(
            device_name='pi', inverted=True)
        self.interfaces['pyaudio'] = pyaudio_.PyAudioInterface()

        self.light_relay = hwio.BooleanOutput(
            interface=self.interfaces['relay'],
            params={'channel': relay_pin})
        self.outputs.append(self.light_relay)
        self.house_light = components.HouseLight(light=self.light_relay)

        self.microphone = hwio.AudioInput(
            interface=self.interfaces['pyaudio'],
            params={'device_name': AUDIO_INPUT_DEVICE,
                    'sample_rate': 48000,
                    'channels': 1})

    def reset(self):
        self.house_light.on()


class Pi1(PiPanel):
    """Panel 1 -- recorder box."""
    def __init__(self, **kwargs):
        super(Pi1, self).__init__(id=1, **kwargs)


PANELS = {
    "1": Pi1,
}

BEHAVIORS = ['pyoperant.behavior',
             'glab_behaviors',
             ]

DATAPATH = '/home/bird/opdat/'

DEFAULT_EMAIL = 'tgentner@ucsd.edu'

SMTP_CONFIG = {'mailhost': '192.168.1.100',
               'toaddrs': [DEFAULT_EMAIL],
               'fromaddr': 'bird@magpi.ucsd.edu',
               'subject': '[pyoperant notice] on %s' % socket.gethostname(),
               'credentials': None,
               'secure': None,
               }
