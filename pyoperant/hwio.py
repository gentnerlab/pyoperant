import time
import datetime
import comedi
import socket
import pyaudio
import wave
import subprocess

class GoodNite(Exception):
    """ exception for when the lights should be off """
    pass

## defining Error classes for operant HW control
class Error(Exception):
    '''base class for exceptions in this module'''
    pass

class AudioError(Error):
    '''raised for problems with audio'''
    pass

class ComediError(Error):
    '''raised for problems communicating with the comedi driver'''
    pass

class OperantError(Error):
    """raised for problems with the operant box"""
    pass

class ResponseDuringFeedError(Error):
    """raised when subject response during feed, suggesting that hopper may be working improperly"""
    pass

class HopperAlreadyUpError(Error):
    """raised when there is a detected error with the hopper (1: already up, 2: didn't come up, 3: didn't go down)"""
    pass

class HopperDidntRaiseError(Error):
    """raised when there is a detected error with the hopper (1: already up, 2: didn't come up, 3: didn't go down)"""
    pass

class HopperDidntDropError(Error):
    """raised when there is a detected error with the hopper (1: already up, 2: didn't come up, 3: didn't go down)"""
    pass

def wait(secs=1.0, final_countdown=0.2,waitfunc=None):
    """Smartly wait for a given time period.

    secs -- total time to wait in seconds
    final_countdown -- time at end of secs to wait and constantly poll the clock
    waitfunc -- optional function to run in a loop during hogCPUperiod

    If secs=1.0 and final_countdown=0.2 then for 0.8s python's time.sleep function will be used,
    which is not especially precise, but allows the cpu to perform housekeeping. In
    the final hogCPUsecs the more precise method of constantly polling the clock
    is used for greater precision.
    """
    #initial relaxed period, using sleep (better for system resources etc)
    if secs>final_countdown:
        time.sleep(secs-final_countdown)
        secs=final_countdown # only this much is now left

    #It's the Final Countdown!!
    #hog the cpu, checking time
    t0=time.time()
    while (time.time()-t0)<secs:
        #let's see if any events were collected in meantime
        try:
            waitfunc()
        except:
            pass

def comedi_read(device,subdevice,channel):
    """ read from comedi port
    """
    (s,v) = comedi.comedi_dio_read(device,subdevice,channel)
    if s:
        return (not v)
    else:
        raise InputError('could not read from comedi device "%s", subdevice %s, channel %s' % (device,subdevice,channel))

def comedi_write(device,subdevice,channel,value):
    """Write to comedi port
    """
    val = not value #invert the value for comedi
    return comedi.comedi_dio_write(device,subdevice,channel,value)

def time_in_range(start, end, x):
    """Return true if x is in the range [start, end]"""
    if start <= end:
        return start <= x <= end
    else:
        return start <= x or x <= end


def check_time(schedule,fmt="%H:%M"):
    """ determine whether trials should be done given the current time and the light schedule

    returns Boolean if current time meets schedule

    schedule=['sun'] will change lights according to local sunrise and sunset

    schedule=[('07:00','17:00')] will have lights on between 7am and 5pm
    schedule=[('06:00','12:00'),('18:00','24:00')] will have lights on between

    """
    for epoch in schedule:
        if 'sun' in epoch:
            if is_day():
                return True
        else:
            now = dt.datetime.time(dt.datetime.now())
            start = dt.datetime.time(dt.datetime.strptime(epoch[0],fmt))
            end = dt.datetime.time(dt.datetime.strptime(epoch[1],fmt))
            if time_in_range(start,end,now):
                return True
    return False


# Classes of operant components
class IO(object):
    """docstring for IO"""
    def __init__(self,interface=None,*args,**kwargs):
        super(IO, self).__init__()
        for key, value in kwargs.items():
            setattr(self, key, value)
        if self.interface is 'comedi':
            self.device = comedi.comedi_open(self.dev_name)
        elif self.interface is None:
            raise Error('you must specificy an interface')
        else:
            raise Error('unknown interface')

class InputChannel(IO):
    """Class which holds information about inputs"""
    def __init__(self,interface=None,*args,**kwargs):
        super(InputChannel, self).__init__()

    def get(self):
        """get status"""
        if self.interface is 'comedi':
            return comedi_read(self.device,self.subdevice,self.channel)
        else:
            raise Error('unknown interface')

    def poll(self):
        """ runs a loop, querying for pecks. returns peck time or "GoodNite" exception """
        if self.interface is 'comedi':
            date_fmt = '%Y-%m-%d %H:%M:%S.%f'
            timestamp = subprocess.check_output(['wait4peck', self.device_name, '-s', str(self.subdevice), '-c', str(self.channel)])
            return datetime.datetime.strptime(timestamp.strip(),date_fmt)
        else:
            raise Error('unknown interface')

class OutputChannel(IO):
    """Class which holds information about inputs"""
    def __init__(self,interface=None,*args,**kwargs):
        super(OutputChannel, self).__init__()
            setattr(self, key, value)

    def get(self):
        """get status"""
        if self.interface is 'comedi':
            return comedi_read(self.device,self.subdevice,self.channel)
        else:
            raise Error('unknown interface')

    def set(self,value=False):
        """set status"""        
        if self.interface is 'comedi':
            return comedi_write(self.device,self.subdevice,self.channel,value)
        else:
            raise Error('unknown interface')

    def toggle(self):
        value = not self.get()
        return self.set(value=value)
        

class Component(object):
    """docstring for Component"""
    def __init__(self, arg):
        super(Component, self).__init__()
        pass

class Hopper(Component):
    """Class which holds information about hopper

    has parts: IR Beam (Input) & Solenoid (output)
    """
    def __init__(self,IR,solenoid):
        super(Hopper, self).__init__()
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
                raise FeederActiveError
            elif solenoid_status:
                raise FeederInactiveError
            else:
                raise FeederError('IR:%s,solenoid:%s' % (IR_status,solenoid_status))
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
        self.check()
        feed_time = datetime.datetime.now()
        self.solenoid.set(True)
        feed_duration = datetime.datetime.now() - feed_time
        while feed_duration < datetime.timedelta(seconds=dur):
            self.check()
            feed_duration = datetime.datetime.now() - feed_time
        self.solenoid.set(False)
        wait(lag) # let the hopper drop
        self.check()
        return (feed_time,feed_duration)

    def reward(self,value=2.0):
        return self.feed(dur=value)

class PeckPort(Component):
    """Class which holds information about peck ports

    has parts: IR Beam (Input) & LED (output)
    """
    def __init__(self,IR,LED):
        super(PeckPort, self).__init__()
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
        pass

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


class HouseLight(Component):
    """Class which holds information about the house light

    Inherited from Output
    """    
    def __init__(self,light,schedule=[]):
        super(HouseLight, self).__init__()
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
        return self.light.set(check_time(self.schedule))

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

class Perch(Component):
    """Class which holds information about a perch

    Has parts:
    - IR Beam (input)
    - Audio device
    """
    def __init__(self):
        super(Perch, self).__init__()

class CueLight(Component):
    """Class which holds information about a cue light

    Has parts:
    - Red LED
    - Green LED
    - Blue LED


    """
    def __init__(self,red_LED,green_LED,blue_LED):
        super(CueLight, self).__init__()
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

class StreamContainer(object):
    def __init__(self,wf,stream):
        super(StreamContainer, self).__init__()
        self.wf = wf
        self.stream = stream

    def close(self):
        self.stream.close()
        self.wf.close()

    def play(self):
        self.stream.start_stream()

    def __del__(self):
        self.close()

class AudioDevice(Component):
    """Class which holds information about an audio device"""
    def __init__(self,name='',device_index=0):
        super(AudioDevice, self).__init__()
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


## Panel classes
class Panel(object):
    """Defines basic class for experiment box.

    This class has a minimal set of information to allow
    reading from input ports and writing to output ports
    of an experimental box.
    """
    def __init__(self, name='', **kwargs):
        super(Panel, self).__init__()
        self.name = name

    def read(self,port_id):
        """Reads value of input port on this box.

        Keyword arguments:
        port_id -- int of port to query

        Returns boolean value of port or raises OperantError
        """
        # port_id is the local port number 1-4
        r =  operant_read(self.m,self.box_id,port_id)
        if r < 0 :
            raise OperantError("error reading from input port %i on %s box %i" % (port_id, self.m.name, self.box_id))
        return r

    def write(self,port_id,val=None):
        """Writes value of output port on this box.

        Keyword arguments:
        port_id -- int of port to write or query
        val     -- value to assign to port (default=None)

        If no value is assigned for val, then current value is returned.
        Returns 1 for successful write or raises OperantError
        """
        r = operant_write(self.m,self.box_id,port_id,val)
        if r < 0 :
            raise OperantError("error writing to output port %i on %s box %i" % (port_id, self.m.name, self.box_id))
        return r

    def toggle(self,port_id):
        """ Toggles value of output port based on current value"""
        current_val = self.write(port_id)
        if current_val > -1:
            r = self.write(port_id, not current_val)
            if r < 0 :
                raise OperantError("error writing to output port %i on %s box %i" % (port_id, self.m.name, self.box_id))
            return r
        else:
            raise OperantError("error reading from output port %i on %s box %i" % (port_id, self.m.name, self.box_id))

    def reset(self):
        ports = range(1,9)
        for p in ports:
            self.write(p,False)

class OperantPanel(Panel):
    """Defines class for an operant box.

    Inherited from Panel() class.

    Major methods:
    timeout --
    feed --

    """
    def __init__(self,box_id):
        Panel.__init__(self,box_id)
        #
        self.dio = {'LED_left': 1,
                    'LED_center': 2,
                    'LED_right': 3,
                    'light': 4,
                    'hopper': 5,
                    'IR_left': 1,
                    'IR_center': 2,
                    'IR_right': 3,
                    'IR_hopper': 4,
                    }

        self.dio['LED_all'] = (self.dio['LED_left'],
                               self.dio['LED_center'],
                               self.dio['LED_right'],
                               )

        self.audio = AudioDevice(self.box_id)

    def feed(self, feedsecs=2.0, hopper_lag=0.3):
        """Performs a feed for this box.

        arguments:
        feedsecs -- duration of feed in seconds (default: %default)
        """
        if self.read(self.dio['IR_hopper']):
            raise HopperAlreadyUpError(self.box_id) # hopper already up
        tic = datetime.datetime.now()
        self.write(self.dio['hopper'], True)
        feed_timedelta = datetime.datetime.now() - tic
        while feed_timedelta < datetime.timedelta(seconds=feedsecs):
            if self.read(self.dio['LED_center']):
                raise ResponseDuringFeedError(self.box_id)
            if feed_timedelta > datetime.timedelta(seconds=hopper_lag) and not self.read(self.dio['IR_hopper']):
                raise HopperDidntRaiseError(self.box_id) # hopper not up during feed
            feed_timedelta = datetime.datetime.now() - tic

        self.write(self.dio['hopper'], False)
        wait(hopper_lag) # let the hopper drop
        toc = datetime.datetime.now()
        if self.read(self.dio['IR_hopper']):
            raise HopperDidntDropError(self.box_id) # hopper still up after feed

        return (tic, toc)

    def timeout(self, timeoutsecs=10):
        """Turns off the light in the box temporarily

        :param timeoutsecs: Duration of timeout in seconds
        :type  timeoutsecs: float

        :return: epoch of timeout
        :rtype: (datetime, datetime)
        """

        tic = datetime.datetime.now()
        self.write(self.dio['light'], False)
        wait(timeoutsecs)
        toc = datetime.datetime.now()
        self.write(self.dio['light'], True)

        return (tic, toc)

    def lights_on(self,on=True):
        self.write(self.dio['light'],on)

    def lights_off(self,off=True):
        on = not off
        self.write(self.dio['light'],on)

    def LED(self, port_ids=(1,2,3), dur=2.0):
        for p in port_ids:
            self.write(p,True)
        wait(dur)
        for p in port_ids:
            self.write(p,False)
        return True

    def flash(self,port_ids=(1,2,3),dur=2.0,isi=0.1):
        """ flash a set of LEDs """
        if type(port_ids) is int:
            port_ids = (port_ids,)
        prior = [self.write(p) for p in port_ids]
        tic = datetime.datetime.now()
        while (datetime.datetime.now()-tic) < datetime.timedelta(seconds=dur):
            for p in port_ids:
                self.toggle(p)
            wait(isi)
        for i, p in enumerate(port_ids):
            self.write(p,prior[i])
        toc = datetime.datetime.now()
        return (tic, toc)


class CuePanel(OperantPanel):
    def __init__(self,box_id):
        OperantPanel.__init__(self,box_id)
        self.dio['cue_green'] = 6
        self.dio['cue_blue'] = 7
        self.dio['cue_red'] = 8

class PerchChoicePanel(Panel):
    def __init__(self,box_id):
        Panel.__init__(self,box_id)
