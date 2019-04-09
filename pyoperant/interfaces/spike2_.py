from pyoperant.interfaces import base_


class Spike2Interface(base_.BaseInterface):
    """docstring for Spike2Interface"""

    def __init__(self):
        super(Spike2Interface, self).__init__()

    def open(self):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError

    def _read_bool(self):
        raise NotImplementedError

    def _write_bool(self):
        raise NotImplementedError

    def _queue_wav(self):
        raise NotImplementedError

    def _play_wav(self):
        raise NotImplementedError

    def _stop_wav(self):
        raise NotImplementedError
