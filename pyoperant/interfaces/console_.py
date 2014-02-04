import sys
from pyoperant.interfaces import base_

class ConsoleInterface(base_.BaseInterface):
    """docstring for ComediInterface"""
    def __init__(self,*args,**kwargs):
        super(ConsoleInterface, self).__init__(*args,**kwargs)
        pass

    def _read(self,prompt=''):
        """ read from keyboard input
        """
        return raw_input(prompt)

    def _write(self,value):
        """Write to console
        """
        print value
