

class Spike2Interface(object):
    """docstring for Spike2Interface"""
    def __init__(self, arg):
        super(Spike2Interface, self).__init__()
        self.arg = arg

    def open(self):
        pass

    def close(self):
        pass
        
    def _read_bool(self):
        pass

    def _write_bool(self):
        pass

    def _queue_wav(self):
        pass

    def _play_wav(self):
        pass

    def _stop_wav(self):
        pass