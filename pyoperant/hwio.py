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
    def __init__(self,interface=None,*args,**kwargs):
        self.interface = interface
        for key, value in kwargs.items():
            setattr(self, key, value)

        if self.interface is None:
            interface = console.ConsoleInterface()

class InputChannel(BaseIO):
    """Class which holds information about inputs and abstracts the methods of querying them"""
    def __init__(self,interface=None,*args,**kwargs):
        super(InputChannel, self).__init__(interface=interface,*args,**kwargs)

    def get(self):
        """get status"""
        if self.interface is 'comedi':
              return comedi_read(self.device,self.subdevice,self.channel)
        else:
            raise Error('unknown interface')

    def poll(self):
        """ runs a loop, querying for pecks. returns peck time or "GoodNite" exception """
        if self.interface is 'comedi':
            date_fmt = '%Y-%m-%d %H:%M:%S.%f'
            timestamp = subprocess.check_output(['wait4peck', self.device_name, '-s', str(self.subdevice), '-c', str(self.channel)])
            return datetime.datetime.strptime(timestamp.strip(),date_fmt)
        else:
            raise Error('unknown interface')

class OutputChannel(BaseIO):
    """Class which holds information about inputs and abstracts the methods of querying them and setting them"""
    def __init__(self,interface=None,*args,**kwargs):
        super(OutputChannel, self).__init__(interface=interface,*args,**kwargs)

    def get(self):
        """get status"""
        if self.interface is 'comedi':
            return comedi_read(self.device,self.subdevice,self.channel)
        else:
            raise Error('unknown interface')

    def set(self,value=False):
        """set status"""
        if self.interface is 'comedi':
            return comedi_write(self.device,self.subdevice,self.channel,value)
        else:
            raise Error('unknown interface')

    def toggle(self):
        value = not self.get()
        return self.set(value=value)





