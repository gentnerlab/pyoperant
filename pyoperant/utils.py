import wave
import sys
import struct
import time
import datetime as dt
from argparse import ArgumentParser

import ephem


## defining Error classes for operant HW control
class Error(Exception):
    '''base class for exceptions in this module'''
    pass


# consider importing this from python-neo
class Event(object):
    """docstring for Event"""
    def __init__(self, time, duration=None, label=None, name=None, description=None, file_origin=None, **annotations):
        super(Event, self).__init__()
        assert isinstance(time, float)
        assert isinstance(label, str)
        self.time = time
        self.duration = duration
        self.label = label
        self.name = name
        self.description = description
        self.file_origin = file_origin
        self.annotations = annotations


class Stimulus(Event):
    """docstring for Stimulus"""
    def __init__(self, *args, **kwargs):
        super(Stimulus, self, *args, **kwargs).__init__()
        for key, value in kwargs.items():
            setattr(self, key, value)



class AuditoryStimulus(Stimulus):
    """docstring for AuditoryStimulus"""
    def __init__(self, *args, **kwargs):
        super(AuditoryStimulus, self, *args, **kwargs).__init__()
        pass


def parse_commandline(arg_str=sys.argv[1:]):
    """ parse command line arguments
    note: optparse is depreciated w/ v2.7 in favor of argparse

    """
    parser=ArgumentParser()
    parser.add_argument('-B', '--box',
                      action='store', type=int, dest='box',
                      help='(int) box identifier')
    parser.add_argument('-S', '--subject',
                      action='store', type=str, dest='subj',
                      help='subject ID and folder name')
    parser.add_argument('-c','--config',
                      action='store', type=str, dest='config_file', default='config.json',
                      help='configuration file [default: %(default)s]')
    args = parser.parse_args(arg_str)
    return vars(args)

def is_day((latitude, longitude) = ('32.82', '-117.14')):
    """Is it daytime?

    (lat,long) -- latitude and longitude of location to check (default is San Diego*)
    Returns True if it is daytime

    * Discovered by the Germans in 1904, they named it San Diego,
    which of course in German means a whale's vagina. (Burgundy, 2004)
    """
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
    if schedule is 'sun':
        if is_day():
            return True
    else:
        for epoch in schedule:
            assert len(epoch) is 2
            now = datetime.datetime.time(datetime.datetime.now())
            start = datetime.datetime.time(datetime.datetime.strptime(epoch[0],fmt))
            end = datetime.datetime.time(datetime.datetime.strptime(epoch[1],fmt))
            if time_in_range(start,end,now):
                return True
        else:
            raise Error('unknown epoch: %s' % epoch)
    return False

def wait(secs=1.0, final_countdown=0.2,waitfunc=None):
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
    epochs = [] # list of tuples defining file epochs
    audio_data = ''
    output = wave.open(output_filename, 'wb')

    try:
        for input_filename, isi in input_file_list:

            # read in the wav file
            wav_part = wave.open(input_filename,'rb')


            try:
                params = wav_part.getparams()
                output.setparams(params)
                fs = output.getframerate()
            except: # TODO: what was I trying to except here? be more specific
                pass

            audio_frames = wav_part.readframes(wav_part.getnframes())
            wav_part.close

            # append the audio data
            audio_data += audio_frames

            part_start = cursor
            part_dur = len(audio_frames)/params[1]

            epochs.append(AuditoryStimulus(time=float(part_start)/fs,
                                           duration=float(part_dur)/fs,
                                           name=input_filename,
                                           file_origin=input_filename,
                                           annotations=params,
                                           ))
            cursor += part_dur # move cursor length of the duration

            # add isi
            if isi > 0.0:
                isi_frames = ''.join([struct.pack('h', fr) for fr in [0]*int(fs*isi)])
                audio_data += isi_frames
                cursor += len(isi_frames)/params[1]

        # concat all of the audio together and write to file
        output.writeframes(audio_data)

    finally:
        output.close()

    concat_wav = AuditoryStimulus(time=0.0,
                                  duration=epochs[-1].time+epochs[-1].duration,
                                  name=output_filename,
                                  label='wav',
                                  description=description,
                                  file_origin=output_filename,
                                  annotations=output.getparams(),
                                  )

    return (concat_wav,epochs)

class Experiment(object):
    """docstring for Experiment"""
    def __init__(self, *args, **kwargs):
        super(Experiment,  *args, **kwargs).__init__()
        for key, value in kwargs.items():
            setattr(self, key, value)

        self.filetime_fmt = '%Y-%m-%d-%H-%M-%S'
        self.exp_timestamp = dt.datetime.now().strftime(self.filetime_fmt)


    def log_config(self):
        if self.debug:
            self.log_level = logging.DEBUG
        else:
            self.log_level = logging.INFO

        logging.basicConfig(filename=self.log_file,
                            level=self.log_level,
                            format='"%(asctime)s","%(levelname)s","%(message)s"')
        self.log = logging.getLogger()
        #email_handler = logging.handlers.SMTPHandler(mailhost='localhost',
        #                                             fromaddr='bird@vogel.ucsd.edu',
        #                                             toaddrs=[options['experimenter']['email'],],
        #                                             subject='error notice',
        #                                             )
        #email_handler.setlevel(logging.ERROR)
        #log.addHandler(email_handler)

    def init_summary():
        """ initializes an empty summary dictionary """
        self.summary = {'trials': 0,
                        'feeds': 0,
                        'hopper_failures': 0,
                        'hopper_wont_go_down': 0,
                        'hopper_already_up': 0,
                        'responses_during_feed': 0,
                        'responses': 0,
                        'last_trial_time': [],
                        }

    def write_summary(self):
        """ takes in a summary dictionary and options and writes to the bird's summaryDAT"""
        with open(self.options['summaryDAT'],'wb') as f:
            f.write("Trials this session: %s\n" % summary['trials'])
            f.write("Last trial run @: %s\n" % summary['last_trial_time'])
            f.write("Feeder ops today: %i\n" % summary['feeds'])
            f.write("Hopper failures today: %i\n" % summary['hopper_failures'])
            f.write("Hopper won't go down failures today: %i\n" % summary['hopper_wont_go_down'])
            f.write("Hopper already up failures today: %i\n" % summary['hopper_already_up'])
            f.write("Responses during feed: %i\n" % summary['responses_during_feed'])
            f.write("Rf'd responses: %i\n" % summary['responses'])

