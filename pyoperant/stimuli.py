import fnmatch
import os
import wave
import logging
import random
from contextlib import closing
from pyoperant.utils import Event, filter_files

logger = logging.getLogger(__name__)

# TODO: Integrate this concept of "event" with the one in events.py

class Stimulus(Event):
    """docstring for Stimulus"""
    def __init__(self, *args, **kwargs):
        super(Stimulus, self).__init__(*args, **kwargs)
        if self.label=='':
            self.label = 'stimulus'


class AuditoryStimulus(Stimulus):
    """docstring for AuditoryStimulus"""
    def __init__(self, *args, **kwargs):
        super(AuditoryStimulus, self).__init__(*args, **kwargs)
        if self.label=='':
            self.label = 'auditory_stimulus'

    @classmethod
    def from_wav(cls, wavfile):

        logger.debug("Attempting to create stimulus object from %s" % wavfile)
        with closing(wave.open(wavfile,'rb')) as wf:
            (nchannels, sampwidth, framerate, nframes, comptype, compname) = wf.getparams()

            duration = float(nframes)/sampwidth
            duration = duration * 2.0 / framerate
            stim = cls(time=0.0,
                       duration=duration,
                       name=wavfile,
                       label='wav',
                       description='',
                       file_origin=wavfile,
                       annotations={'nchannels': nchannels,
                                    'sampwidth': sampwidth,
                                    'framerate': framerate,
                                    'nframes': nframes,
                                    'comptype': comptype,
                                    'compname': compname,
                                    }
                       )
        return stim


class StimulusCondition(object):
    """ Class to represent a single stimulus condition for an operant
    conditioning experiment. The name parameter should be meaningful, as it will
    be stored with the trial data. The booleans "is_rewarded" and "is_punished"
    can be used to state if a stimulus should consequated according to the
    experiment's reinforcement schedule.

    Parameters
    ----------
    name: string
        Name of the stimulus condition used in data storage
    response: string, int, or bool
        The value of the desired response. Used to determine if the subject's
        response was correct. (e.g. "left", True)
    is_rewarded: bool
        Whether or not a correct response should be rewarded
    is_punished: bool
        Whether or not an incorrect response should be punished
    files: list
        A list of files to use for the condition. If files is omitted, the list
        will be discovered using the file_path, file_pattern, and recursive
        parameters.
    file_path: string
        Path to directory where stimuli are stored
    recursive: bool
        Whether or not to search file_path recursively
    file_pattern: string
        A glob pattern to filter files by
    replacement: bool
        Whether individual stimuli should be sampled with replacement
    shuffle: bool
        Whether the list of files should be shuffled before sampling.

    Attributes
    ----------
    name: string
        Name of the stimulus condition used in data storage
    response: string, int, or bool
        The value of the desired response. Used to determine if the subject's
        response was correct. (e.g. "left", True)
    is_rewarded: bool
        Whether or not a correct response should be rewarded
    is_punished: bool
        Whether or not an incorrect response should be punished
    files: list
        All of the matching files found
    replacement: bool
        Whether individual stimuli should be sampled with replacement
    shuffle: bool
        Whether the list of files should be shuffled before sampling.

    Methods
    -------
    get()

    Examples
    --------
    # Get ".wav" files for a "go" condition of a "Go-NoGo" experiment
    condition = StimulusCondition(name="Go",
                                  response=True,
                                  is_rewarded=True,
                                  is_punished=True,
                                  file_path="/path/to/stimulus_directory",
                                  recursive=True,
                                  file_pattern="*.wav",
                                  replacement=False)

    # Get a wavefile
    wavefile = condition.get()
    """

    def __init__(self, name="", response=None, is_rewarded=True,
                 is_punished=True, files=None, file_path="", recursive=False,
                 file_pattern="*", shuffle=True, replacement=False):

        # These should do something better than printing and returning
        if files is None:
            if len(file_path) == 0:
                raise IOError("No stimulus file_path provided!")
            if not os.path.exists(file_path):
                raise IOError("Stimulus file_path does not exist! %s" % file_path)

        self.name = name
        self.response = response
        self.is_rewarded = is_rewarded
        self.is_punished = is_punished
        self.shuffle = shuffle
        self.replacement = replacement

        if files is None:
            self.files = filter_files(file_path,
                                      file_pattern=file_pattern,
                                      recursive=recursive)
        else:
            self.files = files

        self._index_list = range(len(self.files))
        if self.shuffle:
            random.shuffle(self._index_list)

        logger.debug("Created new condition: %s" % self)

    def __str__(self):

        return "".join(["Condition %s: " % self.name,
                        "# files = %d" % len(self.files)])

    def get(self):
        """ Gets a single file from this condition's list of files. If
        replacement is True, choose a file randomly with replacement. If
        replacement is False, then return files in their (possibly shuffled)
        order.
        """

        if len(self._index_list) == 0:
            self._index_list = range(len(self.files))
            if self.shuffle:
                random.shuffle(self._index_list)

        if self.replacement is True:
            index = random.choice(self._index_list)
        else:
            index = self._index_list.pop(0)

        logger.debug("Selected file %d of %d" % (index + 1, len(self.files)))
        return self.files[index]


class StimulusConditionWav(StimulusCondition):
    """ Modifies StimulusCondition to only include .wav files. For usage
    information see StimulusCondition.
    """

    def __init__(self, *args, **kwargs):

        super(StimulusConditionWav, self).__init__(file_pattern="*.wav",
                                                   *args, **kwargs)

    def get(self):
        """ Gets an AuditoryStimulus instance from a chosen .wav file """
        wavfile = super(StimulusConditionWav, self).get()

        return AuditoryStimulus.from_wav(wavfile)
