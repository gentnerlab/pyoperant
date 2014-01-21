import sys
from pyoperant.interfaces import base

class ConsoleInterface(base.BaseInterface):
    """docstring for ComediInterface"""
    def __init__(self,*args,**kwargs):
        super(ConsoleInterface, self).__init__(*args,**kwargs)
        pass

    def read(self,prompt=''):
        """ read from keyboard input
        """
        return raw_input(prompt)

    def write(self,value):
        """Write to console
        """
        print value
