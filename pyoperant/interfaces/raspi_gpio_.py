import time
import datetime
import logging
#import RPi.GPIO as GPIO

from pyoperant.interfaces import base_
from pyoperant import utils, InterfaceError

logger = logging.getLogger(__name__)

#!/usr/bin/env python

# PCA9685.py
# 2016-01-31
# Public Domain

import time

import pigpio

PCA9685_ADDRESS = 0x55

class PWM:

   """
   This class provides an interface to the I2C PCA9685 PWM chip.

   The chip provides 16 PWM channels.

   All channels use the same frequency which may be set in the
   range 24 to 1526 Hz.

   If used to drive servos the frequency should normally be set
   in the range 50 to 60 Hz.

   The duty cycle for each channel may be independently set
   between 0 and 100%.

   It is also possible to specify the desired pulse width in
   microseconds rather than the duty cycle.  This may be more
   convenient when the chip is used to drive servos.

   The chip has 12 bit resolution, i.e. there are 4096 steps
   between off and full on.
   """

   _MODE1         = 0x00
   _MODE2         = 0x01
   _SUBADR1       = 0x02
   _SUBADR2       = 0x03
   _SUBADR3       = 0x04
   _PRESCALE      = 0xFE
   _LED0_ON_L     = 0x06
   _LED0_ON_H     = 0x07
   _LED0_OFF_L    = 0x08
   _LED0_OFF_H    = 0x09
   _ALL_LED_ON_L  = 0xFA
   _ALL_LED_ON_H  = 0xFB
   _ALL_LED_OFF_L = 0xFC
   _ALL_LED_OFF_H = 0xFD

   _RESTART = 1<<7
   _AI      = 1<<5
   _SLEEP   = 1<<4
   _ALLCALL = 1<<0

   _OCH    = 1<<3
   _OUTDRV = 1<<2

   def __init__(self, pi, bus=1, address=0x40):

      self.pi = pi
      self.bus = bus
      self.address = address

      self.h = pi.i2c_open(bus, address)

      self._write_reg(self._MODE1, self._AI | self._ALLCALL)
      self._write_reg(self._MODE2, self._OCH | self._OUTDRV)

      time.sleep(0.0005)

      mode = self._read_reg(self._MODE1)
      self._write_reg(self._MODE1, mode & ~self._SLEEP)

      time.sleep(0.0005)

      self.set_duty_cycle(-1, 0)
      self.set_frequency(200)

   def get_frequency(self):

      "Returns the PWM frequency."

      return self._frequency

   def set_frequency(self, frequency):

      "Sets the PWM frequency."

      prescale = int(round(25000000.0 / (4096.0 * frequency)) - 1)

      if prescale < 3:
         prescale = 3
      elif prescale > 255:
         prescale = 255

      mode = self._read_reg(self._MODE1);
      self._write_reg(self._MODE1, (mode & ~self._SLEEP) | self._SLEEP)
      self._write_reg(self._PRESCALE, prescale)
      self._write_reg(self._MODE1, mode)

      time.sleep(0.0005)

      self._write_reg(self._MODE1, mode | self._RESTART)

      self._frequency = (25000000.0 / 4096.0) / (prescale + 1)
      self._pulse_width = (1000000.0 / self._frequency)

   def set_duty_cycle(self, channel, percent):

      "Sets the duty cycle for a channel.  Use -1 for all channels."

      steps = int(round(percent * (4096.0 / 100.0)))

      if steps < 0:
         on = 0
         off = 4096
      elif steps > 4095:
         on = 4096
         off = 0
      else:
         on = 0
         off = steps

      if (channel >= 0) and (channel <= 15):
         self.pi.i2c_write_i2c_block_data(self.h, self._LED0_ON_L+4*channel,
            [on & 0xFF, on >> 8, off & 0xFF, off >> 8])

      else:
         self.pi.i2c_write_i2c_block_data(self.h, self._ALL_LED_ON_L,
            [on & 0xFF, on >> 8, off & 0xFF, off >> 8])

   def set_pulse_width(self, channel, width):

      "Sets the pulse width for a channel.  Use -1 for all channels."

      self.set_duty_cycle(channel, (float(width) / self._pulse_width) * 100.0)

   def cancel(self):

      "Switches all PWM channels off and releases resources."

      self.set_duty_cycle(-1, 0)
      self.pi.i2c_close(self.h)

   def _write_reg(self, reg, byte):
      self.pi.i2c_write_byte_data(self.h, reg, byte)

   def _read_reg(self, reg):
      return self.pi.i2c_read_byte_data(self.h, reg)


# Raspberry Pi GPIO Interface for Pyoperant

class RaspberryPiInterface(base_.BaseInterface):
    """ Opens Raspberry Pi GPIO ports for operant interface """

    def __init__(self, device_name, inputs=None, outputs=None,  *args, **kwargs):
        super(RaspberryPiInterface, self).__init__(*args, **kwargs)

        self.device_name = device_name
        self.pi = pigpio.pi(port=7777)

        if not self.pi.connected:
            logger.debug("PIGPIO Not Connected...")

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
        #GPIO.setmode(GPIO.BCM)
        # Setup PWM
        self.pwm = PWM(self.pi, address=PCA9685_ADDRESS)
        self.pwm.set_frequency(240)


    def close(self):
        logger.debug("Closing %s")
        self.pi.stop()

    def _config_read(self, channel, **kwargs):
        self.pi.set_mode(channel, pigpio.INPUT)
        
    def _config_write(self, channel, **kwargs):
        self.pi.set_mode(channel, pigpio.OUTPUT)

    def _read_bool(self, channel, **kwargs):
        while True:
            try: 
                v = self.pi.read(channel)
                break
            except:
                RaspberryPiException("Could not read GPIO")

        return v == 1

    def _write_bool(self, channel, value, **kwargs):
        if value:
            self.pi.write(channel, 1)
        else:
            self.pi.write(channel, 0)

    def _write_pwm(self, channel, value, **kwargs):
        self.pwm.set_duty_cycle(channel, value)
        return value

    def _poll2(self, channel, timeout=None, suppress_longpress=True, **kwargs):
        ''' runs a loop, querying for transitions '''
        date_fmt = '%Y-%m-%d %H:%M:%S.%f'
        cb1 = self.pi.callback(channel, pigpio.RISING_EDGE)
        if timeout is not None:
            start = time.time()
        print('Starting poll')
        while True:
            if cb1.tally() > 0:
                print(cb1.tally())
                cb1.reset_tally()
                cb1.cancel()
                return datetime.datetime.now()
            if timeout is not None:
                if time.time() - start >= timeout:
                    cb1.reset_tally()
                    cb1.cancel()
                    return None

    def _poll(self, channel, timeout=None, suppress_longpress=True, **kwargs):
        date_fmt = '%Y-%m-%d %H:%M:%S.%f'
        if timeout is not None:
            start = time.time()
        if self.pi.wait_for_edge(channel, pigpio.RISING_EDGE, timeout):
            return datetime.datetime.now()
        else:
            return None

    def _callback(self, channel, func=None, **kwargs):
        date_fmt = '%Y-%m-%d %H:%M:%S.%f'
        if func:
            return self.pi.callback(channel, pigpio.RISING_EDGE, func)
        else:
            return self.pi.callback(channel, pigpio.RISING_EDGE)

