import ephem, wave, sys, struct
import datetime as dt
from optparse import OptionParser


def parse_commandline(args=sys.argv[1:]):
    """ parse command line arguments
    note: optparse is depreciated w/ v2.7 in favor of argparse
    
    """
    parser=OptionParser()
    parser.add_option('-B', '--box',
                      action='store', type='int', dest='box',
                      help='(int) box identifier')
    parser.add_option('-S', '--subject',
                      action='store', type='string', dest='subj',
                      help='(string) subject ID and folder name')
    parser.add_option('-c','--config',
                      action='store', type='string', dest='config_file', default='config.json',
                      help='(string) configuration file [default: %default]')
    parser.set_defaults()
    (options, args) = parser.parse_args(args)
    return (options, args)


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

    schedule=('07:00','17:00') will have lights on between 7am and 5pm
    schedule=[('06:00','12:00'),('18:00','24:00')] will have lights on between

    """
    if type(schedule) is str:
        if 'sun' in schedule:
            if is_day():
                return True
    elif type(schedule) is tuple:
        now_time = dt.datetime.time(dt.datetime.now())
        on_time = dt.datetime.time(dt.datetime.strptime(epoch[0],fmt))
        off_time = dt.datetime.time(dt.datetime.strptime(epoch[1],fmt))
        if (now_time > on_time) and (now_time < off_time):
            return True

    elif type(schedule) is list:
        for epoch in schedule:
            if 'sun' in epoch:
                if is_day():
                    return True
            else:
                now_time = dt.datetime.time(dt.datetime.now())
                on_time = dt.datetime.time(dt.datetime.strptime(epoch[0],fmt))
                off_time = dt.datetime.time(dt.datetime.strptime(epoch[1],fmt))
                if (now_time > on_time) and (now_time < off_time):
                    return True
    return False

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

def write_summaryDAT(summary,summaryDAT_fname):
    """ takes in a summary dictionary and options and writes to the bird's summaryDAT"""
    with open(summaryDAT_fname,'wb') as f:
        f.write("Last trial run @: %s\n" % summary['last_trial_time'])
        f.write("Feeder ops today: %i\n" % summary['feeds'])
        f.write("Hopper failures today: %i\n" % summary['hopper_failures'])
        f.write("Hopper won't go down failures today: %i\n" % summary['hopper_wont_go_down'])
        f.write("Hopper already up failures today: %i\n" % summary['hopper_already_up'])
        f.write("Responses during feed: %i\n" % summary['responses_during_feed'])
        f.write("Rf'd responses: %i\n" % summary['responses'])
