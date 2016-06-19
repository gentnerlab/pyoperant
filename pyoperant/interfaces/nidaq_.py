import time
import datetime
import logging
import numpy as np
import nidaqmx
import wave
from pyoperant.interfaces import base_
from pyoperant import utils, InterfaceError
from pyoperant.events import events, EventDToAHandler

logger = logging.getLogger(__name__)


def list_devices():
    """ List the devices currently connected to the system. """

    return nidaqmx.System().devices


def list_analog_inputs():
    """ List the analog inputs for each device """

    channels = dict()
    for dev in nidaqmx.System().devices:
        channels[str(dev)] = dev.get_analog_input_channels()

    return channels


def list_analog_outputs():
    """ List the analog outputs for each device """

    channels = dict()
    for dev in nidaqmx.System().devices:
        channels[str(dev)] = dev.get_analog_output_channels()

    return channels


def list_boolean_inputs():
    """ List the boolean inputs for each device """

    channels = dict()
    for dev in nidaqmx.System().devices:
        channels[str(dev)] = dev.get_digital_input_lines()

    return channels


def list_boolean_outputs():
    """ List the boolean outputs for each device """

    channels = dict()
    for dev in nidaqmx.System().devices:
        channels[str(dev)] = dev.get_digital_output_lines()

    return channels


# TODO: list clock channels?

class NIDAQmxError(InterfaceError):
    pass


class NIDAQmxInterface(base_.BaseInterface):
    """ Creates an interface for inputs and outputs to a NIDAQ card using
    the pylibnidaqmx library: https://github.com/imrehg/pylibnidaqmx

    Parameters
    ----------
    device_name: string
        the name of the device on your system (e.g. "Dev1")
    samplerate: float
        the samplerate for all inputs and outputs. If an external clock is
        specified, then this should be the maximum allowed samplerate.
    clock_channel: string
        the channel name for an external clock signal (e.g. "/Dev1/PFI0")
    analog_event_handler: instance of events.EventDToAHandler
        an event handler for sending event information down an analog channel.
        Should have a channel attribute. This can also be passed when you
        configure the analog output.

    Attributes
    ----------
    device_name: string
        the name of the device on your system (e.g. "Dev1")
    samplerate: float
        the samplerate for all inputs and outputs. If an external clock is
        specified, then this should be the maximum allowed samplerate.
    clock_channel: string
        the channel name for an external clock signal (e.g. "/Dev1/PFI0")
    tasks: dict
        a dictionary of all configured tasks. Each task corresponds to inputs or outputs of the same type that will be read or written to together.
    analog_event_handler: instance of events.EventDToAHandler
        an event handler for sending event information down an analog channel.

    Methods
    -------
    _config_write
    _config_read
    _write_bool
    _read_bool
    _config_write_analog
    _config_read_analog
    _write_analog
    _read_analog

    Examples
    --------
    dev = NIDAQmxInterface("Dev1") # open the device at "Dev1"
    # or with an external clock
    dev = NIDAQmxInterface("Dev1", clock_channel="/Dev1/PFI0")

    # Configure a boolean output on port 0, line 0
    dev._config_write("Dev1/port0/line0")
    # Set the output to True
    dev._write_bool("Dev1/port0/line0", True)

    # Configure a boolean input on port 0, line 1
    dev._config_read("Dev1/port0/line1")
    # Read from that input
    dev._read_bool("Dev1/port0/line1")

    # Configure an analog output on channel ao0
    dev._config_write("Dev1/ao0")
    # Set the output to True
    dev._write("Dev1/ao0", True)

    # Configure a analog input on channel ai0
    dev._config_read("Dev1/ai0")
    # Read from that input
    dev._read("Dev1/ai0")
    """

    def __init__(self, device_name, samplerate=30000,
                 analog_event_handler=None, clock_channel="OnboardClock",
                 *args, **kwargs):
        super(NIDAQmxInterface, self).__init__(*args, **kwargs)
        self.device_name = device_name
        self.samplerate = samplerate
        self.clock_channel = clock_channel
        self._analog_event_handler = analog_event_handler

        self.tasks = dict()
        self.open()

    def open(self):
        """ Opens the nidaqmx device """

        logger.debug("Opening nidaqmx device named %s" % self.device_name)
        self.device = nidaqmx.Device(self.device_name)

    def close(self):
        """ Closes the nidaqmx device and deletes all of the tasks """

        logger.debug("Closing nidaqmx device named %s" % self.device_name)
        for task in self.tasks.values():
            logger.debug("Deleting task named %s" % str(task.name))
            task.stop()
            task.clear()
            del task
        self.tasks = dict()

    def _config_read(self, channel, **kwargs):
        """Configure a channel or group of channels as a boolean input

        Parameters
        ----------
        channel: string
            a channel or group of channels that will all be read from at the same time (e.g. "Dev1/port0/line1" or "Dev1/port0/line1-7")

        Returns
        -------
        True on successful configuration
        """
        # TODO: test multiple channels. What format should channels be in?

        logger.debug("Configuring digital input on channel(s) %s" % str(channel))
        task = nidaqmx.DigitalInputTask()
        task.create_channel(channel)
        task.configure_timing_sample_clock(source=self.clock_channel,
                                           rate=self.samplerate,
                                           sample_mode="continuous")
        task.set_read_relative_to("most_recent")
        task.set_read_offset(-1)
        self.tasks[channel] = task

    def _config_write(self, channel, **kwargs):
        """ Configure a channel or group of channels as a boolean output

        Parameters
        ----------
        channel: string
            a channel or group of channels that will all be written to at the same time

        Returns
        -------
        True on successful configuration
        """

        # TODO: test multiple channels. What format should channels be in?
        logger.debug("Configuring digital output on channel(s) %s" % str(channel))
        task = nidaqmx.DigitalOutputTask()
        task.create_channel(channel)
        task.configure_timing_sample_clock(source=self.clock_channel,
                                           rate=self.samplerate)
        task.set_buffer_size(0)
        self.tasks[channel] = task

    def _read_bool(self, channel, invert=False, event=None, **kwargs):
        """ Read a boolean value from a channel or group of channels

        Parameters
        ----------
        channel: string
            a channel or group of channels that will all be read at the same time
        invert: bool
            whether or not to invert the read value
        event: dict
            a dictionary of event information to emit after a True reading

        Returns
        -------
        The value read from the hardware
        """
        if channel not in self.tasks:
            raise NIDAQmxError("Channel(s) %s not yet configured" % str(channel))

        task = self.tasks[channel]
        task.start()
        # while task.get_samples_per_channel_acquired() == 0:
        #     pass
        value, bits_per_sample = task.read(1)
        value = value[0, 0]
        task.stop()
        if invert:
            value = 1 - value
        value = bool(value == 1)
        if value:
            events.write(event)

        return value

    def _write_bool(self, channel, value, event=None, **kwargs):
        """ Write a boolean value to a channel or group of channels

        Parameters
        ----------
        channel: string
            a channel or group of channels that will all be written to at the same time
        value: bool or boolean array
            value to write to the hardware
        event: dict
            a dictionary of event information to emit just before writing

        Returns
        -------
        True
        """
        if channel not in self.tasks:
            raise NIDAQmxError("Channel(s) %s not yet configured" % str(channel))
        task = self.tasks[channel]
        events.write(event)
        task.write(value, auto_start=True)

        return True

    def _poll(self, channel=None, invert=False,
              last_value=False, suppress_longpress=False,
              timeout=None, wait=None, event=None, *args, **kwargs):
        """ Runs a loop, querying for the boolean input to return True.

        Parameters
        ----------
        channel:
            default channel argument to pass to _read_bool()
        invert: bool
            whether or not to invert the read value
        last_value: bool
            if the last read value was True. Necessary to suppress longpresses
        suppress_longpress: bool
            if True, attempts to suppress returning immediately if the button is still being pressed since the last call. If last_value is True, then it waits until the interface reads a single False value before allowing it to return.
        timeout: float
            the time, in seconds, until polling times out. Defaults to no timeout.
        wait: float
            the time, in seconds, to wait between subsequent reads (default no wait).

        Returns
        -------
        timestamp of True read or None if timed out
        """

        logger.debug("Begin polling from device %s" % self.device_name)
        if timeout is not None:
            start = time.time()

        if channel not in self.tasks:
            raise NIDAQmxError("Channel(s) %s not yet configured" % str(channel))

        task = self.tasks[channel]
        task.start()
        while True:
            # Read the value - cannot use _read_bool because it must start and stop the task each time.
            value, bits_per_sample = task.read(1)
            value = value[0, 0]
            if invert:
                value = 1 - value
            value = bool(value == 1)
            if value:
                events.write(event)

            if not isinstance(value, bool):
                task.stop()
                raise ValueError("Polling for bool returned something that was not a bool")
            if value is True:

                if (last_value is False) or (suppress_longpress is False):
                    logger.debug("Input detected. Returning")
                    task.stop()
                    return datetime.datetime.now()
            else:
                last_value = False

            if timeout is not None:
                if time.time() - start >= timeout:
                    logger.debug("Polling timed out. Returning")
                    task.stop()
                    return None

            if wait is not None:
                utils.wait(wait)


    def _config_read_analog(self, channel, min_val=-10.0, max_val=10.0,
                            **kwargs):
        """ Configure a channel or group of channels as an analog input

        Parameters
        ----------
        channel: string
            a channel or group of channels that will all be read at the same time
        min_val: float
            the minimum voltage that can be read
        max_val: float
            the maximum voltage that can be read

        Returns
        -------
        True if configuration succeeded
        """

        logger.debug("Configuring analog input on channel(s) %s" % str(channel))
        task = nidaqmx.AnalogInputTask()
        task.create_voltage_channel(channel, min_val=min_val, max_val=max_val)
        task.configure_timing_sample_clock(source=selsf.clock_channel,
                                           rate=self.samplerate,
                                           sample_mode="finite")
        self.tasks[channel] = task

        return True

    def _config_write_analog(self, channel, analog_event_handler=None,
                             min_val=-10.0, max_val=10.0, **kwargs):
        """ Configure a channel or group of channels as an analog output

        Parameters))
        ----------
        channel: string
            a channel or group of channels that will all be written to at the same
        analog_event_handler: instance of events.EventDToAHandler
            an event handler for sending event information down an analog channel. Should have a channel attribute.
        min_val: float
            the minimum voltage that can be read
        max_val: float
            the maximum voltage that can be read

        Returns
        -------
        True if configuration succeeded
        """

        logger.debug("Configuring analog output on channel(s) %s" % str(channel))
        task = nidaqmx.AnalogOutputTask()
        if self._analog_event_handler is None and \
            analog_event_handler is not None:
            if not hasattr(analog_event_handler, "channel"):
                raise AttributeError("analog_event_handler must have a channel attribute")
            channel = nidaqmx.libnidaqmx.make_pattern([channel,
                                                       analog_event_handler.channel])
            logger.debug("Configuring digital to analog output as well.")
            self._analog_event_handler = analog_event_handler

        task.create_voltage_channel(channel, min_val=min_val, max_val=max_val)
        task.configure_timing_sample_clock(source=self.clock_channel,
                                           rate=self.samplerate,
                                           sample_mode="finite")
        self.tasks[channel] = task

    def _read_analog(self, channel, nsamples, event=None, **kwargs):
        """ Read from a channel or group of channels for the specified number of
        samples.

        Parameters
        ----------
        channel: string
            a channel or group of channels that will be read at the same time
        nsamples: int
            the number of samples to read
        event: dict
            a dictionary of event information to emit after reading

        Returns
        -------
        a numpy array of the data that was read
        """

        if channel not in self.tasks:
            raise NIDAQmxError("Channel(s) %s not yet configured" % str(channel))

        task = self.tasks[channel]
        task.configure_timing_sample_clock(source=self.clock_channel,
                                           rate=self.samplerate,
                                           sample_mode="finite",
                                           samples_per_channel=nsamples)
        values = task.read(nsamples)
        events.write(event)
        return values

    def _write_analog(self, channel, values, is_blocking=False, event=None,
                      **kwargs):
        """ Write a numpy array of float64 values to the buffer on a channel or
        group of channels

        Parameters
        ----------
        channel: string
            a channel or group of channels that will all be written to at the same time
        values: numpy array of float64 values
            values to write to the hardware. Should be of dimension nchannels x nsamples.
        is_blocking: bool
            whether or not to block execution until all samples are written to the hardware
        event: dict
            a dictionary of event information to emit just before writing

        Returns
        -------
        True
        """

        if channel not in self.tasks:
            raise NIDAQmxError("Channel(s) %s not yet configured" % str(channel))

        task = self.tasks[channel]
        task.stop()
        task.configure_timing_sample_clock(source=self.clock_channel,
                                           rate=self.samplerate,
                                           sample_mode="finite",
                                           samples_per_channel=values.shape[0])

        if self._analog_event_handler is not None:
            # Get the string of (scaled) bits from the event handler
            bit_string = self._analog_event_handler.to_bit_sequence(event)

            # multi-channel outputs need to be of shape nsamples x nchannels
            if len(values.shape) == 1:
                values = values.reshape((-1, 1))

            # Add a channel of all zeros
            values = np.hstack([values, np.zeros((values.shape[0], 1))])
            # Place the bit string at the start
            values[:len(bit_string), -1] = bit_string

        # Write the values to the nidaq buffer
        # I think we might want to set layout='group_by_scan_number' in .write()
        task.write(values, auto_start=False)
        events.write(event)
        task.start()
        if is_blocking:
            task.wait_until_done()
            task.stop()

        return True


class NIDAQmxAudioInterface(NIDAQmxInterface, base_.AudioInterface):
    """ Creates an interface for writing audio data to a NIDAQ card using
    the pylibnidaqmx library: https://github.com/imrehg/pylibnidaqmx

    Parameters
    ----------
    device_name: string
        the name of the device on your system (e.g. "Dev1")
    samplerate: float
        the samplerate for the sound. If an external clock is
        specified, then this should be the maximum allowed samplerate.
    clock_channel: string
        the channel name for an external clock signal (e.g. "/Dev1/PFI0")

    Attributes
    ----------
    device_name: string
        the name of the device on your system (e.g. "Dev1")
    samplerate: float
        the samplerate for the sound. If an external clock is
        specified, then this should be the maximum allowed samplerate.
    clock_channel: string
        the channel name for an external clock signal (e.g. "/Dev1/PFI0")
    stream: nidaqmx.AnalogOutputTask
        the task used for writing out sound data
    wf: file handle
        the currently playing wavefile handle

    Methods
    -------
    _config_write_analog
    _get_stream
    _queue_wav
    _play_wav
    _stop_wav

    Examples
    --------

    """
    def __init__(self, device_name, samplerate=30000.0,
                 clock_channel=None, *args, **kwargs):

        super(NIDAQmxAudioInterface, self).__init__(device_name=device_name,
                                                    samplerate=samplerate,
                                                    clock_channel=clock_channel,
                                                    *args, **kwargs)
        self.stream = None
        self.wf = None
        self._wav_data = None

    def _config_write_analog(self, channel, analog_event_handler=None,
                             min_val=-10.0, max_val=10.0, **kwargs):
        """ Configure a channel or group of channels as an analog output

        Parameters
        ----------
        channel: string
            a channel or group of channels that will all be written to at the
            same time
        analog_event_handler: instance of events.EventDToAHandler
            an event handler for sending event information down an analog channel. Should have a channel attribute.
        min_val: float
            the minimum voltage that can be read
        max_val: float
            the maximum voltage that can be read

        Returns
        -------
        True if configuration succeeded
        """
        super(NIDAQmxAudioInterface, self)._config_write_analog(
                                                channel,
                                                analog_event_handler=analog_event_handler,
                                                min_val=min_val,
                                                max_val=max_val,
                                                **kwargs)
        self.stream = self.tasks.values()[0]

    def _queue_wav(self, wav_file, start=False, event=None, **kwargs):
        """ Queue the wav file for playback

        Parameters
        ----------
        wav_file: string
            Path to the wave file to load
        start: bool
            Whether or not to immediately start playback
        event: dict
            a dictionary of event information to emit just before playback
        """

        if self.wf is not None:
            self._stop_wav()

        events.write(event)
        logger.debug("Queueing wavfile %s" % wav_file)
        self._wav_data = self._load_wav(wav_file)

        if self._analog_event_handler is not None:
            # Get the string of (scaled) bits from the event handler
            bit_string = self._analog_event_handler.to_bit_sequence(event)

            # multi-channel outputs need to be of shape nsamples x nchannels
            if len(self._wav_data.shape) == 1:
                values = self._wav_data.reshape((-1, 1))
            else:
                values = self._wav_data

            # Add a channel of all zeros
            self._wav_data = np.hstack([values, np.zeros((values.shape[0], 1))])
            # Place the bit string at the start
            self._wav_data[:len(bit_string), -1] = bit_string
        self._get_stream(start=start, **kwargs)

    def _get_stream(self, start=False, **kwargs):
        """ Writes the stream to the nidaq buffer and optionally starts it.

        Parameters
        ----------
        start: bool
            Whether or not to immediately start playback
        """

        self.stream.configure_timing_sample_clock(source=self.clock_channel,
                                                  rate=self.samplerate,
                                                  sample_mode="finite",
                                                  samples_per_channel=self._wav_data.shape[0])
        # I think we might want to set layout='group_by_scan_number' in .write()
        self.stream.write(self._wav_data, auto_start=False)
        if start:
            self._play_wav(**kwargs)

    def _play_wav(self, is_blocking=False, event=None, **kwargs):
        """ Play the data that is currently in the buffer

        Parameters
        ----------
        is_blocking: bool
            Whether or not to play the sound in blocking mode
        event: dict
            a dictionary of event information to emit just before playback
        """

        logger.debug("Playing wavfile")
        events.write(event)
        self.stream.start()
        if is_blocking:
            self.wait_until_done()

    def _stop_wav(self, event=None, **kwargs):
        """ Stop the current playback and clear the buffer

        Parameters
        ----------
        event: dict
            a dictionary of event information to emit just before stopping
        """

        try:
            logger.debug("Attempting to close stream")
            events.write(event)
            self.stream.stop()
            logger.debug("Stream closed")
        except AttributeError:
            self.stream = None

        try:
            self.wf.close()
        except AttributeError:
             self.wf = None

        self._wav_data = None
