import pyaudio
import wave
from interfaces import base

class StreamContainer(object):
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

class Audio(base.BaseInterface):
    """Class which holds information about an audio device"""
    def __init__(self,name='',device_name='',*args,**kwargs):
        super(Audio, self).__init__(*args,**kwargs)
        self.pa = pyaudio.PyAudio()
        self.device_name = device_name
        for index in range(self.pa.get_device_count()):
            if self.device_name == self.pa.get_device_info_by_index(index)['name']:
                self.device_index = index
                break
            else:
                self.device_index = None
        self.device_info = self.pa.get_device_info_by_index(self.device_index)

    def __del__(self):
        self.pa.terminate()

    def get_stream(self,wf,start=False):
        """
        """
        def callback(in_data, frame_count, time_info, status):
            data = wf.readframes(frame_count)
            return (data, pyaudio.paContinue)

        stream = self.pa.open(format=self.pa.get_format_from_width(wf.getsampwidth()),
                              channels=wf.getnchannels(),
                              rate=wf.getframerate(),
                              output=True,
                              output_device_index=self.device_index,
                              start=start,
                              stream_callback=callback)

        return stream

    def queue_wav(self,wav_file):
        wf = wave.open(wav_file)
        stream = self.get_stream(wf)
        return StreamContainer(stream=stream,wf=wf)

    def play_wav(self,wav_file):
        wf = wave.open(wav_file)
        stream = self.get_stream(wf,start=True)
        return StreamContainer(stream=stream,wf=wf)
