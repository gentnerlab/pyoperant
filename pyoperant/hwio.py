import time
import datetime
from pyoperant import utils

# Classes of operant components
class BaseIO(object):
    """any type of IO device. maintains info on interface for query IO device"""

    def __init__(self, interface=None, params={}, *args, **kwargs):
        self.interface = interface
        self.params = params


class BooleanInput(BaseIO):
    """Class which holds information about inputs and abstracts the methods of
    querying their values

    Keyword arguments:
    interface -- Interface() instance. Must have '_read_bool' method.
    params -- dictionary of keyword:value pairs needed by the interface

    Methods:
    read() -- reads value of the input. Returns a boolean
    poll() -- polls the input until value is True. Returns the time of the change
    """

    def __init__(self, interface=None, params={}, *args, **kwargs):
        super(BooleanInput, self).__init__(
            interface=interface, params=params, *args, **kwargs
        )

        assert hasattr(self.interface, "_read_bool")
        self.config()

    def _clbk(self, gpio, level, tick):
        self.last_time = datetime.datetime.now()
        self.tally += 1

    def config(self):
        self.tally = 0
        try:
            self.interface._callback(func=self._clbk, **self.params)
        except:
            print("callback error")
            return False
        try:
            return self.interface._config_read(**self.params)
        except AttributeError:
            return False

    def read(self):
        """read status"""
        return self.interface._read_bool(**self.params)

    def poll(self, timeout=None):
        """ runs a loop, querying for pecks. returns peck time or "GoodNite" exception """
        return self.interface._poll(timeout=timeout, **self.params)

    def callback(self, func):
        return self.interface._callback(func=func, **self.params)


class BooleanOutput(BaseIO):
    """Class which holds information about outputs and abstracts the methods of
    writing to them

    Keyword arguments:
    interface -- Interface() instance. Must have '_write_bool' method.
    params -- dictionary of keyword:value pairs needed by the interface

    Methods:
    write(value) -- writes a value to the output. Returns the value
    read() -- if the interface supports '_read_bool' for this output, returns
        the current value of the output from the interface. Otherwise this
        returns the last passed by write(value)
    toggle() -- flips the value from the current value
    """

    def __init__(self, interface=None, params={}, *args, **kwargs):
        super(BooleanOutput, self).__init__(
            interface=interface, params=params, *args, **kwargs
        )

        assert hasattr(self.interface, "_write_bool")
        self.last_value = None
        self.config()

    def config(self):
        try:
            return self.interface._config_write(**self.params)
        except AttributeError:
            return False

    def read(self):
        """read status"""
        if hasattr(self.interface, "_read_bool"):
            return self.interface._read_bool(**self.params)
        else:
            return self.last_value

    def write(self, value=False):
        """write status"""
        self.last_value = self.interface._write_bool(value=value, **self.params)
        return self.last_value

    def toggle(self):
        value = not self.read()
        return self.write(value=value)


class AudioOutput(BaseIO):
    """Class which holds information about audio outputs and abstracts the
    methods of writing to them

    Keyword arguments:
    interface -- Interface() instance. Must have the methods '_queue_wav',
        '_play_wav', '_stop_wav'
    params -- dictionary of keyword:value pairs needed by the interface

    Methods:
    queue(wav_filename) -- queues
    read() -- if the interface supports '_read_bool' for this output, returns
        the current value of the output from the interface. Otherwise this
        returns the last passed by write(value)
    toggle() -- flips the value from the current value
    """

    def __init__(self, interface=None, params={}, GPIO_PIN=None, *args, **kwargs):
        super(AudioOutput, self).__init__(
            interface=interface, params=params, *args, **kwargs
        )
        # create an object for boolean GPIO pin to indicate when audio is playing
        self.GPIO_PIN = GPIO_PIN
        assert hasattr(self.interface, "_queue_wav")
        assert hasattr(self.interface, "_play_wav")
        assert hasattr(self.interface, "_stop_wav")

    def queue(self, wav_filename):
        return self.interface._queue_wav(wav_filename)

    def play(self):
        if self.GPIO_PIN is not None:
              self.GPIO_PIN.write(True)
        return self.interface._play_wav()

    def stop(self):
        if self.GPIO_PIN is not None:
              self.GPIO_PIN.write(False)
        return self.interface._stop_wav()

    def play_open_ephys(self, stim, WAV_PADDING):
        """ plays stimuli and lifts pins if possible
        """
        # start wav playback
        self.interface._play_wav()
        if self.GPIO_PIN is not None:
            # wait until WAV padding ends (0 padding to deal with capacitor)
            utils.wait(WAV_PADDING)
            # drop the pin
            self.GPIO_PIN.write(True)
            # wait for the main wav to finish playing
            utils.wait(stim.duration - WAV_PADDING*2)
            # lift the pin
            self.GPIO_PIN.write(False)
            # wait for the wav to end playing
            utils.wait(WAV_PADDING)
        # stop the wav
        return self.interface._stop_wav()



class PWMOutput(BaseIO):
    """Class which abstracts the writing to PWM outputs
   
   Keyword arguments:
    interface -- Interface() instance. Must have '_write_bool' method.
    params -- dictionary of keyword:value pairs needed by the interface

    Methods:
    write(value) -- writes a value to the output. Returns the value
    read() -- if the interface supports '_read_bool' for this output, returns
        the current value of the output from the interface. Otherwise this
        returns the last passed by write(value)
    """

    def __init__(self, interface=None, params={}, *args, **kwargs):
        super(PWMOutput, self).__init__(
            interface=interface, params=params, *args, **kwargs
        )

        assert hasattr(self.interface, "_write_pwm")
        self.last_value = None
        self.config()

    def config(self):
        self.write(0.0)
        return True

    def read(self):
        """read status"""
        return self.last_value

    def write(self, val=0.0):
        """write status"""
        self.last_value = self.interface._write_pwm(value=val, **self.params)
        return self.last_value

    def toggle(self):
        """ flip value """
        new_val = abs(100.0 - self.last_value)
        self.write(new_val)
        return new_val
