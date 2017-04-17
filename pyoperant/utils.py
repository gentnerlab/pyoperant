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
import fractions

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

def is_day((latitude, longitude) = ('32.82', '-117.14')):
    """Is it daytime?

    (lat,long) -- latitude and longitude of location to check (default is San Diego*)
    Returns True if it is daytime

    * Discovered by the Germans in 1904, they named it San Diego,
    which of course in German means a whale's vagina. (Burgundy, 2004)
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
    
'''
Resample

Created on Apr 7, 2011
by Uri Nieto
uri@urinieto.com
Modified for pyoperant by Tim Sainburg (Jan 2016)

Sample Rate converter from 48kHz to 44.1kHz.

USAGE:
$>python resample.py -i input.wav [-o output.wav -q [0.0-1.0]]

EXAMPLES:
$>python resample.py -i onades.wav
$>python resample.py -i onades.wav -o out.wav
$>python resample.py -i onades-mono.wav -q 0.8
$>python resample.py -i onades.wav -o out3.wav -q 0.5

DESCRIPTION:
The input has to be a WAV file sampled at 48 kHz/sec
with a resolution of 16 bits/sample. It can have n>0
number of channels (i.e. 1=mono, 2=stereo, ...).

The output will be a WAV file sampled at 44.1 kHz/sec
with a resolution of 16 bits/sample, and the same
number of channels as the input.

A quality parameter q can be provided (>0.0 to 1.0), and
it will modify the number of zero crossings of the filter, 
making the output quality best when q = 1.0 and very bad 
as q tends to 0.0

The sample rate factor is:

 44100     147
------- = ----- 
 48000     160
 
To do the conversion, we upsample by 147, low pass filter, 
and downsample by 160 (in this order). This is done by
using an efficient polyphase filter bank with resampling 
algorithm proposed by Vaidyanathan in [2].

The low pass filter is an impulse response windowed
by a Kaiser window to have a better filtering 
(around -60dB in the rejection band) [1].

As a comparison between the Kaiser Window and the
Rectangular Window, this algorithm plotted the following
images included with this package:

KaiserIR.png
KaiserFR.png
RectIR.png
RectFR.png

The images show the Impulse Responses and the Frequency
Responses of the Kaiser and Rectangular Windows. As it can be
clearly seen, the Kaiser window has a gain of around -60dB in the
rejection band, whereas the Rect window has a gain of around -20dB
and smoothly decreasing to -40dB. Thus, the Kaiser window
method is rejecting the aliasing much better than the Rect window.

The Filter Design is performed in the function:
designFIR()

The Upsampling, Filtering, and Downsampling is
performed in the function:
upSampleFilterDownSample()

Also included in the package are two wav files sampled at 48kHz
with 16bits/sample resolution. One is stereo and the other mono:

onades.wav
onades-mono.wav

NOTES:
You need numpy and scipy installed to run this script.
You can find them here:
http://numpy.scipy.org/

You may want to have matplotlib as well if you want to 
print the plots by yourself (commented right now)

This code would be much faster on C or C++, but my decision
on using Python was to make the code more readable (yet useful)
rather than focusing on performance.

@author: uri

REFERENCES:
[1]: Smith, J.O., "Spectral Audio Signal Processing", 
W3K Publishing, March 2010

[2] Vaidyanathan, P.P., "Multirate Systems and Filter Banks", 
Prentice Hall, 1993.

COPYRIGHT NOTES:

Copyright (C) 2011, Uri Nieto

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
 
'''


'''
h = flipTranspose(h, L, cpp)
...
Desc: Flips and Transposes the impulse response h, dividing
it into L different phases with cpp coefficients per phase.
Following as described in [2].
...
h: Impulse response to flip and Transpose
L: Upsampling Factor
cpp: Coeficients per Phase
return hh: h flipped and transposed following the descritpion
'''
def flipTranspose(h, L, cpp):
    
    # Get the impulse response size
    N = len(h)
    
    # Init the output to 0
    hh = np.zeros(N)
    
    # Flip and Transpose:
    for i in range(L):
        hh[cpp - 1 + i*cpp:-N - 1 + i*cpp:-1] = h[i:cpp*L:L]
                    
    return hh

'''
h = upSampleFilterDownSample(x, h, L, M)
...
Desc: Upsamples the input x by L, filters it out using h, and
downsamples it by M.

The algorithm is based on the "efficient polyphase filter bank 
with resampling" found on page 129 of the book [2] (Figure 4.3-8d).

...
x: input signal
h: impulse response (assumes it has the correct cut-off freq)
L: Upsampling Factor
M: Downsampling Factor
returns y: output signal (x upsampled, filtered, and downsampled)
'''
def upSampleFilterDownSample(x, h, L, M):
    
    # Number of samples to convert
    N = len(x)
    
    # Compute the number of coefficients per phase
    cpp = len(h) / L
    
    # Flip and Transpose the impulse response
    h = flipTranspose(h, L, cpp)
    
    #Check number of channels
    if (np.shape(np.shape(x)) == (2,)):
        nchan = np.shape(x)[1]
        y = np.zeros((np.ceil(N*L/float(M)), nchan))
    else:
        nchan = 1
        y = np.zeros(np.ceil(N*L/float(M)))
    
    # Init the output index
    y_i = 0
    
    # Init the phase index
    phase_i = 0
    
    # Init the main loop index
    i = 0
    
    # Main Loop
    while i < N:
        
        # Print % completed
        if (i % 30000 == 0):
            print("%.2f %% completed" % float(100*i/float(len(x))))

        # Compute the filter index
        h_i = phase_i*cpp
        
        # Compute the input index
        x_i = i - cpp + 1;
        
        # Update impulse index if needed (offset)
        if x_i < 0:
            h_i -= x_i
            x_i = 0
        
        # Compute the current output sample
        rang = i - x_i + 1
        if nchan == 1:
            y[y_i] = np.sum(x[x_i:x_i + rang] * h[h_i:h_i + rang])
        else:
            for c in range(nchan):
                y[y_i,c] = np.sum(x[x_i:x_i + rang,c] * h[h_i:h_i + rang])     
        
        # Add the downsampling factor to the phase index
        phase_i += M
        
        # Compute the increment for the index of x with the new phase
        x_incr = phase_i / int(L)
        
        # Update phase index
        phase_i %= L
        
        # Update the main loop index
        i += x_incr
        
        # Update the output index
        y_i += 1
        
    return y
    
    
'''
h = impulse(M, L)
...
M: Impulse Response Size
T: Sampling Period
returns h: The impulse response
'''
def impulse(M, T):
    
    # Create time array
    n = np.arange(-(M-1)/2, (M-1)/2 + 1)
    
    # Compute the impulse response using the sinc function
    h = (1/T)*np.sinc((1/T)*n)
        
    return h

'''
b = bessel(x)
...
Desc: Zero-order modified Bessel function of the first kind, with
approximation using the Maclaurin series, as described in [1]
...
x: Input sample
b: Zero-order modified Bessel function of the first kind
'''
def bessel(x):
    return np.power(np.exp(x),2);

'''
k = kaiser(M, beta)
...
Desc: Generates an M length Kaiser window with the
specified beta parameter. Following instructions in [1]
...
M: Number of samples of the window
beta: Beta parameter of the Kaiser Window
k: array(M,1) containing the Kaiser window with the specified beta
'''
def kaiser(M, beta):
    
    # Init Kaiser Window
    k = np.zeros(M)
    
    # Compute each sample of the Kaiser Window
    i = 0
    for n in np.arange(-(M-1)/2,(M-1)/2 + 1):
        samp = beta*np.sqrt(1-np.power((n/(M/2.0)),2))
        samp = bessel(samp)/float(bessel(beta))
        k[i] = samp
        i = i + 1
    
    return k

'''
h = designFIR(N, L, M)
...
Desc: Designs a low pass filter to perform the conversion of 
sampling frequencies given the upsampling and downsampling factors.
It uses the Kaiser window to better filter out aliasing.
...
N: Maximum size of the Impulse Response of the FIR
L: Upsampling Factor
M: Downsampling Factor
returns h: Impulse Response of the FIR
'''
def designFIR(N, L, M):
    
    # Get the impulse response with the right Sampling Period
    h0 = impulse(N, float(M))
    
    # Compute a Kaiser Window
    alpha = 2.5 # Alpha factor for the Kaiser Window
    k = kaiser(N, alpha*np.pi)
    
    # Window the impulse response with the Kaiser window
    h = h0 * k
    
    # Filter Gain
    h = h * L
    
    # Reduce window by removing almost 0 values to improve filtering
    for i in range(len(h)):
        if abs(h[i]) > 1e-3:
            for j in range(i,0,-1):
                if abs(h[j]) < 1e-7:
                    h = h[j:len(h)-j]
                    break
            break
    

    return h

def resampleAudio(input_wav, input_fr, output_fr):
  q = 1
  Nz = int(25*q) 
  frac = fractions.Fraction(float(44100)/float(48000)).limit_denominator()
  L = frac.numerator
  M = frac.denominator 
  in_nbits = input_wav.dtype
  out_nbits = in_nbits 
  h = designFIR(Nz*L, L, M) 
  # Upsample, Filter, and Downsample
  out_data = upSampleFilterDownSample(input_wav, h, L, M)  
  # Make sure the output is 16 bits
  out_data = out_data.astype(out_nbits)
  return out_data


