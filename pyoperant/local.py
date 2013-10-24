from pyoperant.hwio import BasePanel, AudioDevice, InputChannel, OutputChannel, PeckPort, HouseLight, Hopper

VOGEL_MAP = {
    1: ('/dev/comedi0', 2, 0, 2, 8), # box_id:(subdevice,in_dev,in_chan,out_dev,out_chan)[ii
    2: ('/dev/comedi0', 2, 4, 2, 16),
    3: ('/dev/comedi0', 2, 24, 2, 32),
    4: ('/dev/comedi0', 2, 28, 2, 40),
    5: ('/dev/comedi0', 2, 48, 2, 56),
    6: ('/dev/comedi0', 2, 52, 2, 64),
    7: ('/dev/comedi0', 2, 72, 2, 80),
    8: ('/dev/comedi0', 2, 76, 2, 88),
    }

class VogelBox(BasePanel):
    """docstring for Vogel1"""
    def __init__(self, *args, **kwargs):
        super(VogelBox, self).__init__(*args, **kwargs)
        for in_chan in [ii+VOGEL_MAP[self.id][2] for ii in range(4)]:
            self.inputs.append(InputChannel(interface='comedi',
                                            device_name=VOGEL_MAP[self.id][0],
                                            subdevice=VOGEL_MAP[self.id][1],
                                            channel=in_chan
                                            ))
        for out_chan in [ii+VOGEL_MAP[self.id][4] for ii in range(5)]:
            self.outputs.append(OutputChannel(interface='comedi',
                                              device_name=VOGEL_MAP[self.id][0],
                                              subdevice=VOGEL_MAP[self.id][3],
                                              channel=out_chan))

        self.speaker = AudioDevice(device_index=self.id+4)

        self.left = PeckPort(IR=self.inputs[0],LED=self.outputs[0])
        self.center = PeckPort(IR=self.inputs[1],LED=self.outputs[1])
        self.right = PeckPort(IR=self.inputs[2],LED=self.outputs[2])
        self.house_light = HouseLight(light=self.outputs[3])
        self.hopper = Hopper(IR=self.inputs[3],solenoid=self.outputs[4])

        self.register(self.hopper,'reward')
        self.register(self.house_light,'punish')
        self.register(self.speaker,'play_wav')
    # def reward(self,value=2.0):
    #     self.hopper.reward(value=value)
    # def punish(self,value=10.0):
    #     self.house_light.punish(value=value)
    def reset(self):
        for output in self.outputs:
            output.set(False)


class Vogel1(VogelBox):
    """docstring for Vogel1"""
    def __init__(self, *args, **kwargs):
        self.id = 1
        super(Vogel1, self).__init__(*args, **kwargs)

class Vogel2(VogelBox):
    """docstring for Vogel2"""
    def __init__(self, *args, **kwargs):
        self.id = 2
        super(Vogel2, self).__init__(*args, **kwargs)

class Vogel3(VogelBox):
    """docstring for Vogel1"""
    def __init__(self, *args, **kwargs):
        self.id = 3
        super(Vogel3, self).__init__(*args, **kwargs)

class Vogel4(VogelBox):
    """docstring for Vogel4"""
    def __init__(self, *args, **kwargs):
        self.id = 4
        super(Vogel4, self).__init__(*args, **kwargs)

class Vogel7(VogelBox):
    """docstring for Vogel7"""
    def __init__(self, *args, **kwargs):
        self.id = 7
        super(Vogel7, self).__init__(*args, **kwargs)

class Vogel8(VogelBox):
    """docstring for Vogel8"""
    def __init__(self, *args, **kwargs):
        self.id = 8
        super(Vogel8, self).__init__(*args, **kwargs)
