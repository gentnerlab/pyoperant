import datetime
import subprocess
from pyoperant.utils import is_day, time_in_range, Error


# Classes of operant components
class BaseIO(object):
    """any type of IO device. maintains info on interface for query IO device"""
    def __init__(self,interface=None,params={},*args,**kwargs):
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
    def __init__(self,interface=None,params={},*args,**kwargs):
        super(BooleanInput, self).__init__(interface=interface,params=params,*args,**kwargs)

        assert hasattr(self.interface,'_read_bool')

    def read(self):
        """read status"""
        return self.interface._read_bool(**self.params)

    def poll(self):
        """ runs a loop, querying for pecks. returns peck time or "GoodNite" exception """
        return self.interface._poll(**self.params)

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
    def __init__(self,interface=None,params={},*args,**kwargs):
        super(BooleanOutput, self).__init__(interface=interface,params=params,*args,**kwargs)

        assert hasattr(self.interface,'_write_bool')
        self.last_value = None

    def read(self):
        """read status"""
        if hasattr(self.interface,'_read_bool'):
            return self.interface._read_bool(**self.params)
        else:
            return self.last_value

    def write(self,value=False):
        """write status"""
        self.last_value = self.interface._write_bool(value=value,**self.params)
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
    def __init__(self, interface=None,params={},*args,**kwargs):
        super(AudioOutput, self).__init__(interface=interface,params=params,*args,**kwargs)

        assert hasattr(self.interface,'_queue_wav')
        assert hasattr(self.interface,'_play_wav')
        assert hasattr(self.interface,'_stop_wav')

    def queue(self,wav_filename):
        return self.interface._queue_wav(wav_filename)

    def play(self):
        return self.interface._play_wav()

    def stop(self):
        return self.interface._stop_wav()






