import datetime
import hwio, utils
from errors import ComponentError

class BaseComponent(object):
    """Base class for physcal component"""
    def __init__(self, name=None, *args, **kwargs):
        self.name = name
        pass


## Hopper ##

class HopperActiveError(ComponentError):
    """raised when the hopper is up when it shouldn't be"""
    pass

class HopperInactiveError(ComponentError):
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

    Parameters
    ----------
    solenoid : `hwio.BooleanOutput`
        output channel to activate the solenoid & raise the hopper
    IR : :class:`hwio.BooleanInput` 
       input channel for the IR beam to check if the hopper is up
    lag : float, optional 
        time in seconds to wait before checking to make sure the hopper is up (default=0.3)

    Attributes
    ----------
    solenoid : hwio.BooleanOutput 
        output channel to activate the solenoid & raise the hopper
    IR : hwio.BooleanInput 
       input channel for the IR beam to check if the hopper is up
    lag : float 
        time in seconds to wait before checking to make sure the hopper is up

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
        """reads the status of solenoid & IR beam, then throws an error if they don't match

        Returns
        -------
        bool
            True if the hopper is up.

        Raises
        ------
        HopperActiveError
            The Hopper is up and it shouldn't be. (The IR beam is tripped, but the solenoid is not active.)
        HopperInactiveError
            The Hopper is down and it shouldn't be. (The IR beam is not tripped, but the solenoid is active.)

        """
        IR_status = self.IR.read()
        solenoid_status = self.solenoid.read()
        if IR_status != solenoid_status:
            if IR_status:
                raise HopperActiveError
            elif solenoid_status:
                raise HopperInactiveError
            else:
                raise ComponentError("the IR & solenoid don't match: IR:%s,solenoid:%s" % (IR_status,solenoid_status))
        else:
            return IR_status

    def up(self):
        """Raises the hopper up.

        Returns
        -------
        bool
            True if the hopper comes up.

        Raises
        ------
        HopperWontComeUpError
            The Hopper did not raise.
        """
        self.solenoid.write(True)
        utils.wait(self.lag)
        try:
            self.check()
        except HopperInactiveError as e:
            raise HopperWontComeUpError(e)
        return True

    def down(self):
        """Lowers the hopper.

        Returns
        -------
        bool
            True if the hopper drops.

        Raises
        ------
        HopperWontDropError
            The Hopper did not drop.
        """
        self.solenoid.write(False)
        utils.wait(self.lag)
        try:
            self.check()
        except HopperActiveError as e:
            raise HopperWontDropError(e)
        return True

    def feed(self,dur=2.0):
        """Performs a feed

        Parameters
        ---------
        dur : float, optional 
            duration of feed in seconds

        Returns
        -------
        (datetime, float)
            Timestamp of the feed and the feed duration


        Raises
        ------
        HopperAlreadyUpError
            The Hopper was already up at the beginning of the feed.
        HopperWontComeUpError
            The Hopper did not raise for the feed.
        HopperWontDropError
            The Hopper did not drop fater the feed.

        """
        assert self.lag <= dur, "lag (%ss) must be shorter than duration (%ss)" % (self.lag,dur)
        try:
            self.check()
        except HopperInactiveError as e:
            raise HopperAlreadyUpError(e)
        feed_time = datetime.datetime.now()
        self.up() # includes a lag
        utils.wait(dur - self.lag)
        feed_duration = datetime.datetime.now() - feed_time
        self.down() # includes a lag
        return (feed_time,feed_duration)

    def reward(self,value=2.0):
        """wrapper for `feed`, passes *value* into *dur* """
        return self.feed(dur=value)

## Peck Port ##

class PeckPort(BaseComponent):
    """ Class which holds information about peck ports

    Parameters
    ----------
    LED : hwio.BooleanOutput
        output channel to activate the LED in the peck port
    IR : hwio.BooleanInput
        input channel for the IR beam to check for a peck

    Attributes
    ----------
    LED : hwio.BooleanOutput
        output channel to activate the LED in the peck port
    IR : hwio.BooleanInput
        input channel for the IR beam to check for a peck

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
        """reads the status of the IR beam

        Returns
        -------
        bool
            True if beam is broken
        """
        return self.IR.read()

    def off(self):
        """ Turns the LED off 

        Returns
        -------
        bool
            True if successful
        """
        self.LED.write(False)
        return True

    def on(self):
        """Turns the LED on 

        Returns
        -------
        bool
            True if successful
        """
        self.LED.write(True)
        return True

    def flash(self,dur=1.0,isi=0.1):
        """Flashes the LED on and off with *isi* seconds high and low for *dur* seconds, then revert LED to prior state.

        Parameters
        ----------
        dur : float, optional
            Duration of the light flash in seconds.
        isi : float,optional
            Time interval between toggles. (0.5 * period)

        Returns
        -------
        (datetime, float)
            Timestamp of the flash and the flash duration
        """
        LED_state = self.LED.read()
        flash_time = datetime.datetime.now()
        flash_duration = datetime.datetime.now() - flash_time
        while flash_duration < datetime.timedelta(seconds=dur):
            self.LED.toggle()
            utils.wait(isi)
            flash_duration = datetime.datetime.now() - flash_time
        self.LED.write(LED_state)
        return (flash_time,flash_duration)

    def poll(self):
        """ Polls the peck port until there is a peck

        Returns
        -------
        datetime
            Timestamp of the IR beam being broken.
        """
        return self.IR.poll()

## House Light ##
class HouseLight(BaseComponent):
    """ Class which holds information about the house light

    Keywords
    --------
    light : hwio.BooleanOutput
        output channel to turn the light on and off

    Methods:
    on() -- 
    off() -- 
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
        """Turns the house light off.

        Returns
        -------
        bool
            True if successful.

        """
        self.light.write(False)
        return True

    def on(self):
        """Turns the house light on.

        Returns
        -------
        bool
            True if successful.
        """
        self.light.write(True)
        return True

    def timeout(self,dur=10.0):
        """Turn off the light for *dur* seconds 

        Keywords
        -------
        dur : float, optional
            The amount of time (in seconds) to turn off the light.

        Returns
        -------
        (datetime, float)
            Timestamp of the timeout and the timeout duration

        """
        timeout_time = datetime.datetime.now()
        self.off()
        utils.wait(dur)
        timeout_duration = datetime.datetime.now() - timeout_time
        self.on()
        return (timeout_time,timeout_duration)

    def punish(self,value=10.0):
        """Calls `timeout(dur)` with *value* as *dur* """
        return self.timeout(dur=value)


## Cue Light ##

class RGBLight(BaseComponent):
    """ Class which holds information about an RGB cue light

    Keywords
    --------
    red : hwio.BooleanOutput
        output channel for the red LED
    green : hwio.BooleanOutput
        output channel for the green LED
    blue : hwio.BooleanOutput
        output channel for the blue LED

    """
    def __init__(self,red,green,blue,*args,**kwargs):
        super(RGBLight, self).__init__(*args,**kwargs)
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
        """Turns the cue light to red

        Returns
        -------
        bool
            `True` if successful.
        """
        self._green.write(False)
        self._blue.write(False)
        return self._red.write(True)
    def green(self):
        """Turns the cue light to green

        Returns
        -------
        bool
            `True` if successful.
        """
        self._red.write(False)
        self._blue.write(False)
        return self._green.write(True)
    def blue(self):
        """Turns the cue light to blue

        Returns
        -------
        bool
            `True` if successful.
        """
        self._red.write(False)
        self._green.write(False)
        return self._blue.write(True)
    def off(self):
        """Turns the cue light off

        Returns
        -------
        bool
            `True` if successful.
        """
        self._red.write(False)
        self._green.write(False)
        self._blue.write(False)
        return True


# ## Perch ##

# class Perch(BaseComponent):
#     """Class which holds information about a perch

#     Has parts:
#     - IR Beam (input)
#     - speaker
#     """
#     def __init__(self,*args,**kwargs):
#         super(Perch, self).__init__(*args,**kwargs)


# Classes and functions for testing purposes

class TestHopper(Hopper):
    def __init__(self,IR=None,solenoid=None,lag=0.0,*args,**kwargs):
        self.call_queue = []
        
        if IR is None:
            IR = hwio.TestBooleanInput()
        if solenoid is None:
            solenoid = hwio.TestBooleanOutput()
        
        super(TestHopper, self).__init__(IR, solenoid, lag=lag, *args, **kwargs)
        self.IR.test_set_state(False)
        self.solenoid.write(False)

    def check(self):
        self.call_queue.append('check')
        return super(TestHopper, self).check()

    def up(self):
        self.call_queue.append('up')
        self.IR.test_set_state(True)
        return super(TestHopper, self).up()

    def down(self):
        self.call_queue.append('down')
        self.IR.test_set_state(False)
        return super(TestHopper, self).down()

    def feed(self,dur=2.0):
        self.call_queue.append('feed:%d' % (dur))
        return super(TestHopper, self).feed(dur=0.0)

    def reward(self,value=2.0):
        """wrapper for `feed`, passes *value* into *dur* """
        return self.feed(dur=value)

class TestPeckPort(PeckPort):
    def __init__(self,IR=None,LED=None,*args,**kwargs):
        self.call_queue = []

        if IR is None:
            IR = hwio.TestBooleanInput()
        if LED is None:
            LED = hwio.TestBooleanOutput()

        super(TestPeckPort, self).__init__(IR, LED, *args,**kwargs)
        self.IR.test_set_state(False)
        self.LED.write(False)

    def status(self):
        self.call_queue.append('status')
        return super(TestPeckPort, self).status()

    def off(self):
        self.call_queue.append('off')
        return super(TestPeckPort, self).off()

    def on(self):
        self.call_queue.append('on')
        return super(TestPeckPort, self).on()

    def flash(self,dur=1.0,isi=0.1):
        self.call_queue.append('flash')
        # TODO: should be togglable to use real time
        return super(TestPeckPort, self).flash(dur=0.0, isi=0.0)

    def poll(self):
        self.call_queue.append('poll')
        return super(TestPeckPort, self).poll()

class TestHouseLight(HouseLight):
    def __init__(self,light=None,*args,**kwargs):
        self.call_queue = []

        if light is None:
            light = hwio.TestBooleanOutput()

        super(TestHouseLight, self).__init__(light=light, *args,**kwargs)
        super(TestHouseLight, self).off()

    def off(self):
        self.call_queue.append('off')
        return super(TestHouseLight, self).off()

    def on(self):
        self.call_queue.append('on')
        return super(TestHouseLight, self).on()

    def timeout(self,dur=0.0):
        self.call_queue.append('timeout')
        #TODO: should be togglable to use real time
        return super(TestHouseLight, self).timeout(dur=0.0)

    def punish(self,value=10.0):
        self.call_queue.append('punish')
        return super(TestHouseLight, self).punish(value=value)

class TestRGBLight(RGBLight):
    def __init__(self,red=None,green=None,blue=None,*args,**kwargs):
        self.call_queue = []

        if red is None:
            red = hwio.TestBooleanOutput()
        if green is None:
            green = hwio.TestBooleanOutput()
        if blue is None:
            blue = hwio.TestBooleanOutput()

        super(TestRGBLight, self).__init__(red, green, blue, *args,**kwargs)

    def red(self):
        self.call_queue.append('red')
        return super(TestRGBLight, self).red()
    def green(self):
        self.call_queue.append('green')
        return super(TestRGBLight, self).green()
    def blue(self):
        self.call_queue.append('blue')
        return super(TestRGBLight, self).blue()
    def off(self):
        self.call_queue.append('off')
        return super(TestRGBLight, self).off()

def test_Hopper():
    IR = hwio.TestBooleanInput()
    solenoid = hwio.TestBooleanOutput()
    hopper = TestHopper(IR=IR, solenoid=solenoid)

    assert not hopper.check()
    hopper.up()
    assert hopper.check()
    hopper.down()
    assert not hopper.check()
    hopper.reward()
    assert not hopper.check()

def test_PeckPort():
    IR = hwio.TestBooleanInput()
    LED = hwio.TestBooleanOutput()
    peck_port = TestPeckPort(IR=IR, LED=LED)

    assert not peck_port.status()
    IR.test_set_state(True)
    assert peck_port.status()
    assert not LED.read()
    peck_port.on()
    assert LED.read()
    peck_port.off()
    assert not LED.read()

def test_HouseLight():
    light = hwio.TestBooleanOutput()
    house_light = TestHouseLight(light=light)

    assert not light.read()
    house_light.on()
    assert light.read()
    house_light.off()
    assert not light.read()
    house_light.on()
    house_light.call_queue = []
    house_light.punish()
    assert 'timeout' in house_light.call_queue
    assert 'off' in house_light.call_queue
    assert 'on' in house_light.call_queue
    assert house_light.call_queue.index('off') < house_light.call_queue.index('on')

def test_RGBLight():
    red = hwio.TestBooleanOutput()
    green = hwio.TestBooleanOutput()
    blue = hwio.TestBooleanOutput()
    rgb_light = TestRGBLight(red=red, green=green, blue=blue)

    rgb_light.off()

    assert not red.read()
    assert not green.read()
    assert not blue.read()

    rgb_light.red()

    assert red.read()

    rgb_light.green()

    assert green.read()

    rgb_light.blue()

    assert blue.read()

def test_components():
    test_Hopper()
    test_PeckPort()
    test_HouseLight()
    test_RGBLight()