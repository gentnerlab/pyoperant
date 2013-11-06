import wave
import sys
import struct
import datetime as dt
from argparse import ArgumentParser

import ephem


## defining Error classes for operant HW control
class Error(Exception):
    '''base class for exceptions in this module'''
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

def concat_wav(input_file_list, output_filename='temp_concat.wav'):
    """ concat a set of wav files into a single wav file and return the output filename

    takes in a tuple list of files and duration of pause after the file

    input_file_list = [
        ('a.wav', 0.1),
        ('b.wav', 0.09),
        ('c.wav', 0.0),
        ]

    TODO: add checks for sampling rate, number of channels, etc.
    """
    output = wave.open(output_filename, 'wb')
    toe = 0
    epochs = [] # list of tuples defining file epochs
    audio_data = []
    for input_filename, post_quiet in input_file_list:

        wav_part = wave.open(input_filename,'rb')

        # TODO: add some checks in here
        try:
            params = wav_part.getparams()
            output.setparams(params)
            fs = output.getframerate()
        except:
            pass

        frames = wav_part.readframes(wav_part.getnframes())
        wav_part.close

        start_time = toe
        toe += len(frames)/params[1]

        audio_data.append(frames)
        epochs.append((float(start_time)/fs,float(toe)/fs))

        if post_quiet > 0.0:
            isi_frames = ''.join([struct.pack('h', fr) for fr in [0]*int(fs*post_quiet)])
            toe += len(isi_frames)/params[1]
            audio_data.append(isi_frames)

    data = ''.join(audio_data)
    output.writeframes(data)

    output.close()
    return (output_filename,epochs)

class Experiment(object):
    """docstring for Experiment"""
    def __init__(self, *args, **kwargs):
        super(Experiment,  *args, **kwargs).__init__()


    def log_config(self):
        if self.options['debug']:
            self.log_level = logging.DEBUG
        else:
            self.log_level = logging.INFO

        logging.basicConfig(filename=self.options['log_file'], 
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


class Event(object):
    """docstring for Event"""
    def __init__(self, time, duration=None, label, name=None, description=None, file_origin=None, **annotations):
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
        