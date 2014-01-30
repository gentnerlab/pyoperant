import datetime
import subprocess
from pyoperant.utils import is_day, time_in_range, Error
from pyoperant.interfaces import console


class AudioError(Error):
    '''raised for problems with audio'''
    pass


# Classes of operant components
class BaseIO(object):
    """any type of IO device. maintains info on interface for query IO device"""
    def __init__(self,interface=None,params={},*args,**kwargs):
        self.interface = interface
        self.params = params

        if self.interface is None:
            interface = console.ConsoleInterface()

class BooleanInput(BaseIO):
    """Class which holds information about inputs and abstracts the methods of querying them"""
    def __init__(self,interface=None,params={},*args,**kwargs):
        super(InputChannel, self).__init__(interface=interface,params=params,*args,**kwargs)

        assert hasattr(self.interface,'_read_bool')

    def read(self):
        """read status"""
        return self.interface._read_bool(**self.params)

    # def poll(self):
    #     """ runs a loop, querying for pecks. returns peck time or "GoodNite" exception """
    #     return self.interface._poll(**self.params)

class BooleanOutput(BaseIO):
    """Class which holds information about inputs and abstracts the methods of querying them and writeting them"""
    def __init__(self,interface=None,*args,**kwargs):
        super(OutputChannel, self).__init__(interface=interface,params=params,*args,**kwargs)

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
    """docstring for AudioOutput"""
    def __init__(self, interface=None,*args,**kwargs):
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
        





