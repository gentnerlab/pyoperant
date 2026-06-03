# -*- coding: utf-8 -*-
import datetime
from pyoperant import hwio, utils, ComponentError
import logging

logger = logging.getLogger()

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
    """Controls a food hopper driven by either a solenoid or a servo motor.

    Exactly one of `solenoid` or `servo` must be provided. Use `solenoid` for
    older Magpi boards with a BooleanOutput-driven hopper. Use `servo` with
    `up_angle` and `down_angle` for Rev D boards with a PWMOutput-driven servo.

    Parameters
    ----------
    IR : hwio.BooleanInput
        Input channel for the IR beam that confirms hopper position.
    solenoid : hwio.BooleanOutput, optional
        Output channel for a solenoid-driven hopper. Mutually exclusive with
        `servo`.
    servo : hwio.PWMOutput, optional
        PWM output channel for a servo-driven hopper (pass servo=True in
        params). Mutually exclusive with `solenoid`.
    up_angle : float, optional
        Angle in degrees (0-300) to move the servo to the raised position.
        Required when using `servo`. Must be tuned per-panel in local_pi.py.
    down_angle : float, optional
        Angle in degrees (0-300) to move the servo to the lowered position.
        Required when using `servo`. Must be tuned per-panel in local_pi.py.
    max_lag : float, optional
        Seconds to wait for the IR beam to confirm position (default=0.3).
    inverted : bool, optional
        Set True if the IR beam logic is active-low (default=False).

    Examples
    --------
    Solenoid hopper (older Magpi boards)::

        hopper = Hopper(IR=ir_input, solenoid=bool_output, inverted=True)

    Servo hopper (Rev D Magpi boards)::

        hopper = Hopper(IR=ir_input, servo=pwm_output,
                        up_angle=45, down_angle=10, inverted=True)
    """
    def __init__(self, IR, solenoid=None, servo=None, up_angle=None,
                 down_angle=None, max_lag=None, inverted=False, *args, **kwargs):
        super(Hopper, self).__init__(*args, **kwargs)

        # validate: exactly one actuator must be supplied
        if solenoid is None and servo is None:
            raise ValueError('Hopper requires either a solenoid or a servo argument')
        if solenoid is not None and servo is not None:
            raise ValueError('Hopper takes either a solenoid or a servo, not both')

        if not isinstance(IR, hwio.BooleanInput):
            raise ValueError('%s is not an input channel' % IR)
        self.IR = IR
        self.inverted = bool(inverted)
        if max_lag is not None:
            self.max_lag = max_lag
        elif servo is not None:
            self.max_lag = 1.0  # servos are slower than solenoids
        else:
            self.max_lag = 0.3

        if solenoid is not None:
            if not isinstance(solenoid, hwio.BooleanOutput):
                raise ValueError('%s is not a BooleanOutput channel' % solenoid)
            self.solenoid = solenoid
            self._actuator = 'solenoid'

        else:
            if not isinstance(servo, hwio.PWMOutput):
                raise ValueError('%s is not a PWMOutput channel' % servo)
            if up_angle is None or down_angle is None:
                raise ValueError('up_angle and down_angle are required when using a servo')
            self.servo = servo
            self.up_angle = up_angle
            self.down_angle = down_angle
            self._actuator = 'servo'
            # move to down position on init so the hopper starts in a known state
            self.servo.write(self.down_angle)

    def _actuate_up(self):
        """Send the raise command to whichever actuator is fitted."""
        if self._actuator == 'servo':
            self.servo.write(self.up_angle)
        else:
            self.solenoid.write(True)

    def _actuate_down(self):
        """Send the lower command to whichever actuator is fitted."""
        if self._actuator == 'servo':
            self.servo.write(self.down_angle)
        else:
            self.solenoid.write(False)

    def check(self):
        """Read the IR beam and return whether the hopper is currently up.

        Returns
        -------
        bool
            True if the hopper is up (IR beam tripped).
        """
        IR_status = self.IR.read()
        if self.inverted:
            IR_status = not IR_status
        return IR_status

    def up(self):
        """Raise the hopper.

        Returns
        -------
        datetime
            Timestamp of when the IR beam was tripped (hopper confirmed up).

        Raises
        ------
        HopperWontComeUpError
            The hopper did not raise within max_lag seconds.
        """
        self._actuate_up()
        start = time.time()
        while time.time() - start < self.max_lag:
            if self.check():
                return datetime.datetime.now()
            time.sleep(0.05)
        self._actuate_down()  # safety: return to down position
        raise HopperWontComeUpError

    def down(self):
        """Lower the hopper.

        Returns
        -------
        datetime
            Timestamp of when the down command was confirmed.

        Raises
        ------
        HopperWontDropError
            The hopper did not lower within max_lag seconds.
        """
        self._actuate_down()
        utils.wait(self.max_lag)
        time_down = datetime.datetime.now()
        if self.check():  # IR beam still tripped after waiting
            raise HopperWontDropError
        return time_down

    def feed(self, dur=2.0, error_check=True):
        """Perform a feed cycle: raise the hopper, wait dur seconds, lower it.

        Parameters
        ----------
        dur : float, optional
            Duration of feed in seconds (default=2.0).

        Returns
        -------
        (datetime, datetime.timedelta)
            Timestamp of the feed and its duration.

        Raises
        ------
        HopperAlreadyUpError
            The hopper was already up at the start of the feed.
        HopperWontComeUpError
            The hopper did not raise for the feed.
        HopperWontDropError
            The hopper did not drop after the feed.
        """
        logger.debug("Feeding..")
        assert self.max_lag < dur, \
            "max_lag (%ss) must be shorter than duration (%ss)" % (self.max_lag, dur)
        if self.check():
            self._actuate_down()
            raise HopperAlreadyUpError
        feed_time = self.up()
        utils.wait(dur)
        feed_over = self.down()
        feed_duration = feed_over - feed_time
        return (feed_time, feed_duration)

    def reward(self, value=2.0):
        """Wrapper for `feed`, passes *value* as *dur*."""
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
    def __init__(self,IR,LED, inverted=False,*args,**kwargs):
        super(PeckPort, self).__init__(*args,**kwargs)
        if isinstance(IR,hwio.BooleanInput):
            self.IR = IR
        else:
            raise ValueError('%s is not an input channel' % IR)
        if isinstance(LED,hwio.BooleanOutput):
            self.LED = LED
            self.LEDtype = "boolean"
        elif isinstance(LED, hwio.PWMOutput):
            self.LED = LED
            self.LEDtype = "pwm"
        else:
            raise ValueError('%s is not an output channel' % LED)
        if inverted:
            self.inverted=True
        else:
            self.inverted=False

    def status(self):
        """reads the status of the IR beam

        Returns
        -------
        bool
            True if beam is broken
        """
        if self.inverted:
            return not self.IR.read()
        return self.IR.read()

    def off(self):
        """ Turns the LED off 

        Returns
        -------
        bool
            True if successful
        """
        if self.LEDtype == "boolean":
            self.LED.write(False)
        else:
            self.LED.write(0.0);
        return True

    def on(self, val=100.0):
        """Turns the LED on 

        Returns
        -------
        bool
            True if successful
        """
        if self.LEDtype == "boolean":
            self.LED.write(True)
        else:
            self.LED.write(val);
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
        if isinstance(red, (hwio.BooleanOutput, hwio.PWMOutput)):
            self._red = red
        else:
            raise ValueError('%s is not an output channel' % red)
        if isinstance(green, (hwio.BooleanOutput, hwio.PWMOutput)):
            self._green = green
        else:
            raise ValueError('%s is not an output channel' % green)
        if isinstance(blue, (hwio.BooleanOutput, hwio.PWMOutput)):
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
    def __init__(self,lights,color=[100.0,100.0,100.0,100.0],*args,**kwargs):
        super(LEDStripHouseLight, self).__init__(*args,**kwargs)
        self.lights = []
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
        self.off()
        utils.wait(dur)
        timeout_duration = datetime.datetime.now() - timeout_time
        self.on()
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

