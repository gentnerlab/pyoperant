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
        raise NotImplementedError

# Classes and functions for testing purposes


import hwio
import components
import interfaces.base_
class TestPanel(BasePanel):

    def __init__(self, *args, **kwargs):
        super(TestPanel, self).__init__(*args, **kwargs)
        self.call_queue = []
        self.id = 0

        self.interfaces['test_interface'] = interfaces.base_.TestBaseInterface()

        for in_chan in range(4):
            self.inputs.append(hwio.TestBooleanInput(interface = self.interfaces['test_interface']))

        for out_chan in range(8):
            self.outputs.append(hwio.TestBooleanOutput(interface = self.interfaces['test_interface']))

        self.speaker =  hwio.TestAudioOutput(interface=self.interfaces['test_interface'])

        # assemble inputs into components
        self.left = components.TestPeckPort(IR=self.inputs[0],LED=self.outputs[0],name='l')
        self.center = components.TestPeckPort(IR=self.inputs[1],LED=self.outputs[1],name='c')
        self.right = components.TestPeckPort(IR=self.inputs[2],LED=self.outputs[2],name='r')
        self.house_light = components.TestHouseLight(light=self.outputs[3])
        self.hopper = components.TestHopper(IR=self.inputs[3],solenoid=self.outputs[4])

        # define reward & punishment methods
        self.reward = self.hopper.reward
        self.punish = self.house_light.punish


    def reset(self):
        self.call_queue.append('reset')
        for output in self.outputs:
            output.write(False)
        self.house_light.on()
        self.hopper.down()

def test_Panel():
    panel = TestPanel()
    panel.reset()

def test_panels():
    test_Panel()