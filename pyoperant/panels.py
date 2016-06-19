## Panel classes

class BasePanel(object):
    """Returns a panel instance.

    This class should be subclassed to define a local panel configuration.

    To build a panel, do the following in the __init__() method of your local
        subclass:

    1. add instances of the necessary interfaces to the 'interfaces' dict
        attribute:
        >>> self.interfaces['comedi'] = comedi.ComediInterface(device_name='/dev/comedi0')

    2. add inputs and outputs to the 'inputs' and 'outputs' list attributes:
        >>> for in_chan in range(4):
                self.inputs.append(hwio.BooleanInput(interface=self.interfaces['comedi'],
                                                 params = {'subdevice': 2,
                                                           'channel': in_chan
                                                           },
                                                 )
    3. add components constructed from your inputs and outputs:
        >>> self.hopper = components.Hopper(IR=self.inputs[3],solenoid=self.outputs[4])

    4. assign panel methods needed for operant behavior, such as 'reward':
        >>> self.reward = self.hopper.reward

    5. finally, define a reset() method that will set the entire panel to a
        neutral state:

        >>> def reset(self):
        >>>     for output in self.outputs:
        >>>         output.set(False)
        >>>     self.house_light.write(True)
        >>>     return True

    """
    def __init__(self, *args,**kwargs):

        self.interfaces = {}

        self.inputs = []
        self.outputs = []

    def reset(self):
        """
        Turn everything off (sleep), then ready
        """
        # Should log that nothing is being reset and move on

        self.sleep()
        return self.ready()

    def ready(self):

        return True

    def reward(self):

        pass

    def sleep(self):
        """
        Turn all boolean outputs off
        """
        for output in self.outputs:
            if isinstance(output, hwio.BooleanOutput):
                self.output.write(False)

        return True

    def idle(self):

        return True

    def wake(self):
        """
        Ready the panel
        """

        return self.ready()
