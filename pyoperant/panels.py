from pyoperant.utils import Error

## Panel classes

class BasePanel(object):
    """Defines basic class for experiment box.

    This class has a minimal set of information to allow
    reading from input ports and writing to output ports
    of an experimental box.
    """
    def __init__(self, name='',*args,**kwargs):
        self.name = name
        for key, value in kwargs.items():
            setattr(self, key, value)

        self.inputs = []
        self.outputs = []

    def reset(self):
        for output in self.outputs:
            output.write(False)
        return True
