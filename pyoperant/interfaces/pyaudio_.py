import pyaudio
import wave
from pyoperant.interfaces import base_
from pyoperant import InterfaceError

class _StreamContainer(object):
    def __init__(self,wf,stream):
        self.wf = wf
        self.stream = stream

    def close(self):
        self.stream.close()
        self.wf.close()

    def play(self):
        self.stream.start_stream()

    def __del__(self):
        self.close()

class PyAudioInterface(base_.BaseInterface):
    """Class which holds information about an audio device"""
    def __init__(self,device_name,*args,**kwargs):
        super(PyAudioInterface, self).__init__(*args,**kwargs)
        self.device_name = device_name
        self.open()

    def open(self):
        self.pa = pyaudio.PyAudio()
        for index in range(self.pa.get_device_count()):
            if self.device_name == self.pa.get_device_info_by_index(index)['name']:
                self.device_index = index
                break
            else:
                self.device_index = None
        if self.device_index == None:
            raise InterfaceError('could not find pyaudio device %s' % (self.device_name))

        self.device_info = self.pa.get_device_info_by_index(self.device_index)

    def close(self):
        if hasattr(self,'stream'):
            self.stream.close()
        self.pa.terminate()

    def _get_stream(self,start=False):
        """
        """
        def _callback(in_data, frame_count, time_info, status):
            data = self.wf.readframes(frame_count)
            return (data, pyaudio.paContinue)

        self.stream = self.pa.open(format=self.pa.get_format_from_width(self.wf.getsampwidth()),
                                   channels=self.wf.getnchannels(),
                                   rate=self.wf.getframerate(),
                                   output=True,
                                   output_device_index=self.device_index,
                                   start=start,
                                   stream_callback=_callback)

    def _queue_wav(self,wav_file,start=False):
        self.wf = wave.open(wav_file)
        stream = self._get_stream(start=start)
        self.stream = _StreamContainer(stream=stream,wf=self.wf)

    def _play_wav(self):
        self.stream.play()

    def _stop_wav(self):
        self.stream.close()
