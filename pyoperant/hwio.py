import datetime
import subprocess
import comedi
from pyoperant.utils import is_day, Error


class AudioError(Error):
    '''raised for problems with audio'''
    pass

class ComediError(Error):
    '''raised for problems communicating with the comedi driver'''
    pass


def comedi_read(device,subdevice,channel):
    """ read from comedi port
    """
    (s,v) = comedi.comedi_dio_read(device,subdevice,channel)
    if s:
        return (not v)
    else:
        raise InputError('could not read from comedi device "%s", subdevice %s, channel %s' % (device,subdevice,channel))

def comedi_write(device,subdevice,channel,value):
    """Write to comedi port
    """
    value = not value #invert the value for comedi
    s = comedi.comedi_dio_write(device,subdevice,channel,value)
    if s:
        return True
    else:
        raise OutputError()

def time_in_range(start, end, x):
    """Return true if x is in the range [start, end]"""
    if start <= end:
        return start <= x <= end
    else:
        return start <= x or x <= end

# Classes of operant components
class BaseIO(object):
    """any type of IO device. maintains info on interface for query IO device"""
    def __init__(self,interface=None,*args,**kwargs):
        self.interface = interface
        for key, value in kwargs.items():
            setattr(self, key, value)
        if self.interface is 'comedi':
            self.device = comedi.comedi_open(self.device_name)
        elif self.interface is None:
            raise Error('you must specificy an interface')
        else:
            raise Error('unknown interface')

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





