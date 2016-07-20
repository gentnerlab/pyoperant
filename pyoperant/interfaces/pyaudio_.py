from ctypes import *
from contextlib import contextmanager
import pyaudio
import wave
import logging
from pyoperant.interfaces import base_
from pyoperant import InterfaceError
from pyoperant.events import events

logger = logging.getLogger(__name__)
# TODO: Clean up _stop_wav logging changes


# Modify the alsa error function to suppress needless warnings
# Code derived from answer by Nils Werner at:
# http://stackoverflow.com/questions/7088672/pyaudio-working-but-spits-out-error-messages-each-time
# TODO: Pass actual warnings to logger.debug when logging is fully integrated into master.
@contextmanager
def log_alsa_warnings():
    """ Suppresses ALSA warnings when initializing a PyAudio instance.

    with log_alsa_warnings():
        pa = pyaudio.PyAudio()
    """
    # Set up the C error handler for ALSA
    ERROR_HANDLER_FUNC = CFUNCTYPE(None,
                                   c_char_p,
                                   c_int,
                                   c_char_p,
                                   c_int,
                                   c_char_p,
                                   c_char_p)

    def py_error_handler(filename, line, function, err, fmt, args):

        # ALSA_STR = "ALSA lib %s:%i:(%s) %s"

        # Try to format fmt with args. As far as I can tell, CFUNCTYPE does not
        # support variable number of arguments, so formatting will fail with
        # TypeError if fmt has multiple %'s.
        # if args is not None:
        #     try:
        #         fmt %= args
        #     except TypeError:
        #         pass
        # logger.debug(ALSA_STR, filename, line, function, fmt)
        pass

    c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
    for asound_library in ["libasound.so", "libasound.so.2"]:
        try:
            asound = cdll.LoadLibrary(asound_library)
            break
        except OSError:
            continue
    asound.snd_lib_error_set_handler(c_error_handler)
    yield
    asound.snd_lib_error_set_handler(None)


class PyAudioInterface(base_.AudioInterface):
    """Class which holds information about an audio device

    assign a simple callback function that will execute on each frame
    presentation by writing interface.callback

    interface.callback() should return either True (to continue playback) or
    False (to terminate playback)

    Before assigning any callback function, please read the following:
    https://www.assembla.com/spaces/portaudio/wiki/Tips_Callbacks

    """
    def __init__(self,device_name='default',*args,**kwargs):
        super(PyAudioInterface, self).__init__(*args,**kwargs)
        self.device_name = device_name
        self.device_index = None
        self.stream = None
        self.wf = None
        self.open()

    def open(self):
        with log_alsa_warnings():
            self.pa = pyaudio.PyAudio()
        for index in range(self.pa.get_device_count()):
            if self.device_name == self.pa.get_device_info_by_index(index)['name']:
                logger.debug("Found device %s at index %d" % (self.device_name, index))
                self.device_index = index
                break
            else:
                self.device_index = None
        if self.device_index == None:
            raise InterfaceError('could not find pyaudio device %s' % (self.device_name))

        self.device_info = self.pa.get_device_info_by_index(self.device_index)

    def close(self):
        logger.debug("Closing device")
        try:
            self.stream.close()
        except AttributeError:
            self.stream = None
        try:
            self.wf.close()
        except AttributeError:
            self.wf = None
        self.pa.terminate()

    def validate(self):
        if self.wf is not None:
            return True
        else:
            raise InterfaceError('there is something wrong with this wav file')

    def _get_stream(self,start=False,callback=None):
        """
        """
        if callback is None:
            def callback(in_data, frame_count, time_info, status):
                data = self.wf.readframes(frame_count)
                return (data, pyaudio.paContinue)

        self.stream = self.pa.open(format=self.pa.get_format_from_width(self.wf.getsampwidth()),
                                   channels=self.wf.getnchannels(),
                                   rate=self.wf.getframerate(),
                                   output=True,
                                   output_device_index=self.device_index,
                                   start=start,
                                   stream_callback=callback)

    def _queue_wav(self,wav_file,start=False,callback=None):
        self.wf = wave.open(wav_file)
        self.validate()
        self._get_stream(start=start,callback=callback)

    def _play_wav(self, event=None, **kwargs):
        logger.debug("Playing wavfile")
        events.write(event)
        self.stream.start_stream()

    def _stop_wav(self, event=None, **kwargs):
        try:
            logger.debug("Attempting to close pyaudio stream")
            events.write(event)
            self.stream.close()
            logger.debug("Stream closed")
        except AttributeError:
            self.stream = None
        try:
            self.wf.close()
        except AttributeError:
            self.wf = None

if __name__ == "__main__":

    with log_alsa_warnings():
        pa = pyaudio.PyAudio()
    pa.terminate()
    print "-" * 40
    pa = pyaudio.PyAudio()
    pa.terminate()
