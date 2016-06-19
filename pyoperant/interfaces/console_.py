import sys
import datetime as dt
from pyoperant.interfaces import base_

class ConsoleInterface(base_.BaseInterface):
    """docstring for ComediInterface"""
    def __init__(self,*args,**kwargs):
        super(ConsoleInterface, self).__init__(*args,**kwargs)

    def _config_read(self, **kwargs):
        """
        """
        pass

    def _config_write(self, **kwargs):
        """
        """
        pass

    def _read(self, default_value=None, prompt='', **kwargs):
        """ read from keyboard input
        """
        if default_value is not None:
            return default_value

        return raw_input(prompt)

    def _write(self, value, **kwargs):
        """ Write to console
        """
        print value

    def _poll(self, timeout=None, **kwargs):

        if timeout is not None:
            prompt = "Timeout?"
        else:
            prompt = "Press enter"
        value = self.read(prompt=prompt, **kwargs)

        if value:
            return dt.datetime.now()
        else:
            return None
