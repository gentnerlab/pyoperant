import logging
import numpy as np
from PyDAQmx import *
from pyoperant.interfaces import base_
from pyoperant import utils, InterfaceError


class PyDAQmxInterface(base_.BaseInterface):

    def __init__(self, device_name="default", *args, **kwargs):
        # Initialize the device
        super(PyDAQmxInterface, self).__init__(*args, **kwargs)
        self.device_name = device_name
        self.device_index = None
        # self.stream = None
        # self.wf = None
        # self.callback = None
        self.open()

    def open(self):

        pass

    def close(self):

        pass

    def _config_read(self):

        pass

    def _config_write(self):

        pass

    def _read_bool(self):

        pass

    def _poll(self):

        pass

    def _write_bool(self):

        pass

    def validate(self):

        pass

    def _get_stream(self):

        pass

    def _queue_wav(self):

        pass

    def _play_wav(self):

        pass

    def _stop_wav(self):

        pass
