import comedi
import base

class ComediError(Error):
    '''raised for problems communicating with the comedi driver'''
    pass


class ComediInterface(base.BaseInterface):
    """docstring for ComediInterface"""
    def __init__(self,device_name,subdevice,channel,*args,**kwargs):
        super(ComediInterface, self).__init__(*args,**kwargs)
        self.device_name = device_name
        self.read_params = ('subdevice',
                            'channel',
                            )
        self.open()

    def open(self):
        self.device = comedi.comedi_open(self.device_name)
        if self.device < 0:
            raise ComediError('could not open device %s' % self.device_name)

    def close(self):
        s = comedi.comedi_close(self.device)
        if s < 0:
            raise ComediError('could not close device %s(%s)' % (self.device_name, self.device)

    def _read_bool(self,subdevice,channel):
        """ read from comedi port
        """
        (s,v) = comedi.comedi_dio_read(self.device,subdevice,channel)
        if s:
            return (not v)
        else:
            raise ComediError('could not read from device "%s", subdevice %s, channel %s' % (self.device,subdevice,channel))

    def _poll(self,subdevice,channel):
        """ runs a loop, querying for pecks. returns peck time or "GoodNite" exception """
        date_fmt = '%Y-%m-%d %H:%M:%S.%f'
        timestamp = subprocess.check_output(['wait4peck', self.device_name, '-s', str(subdevice), '-c', str(channel)])
        return datetime.datetime.strptime(timestamp.strip(),date_fmt)

    def _write_bool(self,subdevice,channel,value):
        """Write to comedi port
        """
        value = not value #invert the value for comedi
        s = comedi.comedi_dio_write(self.device,subdevice,channel,value)
        if s:
            return True
        else:
            raise ComediError('could not write to device "%s", subdevice %s, channel %s' % (self.device,subdevice,channel))

        


