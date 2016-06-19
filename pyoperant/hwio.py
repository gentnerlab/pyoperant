import logging
from pyoperant.errors import WriteCannotBeReadError

logger = logging.getLogger(__name__)


class BaseIO(object):
    """ Any type of IO device. Maintains info on the interface and configuration
    params for querying the IO device

    Parameters
    ----------
    name: string
        A name given to the IO. Useful when it is used in logging and error
        messages.
    interface: subclass of base_.BaseInterface
        An instance of an interface through which writes and reads are sent
    params: dictionary
        A dictionary of parameters for configuration and write/read calls.
        Common keys are: subdevice, channel, etc.

    Attributes
    ----------
    name: string
        A name given to the IO. Useful when it is used in logging and error
        messages.
    interface: subclass of base_.BaseInterface
        An instance of an interface through which writes and reads are sent
    params: dictionary
        A dictionary of parameters for configuration and write/read calls.
        Common keys are: subdevice, channel, etc.
    """

    def __init__(self, name=None, interface=None, params={},
                 *args, **kwargs):

        super(BaseIO, self).__init__(*args, **kwargs)
        self.name = name
        self.interface = interface
        self.params = params


class BooleanInput(BaseIO):
    """ Class which holds information about boolean inputs and abstracts the
    methods of querying their values

    Parameters
    ----------
    interface: a subclass of base_.BaseInterface
        Interface through which values are read. Must have '_read_bool' method.
    params: dictionary
        A dictionary of parameters for configuration and boolean read calls.
        Common keys are: subdevice, channel, invert, etc.

    Attributes
    ----------
    name: string

    interface: a subclass of base_.BaseInterface
        Interface through which values are read. Must have '_read_bool' method.
    params: dictionary
        A dictionary of parameters for configuration and boolean read calls.
        Common keys are: subdevice, channel, invert, etc.
    last_value: bool
        Most recently returned value

    Methods
    -------
    config()
        Configures the boolean input
    read()
        Reads value of the input. Returns a boolean
    poll()
        Polls the input until value is True. Returns the time of the change
    """

    def __init__(self, interface=None, params={},
                 *args, **kwargs):
        super(BooleanInput, self).__init__(interface=interface,
                                           params=params,
                                           *args,
                                           **kwargs)

        assert self.interface.can_read_bool
        self.last_value = False
        self.config()

    def config(self):
        """ Calls the interface's _config_read method with the keyword arguments
        in params

        Returns
        -------
        bool
            True if configuration succeeded
        """

        if not hasattr(self.interface, "_config_read"):
            return False

        return self.interface._config_read(**self.params)

    def read(self):
        """ Read the status of the boolean input

        Returns
        -------
        bool
            The current status reported by the interface
        """

        self.last_value = self.interface._read_bool(**self.params)
        return self.last_value

    def poll(self, timeout=None):
        """ Runs a loop, querying for the boolean input to return True.

        Parameters
        ----------
        timeout: float

        Returns
        -------
        datetime or None
            peck time or None if timeout
        """

        input_time = self.interface._poll(timeout=timeout,
                                          last_value=self.last_value,
                                          **self.params)
        if input_time is not None:
            self.last_value = True
        else:
            self.last_value = False

        return input_time

class BooleanOutput(BaseIO):
    """Class which holds information about boolean outputs and abstracts the
    methods of writing to them

    Parameters
    ----------
    interface: subclass of base_.BaseInterface
        Interface through which values are written. Must have '_write_bool'
        method.
    params: dictionary
        A dictionary of parameters for configuration and boolean write calls.
        Common keys are: subdevice, channel, invert, etc.

    Methods
    -------
    config()
        Configures the boolean output
    write(value)
        Writes a value to the output. Returns the value
    read()
        If the interface supports '_read_bool' for this output, returns
        the current value of the output from the interface. Otherwise this
        returns the last passed by write(value)
    toggle()
        Flips the value from the current value
    """
    def __init__(self, interface=None, params={}, *args, **kwargs):
        super(BooleanOutput, self).__init__(interface=interface,
                                            params=params,
                                            *args,
                                            **kwargs)

        assert self.interface.can_write_bool
        self.last_value = None
        self.config()

    def config(self):
        """ Calls the interface's _config_write method with the keyword
        arguments in params

        Returns
        -------
        bool
            True if configuration succeeded
        """
        if not hasattr(self.interface, "_config_write"):
            return False

        logger.debug("Configuring BooleanOutput to write on interface % s" % self.interface)
        return self.interface._config_write(**self.params)

    def read(self):
        """ Read the status of the boolean output, if supported

        Returns
        -------
        bool
            The current status reported by the interface or the last value
            written to the interface.
        """
        if self.interface.can_read_bool:
            try:
                value = self.interface._read_bool(**self.params)
            except WriteCannotBeReadError:
                value = self.last_value
        else:
            value = self.last_value

        return value

    def write(self, value=False, event=None):
        """ Writes to the boolean output

        Parameters
        ----------
        value: bool
            Value to be written to the output
        event: dictionary
            Dictionary containing event details that are passed along to the
            interface.

        Returns
        -------
        bool
            The value written to the interface
        """

        logger.debug("Setting value to %s" % value)
        self.last_value = self.interface._write_bool(value=value,
                                                     event=event,
                                                     **self.params)
        return self.last_value

    def toggle(self, event=None):
        """ Toggles the value of the boolean output

        Parameters
        ----------
        event: dictionary
            Dictionary containing event details that are passed along to the
            interface.

        Returns
        -------
        bool
            The value written to the interface
        """

        # TODO: what will event be here?
        value = not self.read()
        return self.write(value=value, event=event)


class AnalogInput(BaseIO):
    """ Class which holds information about analog inputs and abstracts the
    methods of reading from them

    Parameters
    ----------
    interface: subclass of base_.BaseInterface
        Interface through which values are written. Must have '_read_analog'
        method.
    params: dictionary
        A dictionary of parameters for configuration and analog read calls.
        Common keys are: subdevice, channel, etc.

    Methods
    -------
    config()
        Configures the analog input
    read(nsamples)
        Reads nsamples values from the input. Returns the values as an array
    """
    def __init__(self, interface=None, params={}, *args, **kwargs):
        super(AnalogInput, self).__init__(interface=interface,
                                          params=params,
                                          *args,
                                          **kwargs)
        assert self.interface.can_read_analog

        self.config()

    def config(self):
        """ Calls the interface's _config_read_analog method with the keyword
        arguments in params

        Returns
        -------
        bool
            True if configuration succeeded
        """
        if not hasattr(self.interface, "_config_read_analog"):
            return False

        logger.debug("Configuring AnalogInput to read on interface % s" % self.interface)
        return self.interface._config_read_analog(**self.params)

    def read(self, nsamples):
        """ Reads from the analog input

        Parameters
        ----------
        nsamples: int
            Number of samples to read from input

        Returns
        -------
        numpy array
            The analog signal recorded by the interface
        """
        return self.interface._read_analog(nsamples=nsamples, **self.params)


class AnalogOutput(BaseIO):
    """ Class which holds information about analog outputs and abstracts the
    methods of writing to them

    Parameters
    ----------
    interface: subclass of base_.BaseInterface
        Interface through which values are written. Must have '_write_analog'
        method.
    params: dictionary
        A dictionary of parameters for configuration and analog write calls.
        Common keys are: subdevice, channel, etc.

    Methods
    -------
    config()
        Configures the analog output
    write(values)
        Writes an array of values to the output. Returns True if successful.
    """
    def __init__(self, interface=None, params={}, *args, **kwargs):
        super(AnalogOutput, self).__init__(interface=interface,
                                           params=params,
                                           *args,
                                           **kwargs)
        assert self.interface.can_write_analog

        self.config()

    def config(self):
        """ Calls the interface's config_write_analog method with the keyword
        arguments in params

        Returns
        -------
        bool
            True if configuration succeeded
        """
        if not hasattr(self.interface, "_config_write_analog"):
            return False

        logger.debug("Configuring AnalogOutput to write on interface % s" % self.interface)
        return self.interface._config_write_analog(**self.params)

    def write(self, values, event=None):
        """ Writes to the analog output

        Parameters
        ----------
        values: numpy array
            Array of float values to be written to the output
        event: dictionary
            Dictionary containing event details that are passed along to the
            interface.

        Returns
        -------
        bool
            True if the write succeeded
        """

        return self.interface._write_analog(values=values, event=event)


class AudioOutput(BaseIO):
    """ Class which holds information about audio outputs and abstracts the
    methods of writing to them

    Parameters
    ----------
    interface: subclass of base_.BaseInterface()
        Must have the methods '_queue_wav', '_play_wav', '_stop_wav'
    params: dictionary
        A dictionary of parameters for configuration and audio playback calls.
        Common keys are: subdevice, channel, etc.

    Methods:
    config()
        Configures the audio interface
    queue(wav_filename)
        Queues a .wav file for playback
    play()
        Plays the queued audio file
    stop()
        Stops the playing audio file
    """

    def __init__(self, interface=None, params={}, *args, **kwargs):
        super(AudioOutput, self).__init__(interface=interface,
                                          params=params,
                                          *args,
                                          **kwargs)

        assert hasattr(self.interface, '_queue_wav')
        assert hasattr(self.interface, '_play_wav')
        assert hasattr(self.interface, '_stop_wav')
        self.config()

    def config(self):
        """ Calls the interface's config_write_analog method with the keyword
        arguments in params

        Returns
        -------
        bool
            True if configuration succeeded
        """
        if not hasattr(self.interface, "_config_write_analog"):
            return False

        logger.debug("Configuring AudioOutput to write on interface % s" % self.interface)
        return self.interface._config_write_analog(**self.params)

    def queue(self, wav_filename, event=None):
        return self.interface._queue_wav(wav_filename, event=event, **self.params)

    def play(self, event=None):
        return self.interface._play_wav(event=event, **self.params)

    def stop(self, event=None):
        return self.interface._stop_wav(event=event, **self.params)
