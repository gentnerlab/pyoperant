class BaseInterface(object):
    """docstring for BaseInterface"""
    def __init__(self, *args, **kwargs):
        super(BaseInterface, self).__init__()
        pass

    def open(self):
        pass

    def close(self):
        pass

    def __del__(self):
        self.close()

class TestBaseInterface(BaseInterface):
    def __init__(self, *args, **kwargs):
        super(TestBaseInterface, self).__init__()
        self.call_queue = []

    def open(self):
        self.call_queue.append('open')

    def close(self):
        self.call_queue.append('close')

    def _config_read(self,subdevice,channel):
        self.call_queue.append('_config_read')

    def _config_write(self,subdevice,channel):
        self.call_queue.append('_config_write')

    def _read_bool(self,subdevice,channel):
        self.call_queue.append('_read_bool')

    def _poll(self,subdevice,channel):
        self.call_queue.append('_poll')

    def _write_bool(self,subdevice,channel,value):
        self.call_queue.append('_write_bool')
        return value

    def _queue_wav(self,wav_file,start=False):
        self.call_queue.append('_queue_wav')

    def _play_wav(self):
        self.call_queue.append('_play_wav')

    def _stop_wav(self):
       self.call_queue.append('_stop_wav')

    def __del__(self):
        self.close()