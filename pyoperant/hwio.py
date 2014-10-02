
# Classes of operant components
class BaseIO(object):
    """any type of IO device. maintains info on interface for query IO device"""
    def __init__(self,interface=None,params={},*args,**kwargs):
        self.interface = interface
        self.params = params

class BooleanInput(BaseIO):
    """Class which holds information about inputs and abstracts the methods of
    querying their values

    Keyword arguments:
    interface -- Interface() instance. Must have '_read_bool' method.
    params -- dictionary of keyword:value pairs needed by the interface

    Methods:
    read() -- reads value of the input. Returns a boolean
    poll() -- polls the input until value is True. Returns the time of the change
    """
    def __init__(self,interface=None,params={},*args,**kwargs):
        super(BooleanInput, self).__init__(interface=interface,params=params,*args,**kwargs)

        assert hasattr(self.interface,'_read_bool')
        self.config()

    def config(self):
        try:
            return self.interface._config_read(**self.params)
        except AttributeError:
            return False

    def read(self):
        """read status"""
        return self.interface._read_bool(**self.params)

    def poll(self):
        """ runs a loop, querying for pecks. returns peck time or "GoodNite" exception """
        return self.interface._poll(**self.params)

class BooleanOutput(BaseIO):
    """Class which holds information about outputs and abstracts the methods of
    writing to them

    Keyword arguments:
    interface -- Interface() instance. Must have '_write_bool' method.
    params -- dictionary of keyword:value pairs needed by the interface

    Methods:
    write(value) -- writes a value to the output. Returns the value
    read() -- if the interface supports '_read_bool' for this output, returns
        the current value of the output from the interface. Otherwise this
        returns the last passed by write(value)
    toggle() -- flips the value from the current value
    """
    def __init__(self,interface=None,params={},*args,**kwargs):
        super(BooleanOutput, self).__init__(interface=interface,params=params,*args,**kwargs)

        assert hasattr(self.interface,'_write_bool')
        self.last_value = None
        self.config()

    def config(self):
        try:
            return self.interface._config_write(**self.params)
        except AttributeError:
            return False

    def read(self):
        """read status"""
        if hasattr(self.interface,'_read_bool'):
            return self.interface._read_bool(**self.params)
        else:
            return self.last_value

    def write(self,value=False):
        """write status"""
        self.last_value = self.interface._write_bool(value=value,**self.params)
        return self.last_value

    def toggle(self):
        value = not self.read()
        return self.write(value=value)

class AudioOutput(BaseIO):
    """Class which holds information about audio outputs and abstracts the
    methods of writing to them

    Keyword arguments:
    interface -- Interface() instance. Must have the methods '_queue_wav',
        '_play_wav', '_stop_wav'
    params -- dictionary of keyword:value pairs needed by the interface

    Methods:
    queue(wav_filename) -- queues
    read() -- if the interface supports '_read_bool' for this output, returns
        the current value of the output from the interface. Otherwise this
        returns the last passed by write(value)
    toggle() -- flips the value from the current value
    """
    def __init__(self, interface=None,params={},*args,**kwargs):
        super(AudioOutput, self).__init__(interface=interface,params=params,*args,**kwargs)

        assert hasattr(self.interface,'_queue_wav')
        assert hasattr(self.interface,'_play_wav')
        assert hasattr(self.interface,'_stop_wav')

    def queue(self,wav_filename):
        return self.interface._queue_wav(wav_filename)

    def play(self):
        return self.interface._play_wav()

    def stop(self):
        return self.interface._stop_wav()

class TestBooleanInput(BooleanInput):
    def __init__(self,interface=None,params={},*args,**kwargs):
        self.call_queue = []
        super(TestBooleanInput, self).__init__(interface=interface,params=params,*args,**kwargs)

    def config(self):
        self.call_queue.append('config')
        return super(TestBooleanInput, self).config()

    def read(self):
        self.call_queue.append('read')
        return super(TestBooleanInput, self).read()

    def poll(self):
        self.call_queue.append('poll')
        return super(TestBooleanInput, self).poll()

class TestBooleanOutput(BooleanOutput):
    def __init__(self,interface=None,params={},*args,**kwargs):
        self.call_queue = []
        super(TestBooleanOutput, self).__init__(interface=interface,params=params,*args,**kwargs)

    def config(self):
        self.call_queue.append('config')
        return super(TestBooleanOutput, self).config()

    def read(self):
        self.call_queue.append('read')
        return super(TestBooleanOutput, self).read()

    def write(self,value=False):
        self.call_queue.append('write')
        return super(TestBooleanOutput, self).write(value=value)

    def toggle(self):
        self.call_queue.append('toggle')
        return super(TestBooleanOutput, self).toggle()

class TestAudioOutput(AudioOutput):
    def __init__(self, interface=None,params={},*args,**kwargs):
        self.call_queue = []
        super(TestAudioOutput, self).__init__(interface=interface,params=params,*args,**kwargs)

    def queue(self,wav_filename):
        self.call_queue.append('queue')
        return super(TestAudioOutput, self).queue(wav_filename)

    def play(self):
        self.call_queue.append('play')
        return super(TestAudioOutput, self).play()

    def stop(self):
        self.call_queue.append('stop')
        return super(TestAudioOutput, self).stop()

def test_BooleanInput():
    from interfaces.base_ import TestBaseInterface
    base_int = TestBaseInterface()
    bool_inp = TestBooleanInput(interface=base_int, params= {'subdevice': 0,
                                                           'channel': 0 })
    assert 'config' in bool_inp.call_queue
    assert '_config_read' in base_int.call_queue
    bool_inp.read()
    assert '_read_bool' in base_int.call_queue
    bool_inp.poll()
    assert '_poll' in base_int.call_queue

def test_BooleanOutput():
    from interfaces.base_ import TestBaseInterface
    base_int = TestBaseInterface()
    bool_out = TestBooleanOutput(interface=base_int, params= {'subdevice': 0,
                                                           'channel': 0 })
    assert 'config' in bool_out.call_queue
    assert '_config_write' in base_int.call_queue
    
    bool_out.read()
    assert '_read_bool' in base_int.call_queue

    bool_out.write(value=False)
    assert '_write_bool' in base_int.call_queue
    assert bool_out.last_value == False

    bool_out.write(value=True)
    assert bool_out.last_value == True

    bool_out.toggle()
    #TestBaseInterface doesn't return a value for _read_bool

def test_AudioOutput():
    from interfaces.base_ import TestBaseInterface
    base_int = TestBaseInterface()
    audio_out = TestAudioOutput(interface=base_int)

    audio_out.queue('filename')
    assert '_queue_wav' in base_int.call_queue
    audio_out.play()
    assert '_play_wav' in base_int.call_queue
    audio_out.stop()
    assert '_stop_wav' in base_int.call_queue

def test_hwio():
    test_BooleanInput()
    test_BooleanOutput()
    test_AudioOutput()