import datetime
from pyoperant import hwio, utils, ComponentError

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
    max_lag : float, optional 
        time in seconds to wait before checking to make sure the hopper is up (default=0.3)

    Attributes
    ----------
    solenoid : hwio.BooleanOutput 
        output channel to activate the solenoid & raise the hopper
    IR : hwio.BooleanInput 
       input channel for the IR beam to check if the hopper is up
    max_lag : float 
        time in seconds to wait before checking to make sure the hopper is up

    """
    def __init__(self,IR,solenoid,max_lag=0.3,*args,**kwargs):
        super(Hopper, self).__init__(*args,**kwargs)
        self.max_lag = max_lag
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
        time_up = self.IR.poll(timeout=self.max_lag)

        if time_up is None: # poll timed out
            self.solenoid.write(False)
            raise HopperWontComeUpError
        else:
            return time_up

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
        time_down = datetime.datetime.now()
        utils.wait(self.max_lag)
        try:
            self.check()
        except HopperActiveError as e:
            raise HopperWontDropError(e)
        return time_down

    def feed(self,dur=2.0,error_check=True):
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
        assert self.max_lag < dur, "max_lag (%ss) must be shorter than duration (%ss)" % (self.max_lag,dur)
        try:
            self.check()
        except HopperActiveError as e:
            self.solenoid.write(False)
            raise HopperAlreadyUpError(e)
        feed_time = self.up()
        utils.wait(dur)
        feed_over = self.down()
        feed_duration = feed_over - feed_time
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

    def poll(self,timeout=None):
        """ Polls the peck port until there is a peck

        Returns
        -------
        datetime
            Timestamp of the IR beam being broken.
        """
        return self.IR.poll(timeout)

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
        self.light.write(False)
        utils.wait(dur)
        timeout_duration = datetime.datetime.now() - timeout_time
        self.light.write(True)
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

## House Light ##
class LEDStripHouseLight(BaseComponent):
    """ Class which holds information about the RGBW LED Strip PWM house light

    Keywords
    --------
    light : hwio.PWMOutputs
        [R, G, B, W]
        output channels to turn the light on and off

    Methods:
    on() -- 
    off() -- 
    set_color() -- set the color
    change_color -- sets color and turns on light
    timeout(dur) -- turns off the house light for 'dur' seconds (default=10.0)
    punish() -- calls timeout() for 'value' as 'dur'

    """
    def __init__(self,lights,color=[0,0,0,0.99],*args,**kwargs):
        super(HouseLight, self).__init__(*args,**kwargs)
        for light in lights:
            if isinstance(light,hwio.PWMOutput):
                self.lights.append(light)
        else:
            raise ValueError('%s is not an output channel' % light)
        self.color = color

    def off(self):
        """Turns the house light off.

        Returns
        -------
        bool
            True if successful.

        """
        for light in self.lights:
            light.write(0.0)
        return True

    def on(self):
        """Turns the house light on.

        Returns
        -------
        bool
            True if successful.
        """
        for ind in range(4):
            self.lights[ind].write(self.color[ind])
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
        self.light.write(False)
        utils.wait(dur)
        timeout_duration = datetime.datetime.now() - timeout_time
        self.light.write(True)
        return (timeout_time,timeout_duration)

    def punish(self,value=10.0):
        """Calls `timeout(dur)` with *value* as *dur* """
        return self.timeout(dur=value)

    def set_color(self, color):
        self.color = color

    def change_color(self, color):
        self.color = color
        self.on()
        
# ## Perch ##

# class Perch(BaseComponent):
#     """Class which holds information about a perch

#     Has parts:
#     - IR Beam (input)
#     - speaker
#     """
#     def __init__(self,*args,**kwargs):
#         super(Perch, self).__init__(*args,**kwargs)

