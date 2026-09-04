import time
import datetime
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

    def _clbk(self, gpio, level, tick):
        self.last_time = datetime.datetime.now()
        self.tally += 1

    def config(self):
        self.tally = 0
        try:
            self.interface._callback(func=self._clbk, **self.params)
        except:
            print('callback error')
            return False
        try:
            return self.interface._config_read(**self.params)
        except AttributeError:
            return False

    def read(self):
        """read status"""
        return self.interface._read_bool(**self.params)

    def poll(self,timeout=None):
        """ runs a loop, querying for pecks. returns peck time or "GoodNite" exception """
        #orig = self.tally
        #if timeout is not None:
        #    start = time.time()
        #while time.time() - start < timeout:
        #    if self.tally - orig > 0:
        #        return datetime.datetime.now()
        #return None
        return self.interface._poll(timeout=timeout,**self.params)

    def callback(self, func):
        return self.interface._callback(func=func, **self.params)

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

class PWMOutput(BaseIO):
    """Class which abstracts the writing to PWM outputs
   
   Keyword arguments:
    interface -- Interface() instance. Must have '_write_bool' method.
    params -- dictionary of keyword:value pairs needed by the interface

    Methods:
    write(value) -- writes a value to the output. Returns the value
    read() -- if the interface supports '_read_bool' for this output, returns
        the current value of the output from the interface. Otherwise this
        returns the last passed by write(value)
    """
    def __init__(self,interface=None,params={},*args,**kwargs):
        super(PWMOutput, self).__init__(interface=interface,params=params,*args,**kwargs)

        assert hasattr(self.interface,'_write_pwm')
        self.last_value = None
        self.config()

    def config(self):
        self.write(0.0)
        return True

    def read(self):
        """read status"""
        return self.last_value

    def write(self,val=0.0):
        """write status"""
        self.last_value = self.interface._write_pwm(value=val, **self.params)
        return self.last_value

    def toggle(self):
        """ flip value """
        new_val = abs(100.0 - self.last_value)
        self.write(new_val)
        return new_val

class AudioInput(BaseIO):
    """Class which holds information about an audio input device (e.g. a
    USB microphone) and abstracts the methods of recording from it.

    Keyword arguments:
    interface -- Interface() instance. Must have the method
        '_open_input_stream' (see PyAudioInterface._open_input_stream).
        Typically the panel's existing PyAudioInterface instance -- the
        same one used for the speaker's AudioOutput -- rather than a
        second, standalone one, so mic and speaker share one PortAudio
        context per panel.
    params -- dictionary of keyword:value pairs:
        device_name -- substring to match against input-capable device
            names (default: None, meaning "let the interface pick its own
            default input device").
        sample_rate -- Hz (default 44100).
        channels -- requested channel count (default 1); the interface may
            fall back to the device's actual channel count if this isn't
            supported.

    Methods:
    open_stream(chunk_size, callback=None) -- opens the input stream.
        With callback: non-blocking mode, audio arrives via the callback.
        Without: blocking mode, read via read(). Either way, the format
        actually negotiated is recorded on this object afterward as
        .sample_format / .sample_width / .channels_opened.
    read(n_frames) -- blocking read of n_frames from the currently open
        stream. Returns raw bytes -- decoding to a numeric array (e.g.
        numpy) is deliberately left to the caller (pyoperant.song_recording),
        keeping this hardware-abstraction module free of that dependency.
    close() -- stops and closes the currently open stream.
    """
    def __init__(self, interface=None, params={}, *args, **kwargs):
        super(AudioInput, self).__init__(interface=interface, params=params, *args, **kwargs)

        assert hasattr(self.interface, '_open_input_stream')
        self.device_name = params.get('device_name', None)
        self.sample_rate = params.get('sample_rate', 44100)
        self.channels = params.get('channels', 1)

        self._stream = None
        self.sample_format = None
        self.sample_width = None
        self.channels_opened = None

    def open_stream(self, chunk_size=1024, callback=None):
        (self._stream, self.sample_format,
         self.sample_width, self.channels_opened) = self.interface._open_input_stream(
            sample_rate=self.sample_rate,
            channels=self.channels,
            chunk_size=chunk_size,
            device_name=self.device_name,
            callback=callback,
        )
        return self._stream

    def read(self, n_frames, exception_on_overflow=False):
        return self._stream.read(n_frames, exception_on_overflow=exception_on_overflow)

    def close(self):
        if self._stream is not None:
            try:
                self._stream.stop_stream()
            except Exception:
                pass
            self._stream.close()
            self._stream = None


