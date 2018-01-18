import time
import datetime
import logging
import RPi.GPIO as GPIO

from pyoperant.interfaces import base_
from pyoperant import utils, InterfaceError

logger = logging.getLogger(__name__)

# Raspberry Pi GPIO Interface for Pyoperant

class RaspberryPiInterface(base_.BaseInterface):
    """ Opens Raspberry Pi GPIO ports for operant interface """

    def __init__(self, device_name, inputs=None, outputs=None,  *args, **kwargs):
        super(RaspberryPiInterface, self).__init__(*args, **kwargs)

        self.device_name = device_name
        self.open()
        self.inputs = []
        self.outputs = []

        if inputs is not None:
            for input_ in inputs:
                self._config_read(*input_)
        if outputs is not None:
            for output in outputs:
                self._config_write(output)

    def __str__(self):
        return "Raspberry Pi device at %s" % (self.device_name)

    def open(self):
        logger.debug("Opening device %s")
        GPIO.setmode(GPIO.BCM)

    def close(self):
        logger.debug("Closing %s")
        GPIO.cleanup()

    def _config_read(self, channel, **kwargs):
        GPIO.setup(channel, GPIO.IN)
        

    def _config_write(self, channel, **kwargs):
        GPIO.setup(channel, GPIO.OUT)

    def _read_bool(self, channel, **kwargs):
        while True:
            try: 
                v = GPIO.input(channel)
                break
            except:
                RaspberryPiException("Could not read GPIO")

        return v == 1

    def _write_bool(self, channel, value, **kwargs):
        if value:
            GPIO.output(channel, GPIO.HIGH)
        else:
            GPIO.output(channel, GPIO.LOW)

    def _poll(self, channel, timeout=None, suppress_longpress=True, **kwargs):
        pass

