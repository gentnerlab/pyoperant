import datetime
from pyoperant import hwio
from pyoperant.utils import Error, wait, check_time


class BaseComponent(object):
    """Base class for physcal component"""
    def __init__(self, *args, **kwargs):
        pass


## Hopper ##

class HopperActiveError(HardwareError):
    """raised when the hopper is up when it shouldn't be"""
    pass

class HopperInactiveError(HardwareError):
    """raised when the hopper is down when it shouldn't be"""
    pass

class HopperAlreadyUpError(HopperActiveError):
    """raised when the hopper is already up before it goes up"""
    pass

class HopperWontComeUpError(HopperInactiveError):
    """raised when the hopper won't come up"""
    pass

class HopperWontDropError(HopperActiveError):
    """raised when the hopper won't drop"""
    pass

class Hopper(BaseComponent):
    """ Class which holds information about a hopper

    Keyword arguments:
    solenoid(hwio.BooleanOutput) -- output channel to activate the solenoid &
        raise the hopper
    IR(hwio.BooleanInput) -- input channel for the IR beam to check if the
        hopper is up
    lag(float) -- time in seconds to wait before checking to make sure the
        hopper is up (default=0.3)

    Methods:
    check() -- reads the status of solenoid & IR beam, then throws an error
        if the don't match
    up() -- raises the hopper up
    down() -- drops the hopper down
    feed(dur) -- delivers a feed for 'dur' seconds
    reward(value) -- calls 'feed' for 'value' as 'dur'

    """
    def __init__(self,IR,solenoid,lag=0.3,*args,**kwargs):
        super(Hopper, self).__init__(*args,**kwargs)
        self.lag = lag
        if isinstance(IR,hwio.BooleanInput):
            self.IR = IR
        else:
            raise ValueError('%s is not an input channel' % IR)
        if isinstance(solenoid,hwio.BooleanOutput):
            self.solenoid = solenoid
        else:
            raise ValueError('%s is not an output channel' % solenoid)

    def check(self):
        """get status of solenoid & IR beam, throw hopper error if mismatch"""
        IR_status = self.IR.read()
        solenoid_status = self.solenoid.read()
        if IR_status is not solenoid_status:
            if IR_status:
                raise HopperActiveError
            elif solenoid_status:
                raise HopperInactiveError
            else:
                raise HardwareError('IR:%s,solenoid:%s' % (IR_status,solenoid_status))
        else:
            return IR_status

    def up(self):
        self.solenoid.write(True)
        wait(self.lag)
        try:
            self.check()
        except HopperInactiveError as e:
            raise HopperWontComeUpError(e)
        return True

    def down(self):
        """ drop hopper """
        self.solenoid.write(False)
        wait(self.lag)
        try:
            self.check()
        except HopperActiveError as e:
            raise HopperWontDropError(e)
        return True

    def feed(self,dur=2.0):
        """Performs a feed

        arguments:
        feedsecs -- duration of feed in seconds (default: %default)
        """
        assert self.lag < dur, "lag (%ss) must be shorter than duration (%ss)" % (self.lag,dur)
        try:
            self.check()
        except HopperInactiveError as e:
            raise HopperAlreadyUpError(e)
        feed_time = datetime.datetime.now()
        self.up()
        feed_duration = datetime.datetime.now() - feed_time
        while feed_duration < datetime.timedelta(seconds=dur):
            wait(self.lag)
            self.check()
            feed_duration = datetime.datetime.now() - feed_time
        self.down()
        return (feed_time,feed_duration)

    def reward(self,value=2.0):
        return self.feed(dur=value)

## Peck Port ##

class PeckPort(BaseComponent):
    """ Class which holds information about peck ports

    Keyword arguments:
    LED(hwio.BooleanOutput) -- output channel to activate the LED in the peck
        port
    IR(hwio.BooleanInput) -- input channel for the IR beam to check for a peck

    Methods:
    status() -- reads the status of the IR beam
    on() -- turns the LED on
    off() -- turns the LED off
    flash(dur,isi) -- flashes the LED for 'dur' seconds (default=1.0) with an
        'isi' (default=0.1)
    wait_for_peck() -- waits for a peck. returns the peck time.

    """
    def __init__(self,IR,LED,*args,**kwargs):
        super(PeckPort, self).__init__(*args,**kwargs)
        if isinstance(IR,hwio.BooleanInput):
            self.IR = IR
        else:
            raise ValueError('%s is not an input channel' % IR)
        if isinstance(LED,hwio.BooleanOutput):
            self.LED = LED
        else:
            raise ValueError('%s is not an output channel' % LED)

    def status(self):
        """get the status of the IR beam """
        return self.IR.read()

    def off(self):
        """ turn off the LED  """
        self.LED.write(False)
        return True

    def on(self):
        """ turn on the LED  """
        self.LED.write(True)
        return True

    def flash(self,dur=1.0,isi=0.1):
        """ flash the LED """
        LED_state = self.LED.read()
        flash_time = datetime.datetime.now()
        flash_duration = datetime.datetime.now() - flash_time
        while flash_duration < datetime.timedelta(seconds=dur):
            self.LED.toggle()
            wait(isi)
            flash_duration = datetime.datetime.now() - flash_time
        self.LED.write(LED_state)
        return (flash_time,flash_duration)

    def wait_for_peck(self):
        """ poll peck port until there is a peck"""
        return self.IR.poll()

## House Light ##
class HouseLight(BaseComponent):
    """ Class which holds information about the house light

    Keyword arguments:
    light(hwio.BooleanOutput) -- output channel to turn the light on and off

    Methods:
    on() -- turns the house light on
    off() -- turns the house light off
    timeout(dur) -- turns off the house light for 'dur' seconds (default=10.0)
    punish() -- calls timeout() for 'value' as 'dur'

    """
    def __init__(self,light,*args,**kwargs):
        super(HouseLight, self).__init__(*args,**kwargs)
        if isinstance(light,hwio.BooleanOutput):
            self.light = light
        else:
            raise ValueError('%s is not an output channel' % light)

    def off(self):
        """ drop  """
        self.light.write(False)
        return True

    def on(self):
        """ drop  """
        self.light.write(True)
        return True

    def timeout(self,dur=10.0):
        """ turn off light for a few seconds """
        timeout_time = datetime.datetime.now()
        self.light.write(False)
        timeout_duration = datetime.datetime.now() - timeout_time
        while timeout_duration < datetime.timedelta(seconds=dur):
            timeout_duration = datetime.datetime.now() - timeout_time
        self.light.write(True)
        return (timeout_time,timeout_duration)

    def punish(self,value=10.0):
        return self.timeout(dur=value)


## Cue Light ##

class RGBLight(BaseComponent):
    """ Class which holds information about an RGB cue light

    Keyword arguments:
    red(hwio.BooleanOutput) -- output channel for the red LED
    green(hwio.BooleanOutput) -- output channel for the green LED
    blue(hwio.BooleanOutput) -- output channel for the blue LED

    Methods:
    red() -- turns the light red
    green() -- turns the light green
    blue() -- turns the light blue
    off() -- turns the light off

    """
    def __init__(self,red,green,blue,*args,**kwargs):
        super(CueLight, self).__init__(*args,**kwargs)
        if isinstance(red,hwio.BooleanOutput):
            self._red = red
        else:
            raise ValueError('%s is not an output channel' % red)
        if isinstance(green,hwio.BooleanOutput):
            self._green = green
        else:
            raise ValueError('%s is not an output channel' % green)
        if isinstance(blue,hwio.BooleanOutput):
            self._blue = blue
        else:
            raise ValueError('%s is not an output channel' % blue)

    def red(self):
        self._green.write(False)
        self._blue.write(False)
        return self._red.write(True)
    def green(self):
        self._red.write(False)
        self._blue.write(False)
        return self._green.write(True)
    def blue(self):
        self._red.write(False)
        self._green.write(False)
        return self._blue.write(True)
    def off(self):
        self._red.write(False)
        self._green.write(False)
        self._blue.write(False)


# ## Perch ##

# class Perch(BaseComponent):
#     """Class which holds information about a perch

#     Has parts:
#     - IR Beam (input)
#     - speaker
#     """
#     def __init__(self,*args,**kwargs):
#         super(Perch, self).__init__(*args,**kwargs)

