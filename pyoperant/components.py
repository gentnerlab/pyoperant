import pyaudio
from pyoperant.hwio import InputChannel, OutputChannel
from pyoperant.utils import Error


class BaseComponent(object):
    """Base class for physcal component"""
    def __init__(self, *args, **kwargs):
        pass


## Hopper ##

class HopperError(Error):
    """raised when there is a detected error with the hopper (1: already up, 2: didn't come up, 3: didn't go down)"""
    pass

class HopperActiveError(HopperError):
    """raised when there is a detected error with the hopper (1: already up, 2: didn't come up, 3: didn't go down)"""
    pass

class HopperInactiveError(HopperError):
    """raised when there is a detected error with the hopper (1: already up, 2: didn't come up, 3: didn't go down)"""
    pass

class Hopper(BaseComponent):
    """Class which holds information about hopper

    has parts: IR Beam (Input) & Solenoid (output)
    """
    def __init__(self,IR,solenoid,*args,**kwargs):
        super(Hopper, self).__init__(*args,**kwargs)
        if isinstance(IR,InputChannel):
            self.IR = IR
        else:
            raise Error('%s is not an input channel' % IR)
        if isinstance(solenoid,OutputChannel):
            self.solenoid = solenoid
        else:
            raise Error('%s is not an output channel' % solenoid)

    def check(self):
        """get status of solenoid & IR beam, throw hopper error if mismatch"""
        IR_status = self.IR.get()
        solenoid_status = self.solenoid.get()
        if IR_status is not solenoid_status:
            if IR_status:
                raise HopperActiveError
            elif solenoid_status:
                raise HopperInactiveError
            else:
                raise HopperError('IR:%s,solenoid:%s' % (IR_status,solenoid_status))
        else:
            return IR_status

    def reset(self):
        """ drop hopper """
        self.solenoid.set(False)
        wait(0.3)
        self.check()
        return True

    def feed(self,dur=2.0,lag=0.3):
        """Performs a feed

        arguments:
        feedsecs -- duration of feed in seconds (default: %default)
        """
        assert lag < dur, "lag (%ss) must be shorter than duration (%ss)" % (lag,dur)
        self.check()
        feed_time = datetime.datetime.now()
        self.solenoid.set(True)
        feed_duration = datetime.datetime.now() - feed_time
        while feed_duration < datetime.timedelta(seconds=dur):
            wait(lag)
            self.check()
            feed_duration = datetime.datetime.now() - feed_time
        self.solenoid.set(False)
        wait(lag) # let the hopper drop
        self.check()
        return (feed_time,feed_duration)

    def reward(self,value=2.0):
        return self.feed(dur=value)

## Peck Port ##

class PeckPort(BaseComponent):
    """Class which holds information about peck ports

    has parts: IR Beam (Input) & LED (output)
    """
    def __init__(self,IR,LED,*args,**kwargs):
        super(PeckPort, self).__init__(*args,**kwargs)
        if isinstance(IR,InputChannel):
            self.IR = IR
        else:
            raise Error('%s is not an input channel' % IR)
        if isinstance(LED,OutputChannel):
            self.LED = LED
        else:
            raise Error('%s is not an output channel' % LED)

    def status(self):
        """get status of solenoid & IR beam, throw hopper error if mismatch"""
        return self.IR.get()

    def off(self):
        """ drop  """
        self.LED.set(False)
        return True

    def on(self):
        """ drop  """
        self.LED.set(True)
        return True

    def flash(self,dur=1.0,isi=0.1):
        """ flash a set of LEDs """
        LED_state = self.LED.get()
        flash_time = datetime.datetime.now()
        flash_duration = datetime.datetime.now() - flash_time
        while flash_duration < datetime.timedelta(seconds=dur):
            self.LED.toggle()
            wait(isi)
            flash_duration = datetime.datetime.now() - flash_time
        self.LED.set(LED_state)
        return (flash_time,flash_duration)

    def wait_for_peck():
        """ poll peck port until there is a peck"""
        return self.IR.poll()

## House Light ##

class GoodNite(Exception):
    """ exception for when the lights should be off """
    pass

class HouseLight(BaseComponent):
    """Class which holds information about the house light

    Inherited from Output
    """
    def __init__(self,light,schedule='sun',*args,**kwargs):
        super(HouseLight, self).__init__(*args,**kwargs)
        if isinstance(light,OutputChannel):
            self.light = light
        else:
            raise Error('%s is not an output channel' % light)
        self.schedule = schedule

    def off(self):
        """ drop  """
        self.light.set(False)
        return True

    def on(self):
        """ drop  """
        self.light.set(True)
        return True

    def check_schedule(self):
        return check_time(self.schedule)

    def set_by_schedule(self):
        if self.check_schedule():
            return self.light.set(True)
        else:
            raise GoodNite()

    def timeout(self,dur=10.0):
        """ turn off light for a few seconds """
        timeout_time = datetime.datetime.now()
        self.light.set(False)
        timeout_duration = datetime.datetime.now() - timeout_time
        while timeout_duration < datetime.timedelta(seconds=dur):
            flash_duration = datetime.datetime.now() - flash_time
        self.light.set(True)
        return (flash_time,flash_duration)

    def punish(self,value=10.0):
        return self.timeout(dur=value)


## Cue Light ##

class CueLight(BaseComponent):
    """Class which holds information about a cue light

    Has parts:
    - Red LED
    - Green LED
    - Blue LED


    """
    def __init__(self,red_LED,green_LED,blue_LED,*args,**kwargs):
        super(CueLight, self).__init__(*args,**kwargs)
        if isinstance(red_LED,OutputChannel):
            self.red_LED = red_LED
        else:
            raise Error('%s is not an output channel' % red_LED)
        if isinstance(green_LED,OutputChannel):
            self.green_LED = green_LED
        else:
            raise Error('%s is not an output channel' % green_LED)
        if isinstance(blue_LED,OutputChannel):
            self.blue_LED = blue_LED
        else:
            raise Error('%s is not an output channel' % blue_LED)

    def red(self):
        self.green_LED.set(False)
        self.blue_LED.set(False)
        return self.red_LED.set(True)
    def green(self):
        self.red_LED.set(False)
        self.blue_LED.set(False)
        return self.green_LED.set(True)
    def blue(self):
        self.red_LED.set(False)
        self.green_LED.set(False)
        return self.blue_LED.set(True)
    def off(self):
        self.red_LED.set(False)
        self.green_LED.set(False)
        self.blue_LED.set(False)


## Perch ##

class Perch(BaseComponent):
    """Class which holds information about a perch

    Has parts:
    - IR Beam (input)
    - Audio device
    """
    def __init__(self,*args,**kwargs):
        super(Perch, self).__init__(*args,**kwargs)

## Audio

class StreamContainer(object):
    def __init__(self,wf,stream):
        self.wf = wf
        self.stream = stream

    def close(self):
        self.stream.close()
        self.wf.close()

    def play(self):
        self.stream.start_stream()

    def __del__(self):
        self.close()

class Audio(BaseComponent):
    """Class which holds information about an audio device"""
    def __init__(self,name='',device_index=0,*args,**kwargs):
        super(Audio, self).__init__(*args,**kwargs)
        self.pa = pyaudio.PyAudio()
        self.device_index = device_index
        self.device_info = self.pa.get_device_info_by_index(self.device_index)

    def __del__(self):
        self.pa.terminate()

    def get_stream(self,wf,start=False):
        """
        """
        def callback(in_data, frame_count, time_info, status):
            data = wf.readframes(frame_count)
            return (data, pyaudio.paContinue)

        stream = self.pa.open(format=self.pa.get_format_from_width(wf.getsampwidth()),
                              channels=wf.getnchannels(),
                              rate=wf.getframerate(),
                              output=True,
                              output_device_index=self.device_index,
                              start=start,
                              stream_callback=callback)

        return stream

    def queue_wav(self,wav_file):
        wf = wave.open(wav_file)
        stream = self.get_stream(wf)
        return StreamContainer(stream=stream,wf=wf)

    def play_wav(self,wav_file):
        wf = wave.open(wav_file)
        stream = self.get_stream(wf,start=True)
        return StreamContainer(stream=stream,wf=wf)