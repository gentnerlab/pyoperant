import datetime
from pyoperant import hwio, utils, ComponentError

class BaseComponent(object):
    """Base class for physcal component

    Parameters
    ----------
    name: string
        The name of the component to be stored in events (defaults to the
        class name)

    Attributes
    ----------
    name: string
        The name of the component to be stored in events (defaults to the
        class name)
    event:
        A dictionary that is sent along with changes to the state of inputs and
        outputs. It contains three main keys: name, action, and metadata. name
        is set here, action is set when a component method is called, and
        metadata is set as an optional argument to some methods.
    """
    def __init__(self, name=None, *args, **kwargs):
        if name is None:
            name = self.__class__.__name__
        self.name = name
        self.event = dict(name=self.name,
                          action="",
                          metadata=None)
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
       input channel for the IR beam to check if the hopper is up (optional)
    max_lag : float, optional
        time in seconds to wait before checking to make sure the hopper is up
        (default=0.3)

    Attributes
    ----------
    solenoid : hwio.BooleanOutput
        output channel to activate the solenoid & raise the hopper
    IR : hwio.BooleanInput
       input channel for the IR beam to check if the hopper is up (optional)
    max_lag : float
        time in seconds to wait before checking to make sure the hopper is up

    """
    def __init__(self, solenoid, IR=None, max_lag=0.3, *args, **kwargs):
        super(Hopper, self).__init__(*args, **kwargs)
        self.max_lag = max_lag

        if (IR is not None) and (not isinstance(IR, hwio.BooleanInput)):
            raise ValueError('%s is not an input channel' % IR)
        self.IR = IR

        if isinstance(solenoid, hwio.BooleanOutput):
            self.solenoid = solenoid
        else:
            raise ValueError('%s is not an output channel' % solenoid)

    def check(self):
        """ Reads the status of solenoid & IR beam, then throws an error if they
        don't match. If IR is None, then trust the solenoid's status.

        Returns
        -------
        bool
            True if the hopper is up.

        Raises
        ------
        HopperActiveError
            The Hopper is up and it shouldn't be. (The IR beam is tripped, but
            the solenoid is not active.)
        HopperInactiveError
            The Hopper is down and it shouldn't be. (The IR beam is not tripped,
            but the solenoid is active.)

        """
        if self.IR is None:
            return self.solenoid.read() is True

        IR_status = self.IR.read()
        solenoid_status = self.solenoid.read()
        if IR_status != solenoid_status:
            if IR_status:
                raise HopperActiveError
            elif solenoid_status:
                raise HopperInactiveError
            else:
                raise ComponentError("the IR & solenoid don't match: IR:%s,solenoid:%s" % (IR_status, solenoid_status))
        else:
            return IR_status

    def up(self):
        """ Raises the hopper up.

        Returns
        -------
        datetime
            Time at which the hopper came up

        Raises
        ------
        HopperWontComeUpError
            The Hopper did not raise.
        """

        self.event["action"] = "up"
        self.solenoid.write(True, event=self.event)
        if self.IR is None:
            return datetime.datetime.now()

        time_up = self.IR.poll(timeout=self.max_lag)

        if time_up is None:  # poll timed out
            self.solenoid.write(False)
            raise HopperWontComeUpError
        else:
            return time_up

    def down(self):
        """ Lowers the hopper.

        Returns
        -------
        datetime
            Time at which the hopper came down

        Raises
        ------
        HopperWontDropError
            The Hopper did not drop.
        """
        self.event["action"] = "down"
        self.solenoid.write(False, event=self.event)
        time_down = datetime.datetime.now()
        utils.wait(self.max_lag)
        try:
            self.check()
        except HopperActiveError as e:
            raise HopperWontDropError(e)
        return time_down

    def feed(self, dur=2.0, error_check=True):
        """ Performs a feed

        Parameters
        ----------
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
        assert self.max_lag < dur, "max_lag (%ss) must be shorter than duration (%ss)" % (self.max_lag, dur)
        try:
            self.check()
        except HopperActiveError as e:
            self.solenoid.write(False)
            raise HopperAlreadyUpError(e)
        feed_time = self.up()
        utils.wait(dur)
        feed_over = self.down()
        feed_duration = feed_over - feed_time
        return (feed_time, feed_duration)

    def reward(self, value=2.0):
        """ Performs a feed as a reward

        Parameters
        ----------
        value : float, optional
            duration of feed in seconds

        Returns
        -------
        (datetime, float)
            Timestamp of the feed and the feed duration
        """
        return self.feed(dur=value)


class Button(BaseComponent):
    """ Class which holds information about buttons with an input but no output.
    Could also describe a perch.

    Parameters
    ----------
    IR : hwio.BooleanInput
        input channel for the IR beam to check for a peck

    Attributes
    ----------
    IR : hwio.BooleanInput
        input channel for the IR beam to check for a peck
    """
    def __init__(self, IR, *args, **kwargs):
        super(Button, self).__init__(*args, **kwargs)
        if isinstance(IR, hwio.BooleanInput):
            self.IR = IR
        else:
            raise ValueError('%s is not an input channel' % IR)

    def status(self):
        """ Reads the status of the IR beam

        Returns
        -------
        bool
            True if beam is broken
        """
        return self.IR.read()

    def poll(self, timeout=None):
        """ Polls the peck port until there is a peck

        Returns
        -------
        datetime
            Timestamp of the IR beam being broken.
        """
        return self.IR.poll(timeout=timeout)


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
    def __init__(self, IR, LED, *args, **kwargs):
        super(PeckPort, self).__init__(*args, **kwargs)
        if isinstance(IR, hwio.BooleanInput):
            self.IR = IR
        else:
            raise ValueError('%s is not an input channel' % IR)

        if isinstance(LED, hwio.BooleanOutput):
            self.LED = LED
        else:
            raise ValueError('%s is not an output channel' % LED)

    def status(self):
        """ Reads the status of the IR beam

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
        self.event["action"] = "off"
        self.LED.write(False, event=self.event)
        return True

    def on(self):
        """ Turns the LED on

        Returns
        -------
        bool
            True if successful
        """
        self.event["action"] = "on"
        self.LED.write(True, event=self.event)
        return True

    def flash(self, dur=1.0, isi=0.1):
        """ Flashes the LED on and off with *isi* seconds high and low for *dur*
        seconds, then revert LED to prior state.

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
        return (flash_time, flash_duration)

    def poll(self, timeout=None):
        """ Polls the peck port until there is a peck

        Returns
        -------
        datetime
            Timestamp of the IR beam being broken.
        """
        return self.IR.poll(timeout=timeout)


## House Light ##
class HouseLight(BaseComponent):
    """ Class which holds information about the house light

    Parameters
    ----------
    light : hwio.BooleanOutput
        output channel to turn the light on and off

    Attributes
    ----------
    light : hwio.BooleanOutput
        output channel to turn the light on and off

    """
    def __init__(self, light, *args, **kwargs):
        super(HouseLight, self).__init__(*args, **kwargs)
        if isinstance(light, hwio.BooleanOutput):
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
        self.event["action"] = "off"
        self.light.write(False, event=self.event)
        return True

    def on(self):
        """Turns the house light on.

        Returns
        -------
        bool
            True if successful.
        """
        self.event["action"] = "on"
        self.light.write(True, event=self.event)
        return True

    def timeout(self, dur=10.0):
        """Turn off the light for *dur* seconds

        Parameters
        ----------
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
        return (timeout_time, timeout_duration)

    def punish(self, value=10.0):
        """ Turns light off as a punishment

        Parameters
        ---------
        value : float, optional
            duration of timeout in seconds

        Returns
        -------
        (datetime, float)
            Timestamp of the timeout and the timeout duration
        """
        return self.timeout(dur=value)


## Cue Light ##
class RGBLight(BaseComponent):
    """ Class which holds information about an RGB cue light

    Parameters
    ----------
    red : hwio.BooleanOutput
        output channel for the red LED
    green : hwio.BooleanOutput
        output channel for the green LED
    blue : hwio.BooleanOutput
        output channel for the blue LED

    Attributes
    ----------
    _red : hwio.BooleanOutput
        output channel for the red LED
    _green : hwio.BooleanOutput
        output channel for the green LED
    _blue : hwio.BooleanOutput
        output channel for the blue LED

    """
    def __init__(self, red, green, blue, *args, **kwargs):
        super(RGBLight, self).__init__(*args,**kwargs)
        if isinstance(red, hwio.BooleanOutput):
            self._red = red
        else:
            raise ValueError('%s is not an output channel' % red)

        if isinstance(green, hwio.BooleanOutput):
            self._green = green
        else:
            raise ValueError('%s is not an output channel' % green)

        if isinstance(blue, hwio.BooleanOutput):
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
        self.event["action"] = "red"
        self._green.write(False)
        self._blue.write(False)
        return self._red.write(True, event=self.event)

    def green(self):
        """Turns the cue light to green

        Returns
        -------
        bool
            `True` if successful.
        """
        self.event["action"] = "green"
        self._red.write(False)
        self._blue.write(False)
        return self._green.write(True, event=self.event)

    def blue(self):
        """Turns the cue light to blue

        Returns
        -------
        bool
            `True` if successful.
        """
        self.event["action"] = "blue"
        self._red.write(False)
        self._green.write(False)
        return self._blue.write(True, event=self.event)

    def off(self):
        """Turns the cue light off

        Returns
        -------
        bool
            `True` if successful.
        """
        self.event["action"] = "off"
        self._red.write(False, event=self.event)
        self._green.write(False)
        self._blue.write(False)
        return True


class Speaker(BaseComponent):
    """ Class which holds information about a speaker

    Parameters
    ----------
    output: hwio.AudioOutput
        Output of the speaker

    Attributes
    ----------
    output: hwio.AudioOutput
        Output of the speaker
    """

    def __init__(self, output, *args, **kwargs):

        super(Speaker, self).__init__(*args, **kwargs)
        self.output = output

    def queue(self, wav_filename, metadata=None):

        self.event["action"] = "queue"
        self.event["metadata"] = metadata
        return self.output.queue(wav_filename, event=self.event)

    def play(self):

        self.event["action"] = "play"
        return self.output.play(event=self.event)

    def stop(self):

        self.event["action"] = "stop"
        return self.output.stop(event=self.event)


class Microphone(BaseComponent):
    """ Class which holds information about a microphone

    Parameters
    ----------
    input_: hwio.AnalogInput
        Input to the microphone

    Attributes
    ----------
    input: hwio.AnalogInput
        Input to the microphone
    """

    def __init__(self, input_, *args, **kwargs):

        super(Speaker, self).__init__(*args, **kwargs)
        self.input = input_

    def record(self, nsamples):
        """ Reads from input for a set number of samples

        Parameters
        ----------
        nsamples: int
            Number of samples to read from input

        Returns
        -------
        numpy array
            The analog signal recorded by input
        """
        # TODO: This should use a stop signal too, I think
        self.event["action"] = "rec"
        return self.input.read(nsamples, event=self.event)

# ## Perch ##

# class Perch(BaseComponent):
#     """Class which holds information about a perch

#     Has parts:
#     - IR Beam (input)
#     - speaker
#     """
#     def __init__(self,*args,**kwargs):
#         super(Perch, self).__init__(*args,**kwargs)
