import wave
import sys
import struct
import time
import subprocess
import threading
import traceback
import shlex
import os
import string
import random
import datetime as dt
import numpy as np
import scipy as sp
import scipy.special
from contextlib import closing
from argparse import ArgumentParser
from pyoperant import Error


try:
    import simplejson as json
except ImportError:
    import json

class NumpyAwareJSONEncoder(json.JSONEncoder):
    """ this json encoder converts numpy arrays to lists so that json can write them.

    example usage:

    >>> import numpy as np
    >>> dict_to_save = {'array': np.zeros((5,))}
    >>> json.dumps(dict_to_save,
                   cls=NumpyAwareJSONEncoder
                   )
    '{"array": [0.0, 0.0, 0.0, 0.0, 0.0]}'

    """

    def default(self, obj):
        if isinstance(obj, np.ndarray):
                return obj.tolist()
        return json.JSONEncoder.default(self, obj)

# consider importing this from python-neo
class Event(object):
    """docstring for Event"""
    def __init__(self, time=None, duration=None, label='', name=None, description=None, file_origin=None, *args, **kwargs):
        super(Event, self).__init__()
        self.time = time
        self.duration = duration
        self.label = label
        self.name = name
        self.description = description
        self.file_origin = file_origin
        self.annotations = {}
        self.annotate(**kwargs)

    def annotate(self,**kwargs):
        self.annotations.update(kwargs)


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


def run_state_machine(start_in='pre', error_state=None, error_callback=None, **state_functions):
    """runs a state machine defined by the keyword arguments

    >>> def run_start():
    >>>    print "in 'run_start'"
    >>>    return 'next'
    >>> def run_next():
    >>>    print "in 'run_next'"
    >>>    return None
    >>> run_state_machine(start_in='start',
    >>>                   start=run_start,
    >>>                   next=run_next)
    in 'run_start'
    in 'run_next'
    None
    """
    # make sure the start state has a function to run
    assert (start_in in state_functions.keys())
    # make sure all of the arguments passed in are callable
    for func in state_functions.values():
        assert hasattr(func, '__call__')

    state = start_in
    while state is not None:
        try:
            state = state_functions[state]()
        except Exception, e:
            if error_callback:
                error_callback(e)
                raise
            else:
                raise
            state = error_state


class Trial(Event):
    """docstring for Trial"""
    def __init__(self,
                 index=None,
                 type_='normal',
                 class_=None,
                 *args, **kwargs):
        super(Trial, self).__init__(*args, **kwargs)
        self.label = 'trial'
        self.session = None
        self.index = index
        self.type_ = type_
        self.stimulus = None
        self.class_ = class_
        self.response = None
        self.correct = None
        self.rt = None
        self.reward = False
        self.punish = False
        self.events = []
        self.stim_event = None

 
class Command(object):
    """
    Enables to run subprocess commands in a different thread with TIMEOUT option.
 
    via https://gist.github.com/kirpit/1306188
    
    Based on jcollado's solution:
    http://stackoverflow.com/questions/1191374/subprocess-with-timeout/4825933#4825933
    
    """
    command = None
    process = None
    status = None
    output, error = '', ''
 
    def __init__(self, command):
        if isinstance(command, basestring):
            command = shlex.split(command)
        self.command = command
 
    def run(self, timeout=None, **kwargs):
        """ Run a command then return: (status, output, error). """
        def target(**kwargs):
            try:
                self.process = subprocess.Popen(self.command, **kwargs)
                self.output, self.error = self.process.communicate()
                self.status = self.process.returncode
            except:
                self.error = traceback.format_exc()
                self.status = -1
        # default stdout and stderr
        if 'stdout' not in kwargs:
            kwargs['stdout'] = subprocess.PIPE
        if 'stderr' not in kwargs:
            kwargs['stderr'] = subprocess.PIPE
        # thread
        thread = threading.Thread(target=target, kwargs=kwargs)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            self.process.terminate()
            thread.join()
        return self.status, self.output, self.error

def parse_commandline(arg_str=sys.argv[1:]):
    """ parse command line arguments
    note: optparse is depreciated w/ v2.7 in favor of argparse

    """
    parser=ArgumentParser()
    parser.add_argument('-B', '--box',
                      action='store', type=int, dest='box', required=False,
                      help='(int) box identifier')
    parser.add_argument('-S', '--subject',
                      action='store', type=str, dest='subj', required=False,
                      help='subject ID and folder name')
    parser.add_argument('-c','--config',
                      action='store', type=str, dest='config_file', default='config.json', required=True,
                      help='configuration file [default: %(default)s]')
    args = parser.parse_args(arg_str)
    return vars(args)

def check_cmdline_params(parameters, cmd_line):
    # if someone is using red bands they should ammend the checks I perform here
    allchars=string.maketrans('','')
    nodigs=allchars.translate(allchars, string.digits)
    if not ('box' not in cmd_line or cmd_line['box'] == int(parameters['panel_name'].encode('ascii','ignore').translate(allchars, nodigs))):
        print "box number doesn't match config and command line"
        return False
    if not ('subj' not in cmd_line or int(cmd_line['subj'].encode('ascii','ignore').translate(allchars, nodigs)) == int(parameters['subject'].encode('ascii','ignore').translate(allchars, nodigs))):
        print "subject number doesn't match config and command line"
        return False
    return True



def time_in_range(start, end, x):
    """Return true if x is in the range [start, end]"""
    if start <= end:
        return start <= x <= end
    else:
        return start <= x or x <= end

def is_day(latitude = '32.82', longitude = '-117.14'):
    """Is it daytime?

    (lat,long) -- latitude and longitude of location to check (default is San Diego)
    Returns True if it is daytime

    """
    import ephem
    obs = ephem.Observer()
    obs.lat = latitude # San Diego, CA
    obs.long = longitude
    sun = ephem.Sun()
    sun.compute()
    next_sunrise = ephem.localtime(obs.next_rising(sun))
    next_sunset = ephem.localtime(obs.next_setting(sun))
    return next_sunset < next_sunrise


def check_time(schedule,fmt="%H:%M"):
    """ determine whether trials should be done given the current time and the light schedule

    returns Boolean if current time meets schedule

    schedule='sun' will change lights according to local sunrise and sunset

    schedule=[('07:00','17:00')] will have lights on between 7am and 5pm
    schedule=[('06:00','12:00'),('18:00','24:00')] will have lights on between

    """
    if schedule == 'sun':
        if is_day():
            return True
    else:
        for epoch in schedule:
            assert len(epoch) is 2
            now = dt.datetime.time(dt.datetime.now())
            start = dt.datetime.time(dt.datetime.strptime(epoch[0],fmt))
            end = dt.datetime.time(dt.datetime.strptime(epoch[1],fmt))
            if time_in_range(start,end,now):
                return True
    return False

def wait(secs=1.0, final_countdown=0.0,waitfunc=None):
    """Smartly wait for a given time period.

    secs -- total time to wait in seconds
    final_countdown -- time at end of secs to wait and constantly poll the clock
    waitfunc -- optional function to run in a loop during hogCPUperiod

    If secs=1.0 and final_countdown=0.2 then for 0.8s python's time.sleep function will be used,
    which is not especially precise, but allows the cpu to perform housekeeping. In
    the final hogCPUsecs the more precise method of constantly polling the clock
    is used for greater precision.
    """
    #initial relaxed period, using sleep (better for system resources etc)
    if secs > final_countdown:
        time.sleep(secs-final_countdown)
        secs = final_countdown # only this much is now left

    #It's the Final Countdown!!
    #hog the cpu, checking time
    t0 = time.time()
    while (time.time()-t0) < secs:
        #let's see if any events were collected in meantime
        try:
            waitfunc()
        except:
            pass

def auditory_stim_from_wav(wav):
    with closing(wave.open(wav,'rb')) as wf:
        (nchannels, sampwidth, framerate, nframes, comptype, compname) = wf.getparams()

        duration = float(nframes)/sampwidth
        duration = duration * 2.0 / framerate
        stim = AuditoryStimulus(time=0.0,
                                duration=duration,
                                name=wav,
                                label='wav',
                                description='',
                                file_origin=wav,
                                annotations={'nchannels': nchannels,
                                             'sampwidth': sampwidth,
                                             'framerate': framerate,
                                             'nframes': nframes,
                                             'comptype': comptype,
                                             'compname': compname,
                                             }
                                )
    return stim

def concat_wav(input_file_list, output_filename='concat.wav'):
    """ concat a set of wav files into a single wav file and return the output filename

    takes in a tuple list of files and duration of pause after the file

    input_file_list = [
        ('a.wav', 0.1),
        ('b.wav', 0.09),
        ('c.wav', 0.0),
        ]

    returns a list of AuditoryStimulus objects

    TODO: add checks for sampling rate, number of channels, etc.
    """

    cursor = 0
    epochs = [] # list of file epochs
    audio_data = ''
    with closing(wave.open(output_filename, 'wb')) as output:
        for input_filename, isi in input_file_list:

            # read in the wav file
            with closing(wave.open(input_filename,'rb')) as wav_part:
                try:
                    params = wav_part.getparams()
                    output.setparams(params)
                    fs = output.getframerate()
                except: # TODO: what was I trying to except here? be more specific
                    pass

                audio_frames = wav_part.readframes(wav_part.getnframes())

            # append the audio data
            audio_data += audio_frames

            part_start = cursor
            part_dur = len(audio_frames)/params[1]

            epochs.append(AuditoryStimulus(time=float(part_start)/fs,
                                           duration=float(part_dur)/fs,
                                           name=input_filename,
                                           file_origin=input_filename,
                                           annotations=params,
                                           label='motif'
                                           ))
            cursor += part_dur # move cursor length of the duration

            # add isi
            if isi > 0.0:
                isi_frames = ''.join([struct.pack('h', fr) for fr in [0]*int(fs*isi)])
                audio_data += isi_frames
                cursor += len(isi_frames)/params[1]

        # concat all of the audio together and write to file
        output.writeframes(audio_data)


    description = 'concatenated on-the-fly'
    concat_wav = AuditoryStimulus(time=0.0,
                                  duration=epochs[-1].time+epochs[-1].duration,
                                  name=output_filename,
                                  label='wav',
                                  description=description,
                                  file_origin=output_filename,
                                  annotations=output.getparams(),
                                  )

    return (concat_wav,epochs)


def get_num_open_fds():
    '''
    return the number of open file descriptors for current process

    .. warning: will only work on UNIX-like os-es.
    '''

    pid = os.getpid()
    procs = subprocess.check_output(
        [ "lsof", '-w', '-Ff', "-p", str( pid ) ] )

    nprocs = len(
        filter(
            lambda s: s and s[ 0 ] == 'f' and s[1: ].isdigit(),
            procs.split( '\n' ) )
        )
    return nprocs

def rand_from_log_shape_dist(alpha=10):
    """
    randomly samples from a distribution between 0 and 1 with pdf shaped like the log function
    low probability of getting close to zero, increasing probability going towards 1
    alpha determines how sharp the curve is, higher alpha, sharper curve.
    """
    beta = (alpha + 1) * np.log(alpha + 1) - alpha
    t = random.random()
    ret = ((beta * t-1)/(sp.special.lambertw((beta*t-1)/np.e)) - 1) / alpha
    return max(min(np.real(ret), 1), 0)
