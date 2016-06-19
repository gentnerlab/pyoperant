import time
import datetime
import logging
import wave
import numpy as np
from pyoperant import InterfaceError

logger = logging.getLogger(__name__)

class BaseInterface(object):
    """
    Implements generic interface methods.
    Implemented methods:
    - _poll
    """

    def __init__(self, *args, **kwargs):

        super(BaseInterface, self).__init__()
        self.device_name = None

    def open(self):
        pass

    def close(self):
        pass

    def _poll(self, channel=None, subdevices=None, invert=False,
              last_value=False, suppress_longpress=False,
              timeout=None, wait=None, event=None,
              *args, **kwargs):
        """ Runs a loop, querying for the boolean input to return True.

        Parameters
        ----------
        channel:
            default channel argument to pass to _read_bool()
        subdevices:
            default subdevices argument to pass to _read_bool()
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
        event: dict
            a dictionary of event information to emit just before writing

        Returns
        -------
        timestamp of True read or None if timed out
        """

        logger.debug("Begin polling from device %s" % self.device_name)
        if timeout is not None:
            start = time.time()
        while True:
            value = self._read_bool(channel=channel,
                                   subdevices=subdevices,
                                   invert=invert,
                                   event=event,
                                   *args, **kwargs)
            if not isinstance(value, bool):
                raise ValueError("Polling for bool returned something that was not a bool")
            if value is True:
                if (last_value is False) or (suppress_longpress is False):
                    logger.debug("Input detected. Returning")
                    return datetime.datetime.now()
            else:
                last_value = False

            if timeout is not None:
                if time.time() - start >= timeout:
                    logger.debug("Polling timed out. Returning")
                    return None

            if wait is not None:
                utils.wait(wait)


    def __del__(self):
        self.close()

    @property
    def can_read_bool(self):
        """
        If the interface is capable of reading boolean values from the device
        """

        return hasattr(self, "_read_bool")

    @property
    def can_write_bool(self):
        """
        If the interface is capable of writing boolean values to the device
        """

        return hasattr(self, "_write_bool")

    @property
    def can_read_analog(self):
        """
        If the interface is capable of reading analog values from the device
        """

        return hasattr(self, "_read_analog")

    @property
    def can_write_analog(self):
        """
        If the interface is capable of writing analog values from the device
        """

        return hasattr(self, "_write_analog")

class AudioInterface(BaseInterface):
    """
    Generic audio interface that implements wavefile handling
    Implemented methods:
    - validate
    -
    """

    def __init__(self, *args, **kwargs):

        super(AudioInterface, self).__init__()
        self.wf = None

    def _config_write_analog(self, *args, **kwargs):

        pass

    def validate(self):
        """
        Verifies simply that the wav file has been opened. Could do other
        checks in the future.
        """

        if self.wf is None:
            raise InterfaceError("wavefile is not open, but it should be")

    def _load_wav(self, filename):
        """ Loads the .wav file and normalizes it according to its bit depth
        """

        self.wf = wave.open(filename)
        self.validate()
        sampwidth = self.wf.getsampwidth()
        if sampwidth == 2:
            max_val = 32768.0
            dtype = np.int16
        elif sampwidth == 4:
            max_val = float(2 ** 32)
            dtype = np.int32

        data = np.fromstring(self.wf.readframes(-1), dtype=dtype)

        return (data / max_val).astype(np.float64)
