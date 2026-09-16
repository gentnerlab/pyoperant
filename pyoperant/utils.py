import wave
import sys
import struct
import time
import subprocess
import threading
import traceback
import shlex
import os
import json
import logging
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
        except Exception as e:
            if error_callback:
                error_callback(e)
                state = error_state
            else:
                raise


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
        if isinstance(command, str):
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
    def digits_only(s):
        return ''.join(c for c in s if c.isdigit())
    # panel_hw_id (preferred) / panel_name (legacy) -- see base.py's
    # BaseExp.__init__. A post-init self.parameters always has both
    # mirrored; falling back covers a raw, pre-init config dict too.
    panel_hw_id = parameters.get('panel_hw_id', parameters.get('panel_name'))
    if 'box' in cmd_line and cmd_line['box'] is not None:
        # A safety check, not a resolution change: panel_hw_id can be
        # missing or non-numeric (e.g. a fleet config.json that still has
        # a hostname like "Magpi11" sitting in this field -- see
        # resolve_panel_hw_id()'s docstring for the full history). Fail
        # with a clear message rather than a bare TypeError/ValueError
        # from digits_only(None) or int('').
        if not panel_hw_id or not digits_only(panel_hw_id):
            print("Cannot verify box number: config's panel_hw_id/panel_name "
                  "is missing or non-numeric (%r)" % (panel_hw_id,))
            return False
        if cmd_line['box'] != int(digits_only(panel_hw_id)):
            print("box number doesn't match config and command line")
            return False
    if not ('subj' not in cmd_line or int(digits_only(cmd_line['subj'])) == int(digits_only(parameters['subject']))):
        print("subject number doesn't match config and command line")
        return False
    return True


# Default PANELS[...] key for a box that doesn't specify one -- every
# board has exactly one wired panel today (see resolve_panel_hw_id()).
DEFAULT_PANEL_HW_ID = '1'


def resolve_panel_hw_id(cli_value, config_value, panels, default=DEFAULT_PANEL_HW_ID,
                         logger=None):
    """Resolve which key of `panels` (e.g. local_pi_revd.PANELS) this run
    should control.

    Historical context: `panels`/`-P`/panel_hw_id used to mean "which of
    several panels on this one shared machine" back when the lab ran every
    box from a single central computer. Since migrating to today's
    client-server architecture (each box is its own independent Pi with
    exactly one panel), that mechanism is vestigial -- `panels` is always a
    single-entry `{"1": ...}` dict -- while `panel_subject_behavior`'s own,
    unrelated "panel" column took on a new meaning (the box's SSH
    hostname). The two never got reconciled, and some fleet boxes ended up
    with their hostname mistakenly written into config.json's
    panel_hw_id/panel_name field instead of "1" (e.g. "Magpi11").

    Priority order: an explicit CLI value always wins -- a bad CLI value is
    an explicit user request and is left to raise clearly below, not
    silently substituted. Otherwise config.json's own panel_hw_id/
    panel_name is used, but only if it's actually a valid key of `panels`;
    an unresolved/stale config value (like the "Magpi11" case above) falls
    back to `default` instead of crashing an unattended, cron-driven box,
    with a warning logged when possible so the bad config can still be
    noticed and fixed.
    """
    if cli_value is not None:
        resolved = cli_value
    elif config_value is not None and config_value in panels:
        resolved = config_value
    else:
        if config_value is not None and logger is not None:
            logger.warning(
                "config panel_hw_id/panel_name %r is not a valid panel on "
                "this box (valid: %s); falling back to default panel %r.",
                config_value, sorted(panels), default,
            )
        resolved = default
    if resolved not in panels:
        raise KeyError(
            "panel_hw_id %r is not a valid panel on this box (valid: %s)"
            % (resolved, sorted(panels))
        )
    return resolved


try:
    from pyoperant.local import PANEL_CONFIG_PATH
except ImportError:
    PANEL_CONFIG_PATH = '/home/bird/panel_config.json'


def load_panel_config(path=PANEL_CONFIG_PATH):
    """Reads this box's panel_config.json -- physical-hardware calibration
    (e.g. Rev D's hopper servo hopper_up_angle/hopper_down_angle) that
    belongs to this specific box, not to whichever subject happens to be
    assigned to it. Unlike a subject's config.json, this file is meant to
    survive a bird being swapped out -- see local_pi_revd.py's
    PiPanel.__init__ and scripts/tune_servo.py, which writes it.

    Returns {} if the file doesn't exist (a box with no hardware overrides
    yet -- normal, not an error) or can't be parsed (logged as a warning
    -- a bad calibration file should never crash the whole experiment,
    it should just fall back to PiPanel's own hardcoded defaults).
    """
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (IOError, ValueError) as e:
        logging.getLogger('pyoperant').warning(
            "Could not read panel config %s: %s -- using hardware defaults", path, e
        )
        return {}



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
            assert len(epoch) == 2
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
    audio_data = b''
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
                isi_frames = b''.join([struct.pack('h', fr) for fr in [0]*int(fs*isi)])
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

    .. warning: will only work on UNIX-like OSes with /dev/fd (Linux --
    where /dev/fd is a standard symlink to /proc/self/fd -- and macOS,
    used for dev-machine testing). Previously shelled out to lsof, which
    isn't installed on a minimal Raspberry Pi OS image and isn't in this
    project's offline package set -- that raised FileNotFoundError, which
    run_state_machine()'s error_callback silently swallows unless the
    exception is InterfaceError/ComponentError, so a session would fail
    on every single trial without any error in the log.
    '''
    return len(os.listdir('/dev/fd'))

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
