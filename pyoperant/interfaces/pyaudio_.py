import os
import pyaudio
import wave
import logging
from pyoperant.interfaces import base_
from pyoperant import InterfaceError

class PyAudioInterface(base_.BaseInterface):
    """Class which holds information about an audio device

    assign a simple callback function that will execute on each frame
    presentation by writing interface.callback

    interface.callback() should return either True (to continue playback) or
    False (to terminate playback)

    Before assigning any callback function, please read the following:
    https://www.assembla.com/spaces/portaudio/wiki/Tips_Callbacks

    """

    # Sample formats to try, most-preferred first, when opening an input
    # (recording) stream. 24-bit is native for many measurement mics (e.g.
    # a UMIK-1) but USB Audio Class devices don't expose 24-bit support
    # consistently across ALSA drivers (packed 3-byte vs. padded 4-byte) --
    # probe rather than assume, and fall back through 32-bit/16-bit.
    INPUT_FORMAT_PREFERENCE = ('paInt24', 'paInt32', 'paInt16')

    def __init__(self,device_name='default',*args,**kwargs):
        super(PyAudioInterface, self).__init__(*args,**kwargs)
        self.device_name = device_name
        self.device_index = None
        self.stream = None
        self.wf = None
        self.open()

    def open(self):
        # Suppress ALSA/JACK warnings from portaudio C library
        devnull = os.open(os.devnull, os.O_WRONLY)
        old_stderr = os.dup(2)
        os.dup2(devnull, 2)
        os.close(devnull)
        try:
            self.pa = pyaudio.PyAudio()
        finally:
            os.dup2(old_stderr, 2)
            os.close(old_stderr)

        self.device_index = self._find_device_index(self.device_name)
        self.device_info = (self.pa.get_device_info_by_index(self.device_index)
                             if self.device_index is not None else None)

    def _find_device_index(self, device_name, require_input=False):
        """Return the PortAudio device index whose name contains device_name
        as a case-insensitive substring (not an exact match -- USB device
        names can carry extra detail like a gain suffix), optionally
        requiring it be input-capable. Returns None -- meaning "let
        PortAudio use its own default device" -- when device_name is empty
        or the constructor's own sentinel default, 'default'.

        That sentinel matters: every panel deployed today constructs its
        speaker via PyAudioInterface() with no device_name, which defaults
        to 'default', not None. Resolving that against real device names
        would risk silently routing existing, working output to the wrong
        device; treating it as "no specific device requested" preserves
        today's default-device fallback exactly.
        """
        if not device_name or device_name.lower() == 'default':
            return None
        needle = device_name.lower()
        for index in range(self.pa.get_device_count()):
            info = self.pa.get_device_info_by_index(index)
            if require_input and info.get('maxInputChannels', 0) <= 0:
                continue
            if needle in info.get('name', '').lower():
                return index
        return None

    def _open_input_stream(self, sample_rate, channels=1, chunk_size=1024,
                            device_name=None, callback=None):
        """Open an input (recording) stream.

        Resolves device_name independently of self.device_index (the
        output device resolved in open()) -- a mic and a speaker on the
        same panel are typically different physical devices sharing one
        PyAudioInterface/PortAudio context.

        Tries INPUT_FORMAT_PREFERENCE in order, and falls back from the
        requested channel count to the device's own maxInputChannels, until
        PortAudio accepts a combination -- neither is guaranteed to match
        what a given USB Audio Class device/driver actually supports.

        With callback given: opens a non-blocking stream_callback-mode
        stream (caller receives raw bytes via pyaudio's own callback
        convention -- see SongMonitor's usage in
        pyoperant.song_recording.monitor). Without one: opens a
        blocking-mode stream, read via stream.read(n_frames).

        Returns (stream, sample_format, sample_width_bytes, channels_opened).
        Raises InterfaceError if no format/channel combination could be
        opened -- callers (song_recording's monitor thread) are expected to
        catch this and disable recording for the session rather than crash.
        """
        index = self._find_device_index(device_name, require_input=True)
        try:
            info = (self.pa.get_device_info_by_index(index) if index is not None
                    else self.pa.get_default_input_device_info())
            max_channels = int(info.get('maxInputChannels', channels)) or channels
        except Exception:
            max_channels = channels

        channel_candidates = [channels]
        if max_channels not in channel_candidates:
            channel_candidates.append(max_channels)

        last_error = None
        for fmt_name in self.INPUT_FORMAT_PREFERENCE:
            fmt = getattr(pyaudio, fmt_name)
            for ch in channel_candidates:
                kwargs = dict(format=fmt, channels=ch, rate=sample_rate,
                               input=True, input_device_index=index,
                               frames_per_buffer=chunk_size)
                if callback is not None:
                    kwargs['stream_callback'] = callback
                try:
                    stream = self.pa.open(**kwargs)
                    return stream, fmt, self.pa.get_sample_size(fmt), ch
                except Exception as exc:
                    last_error = exc

        raise InterfaceError(
            'could not open input stream %r: tried formats %s, channels %s '
            '-- last error: %s' % (device_name, self.INPUT_FORMAT_PREFERENCE,
                                    channel_candidates, last_error))

    def close(self):
        try:
            self.stream.close()
        except AttributeError:
            self.stream = None
        try:
            self.wf.close()
        except AttributeError:
            self.wf = None
        except IOError:
            logging.getLogger().error("IOError on _stop_wav")
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

    def _play_wav(self):
        self.stream.start_stream()

    def _stop_wav(self):
        try:
            self.stream.close()
        except AttributeError:
            self.stream = None
        try:
            self.wf.close()
        except AttributeError:
            self.wf = None
