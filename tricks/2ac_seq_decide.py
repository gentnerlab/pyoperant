#!/usr/bin/python

## TODO:
# Save rDAT and trial info
# Implement Error Handling
# Add support for correction trials
# Add support for probe trials

# from psychopy import core, data, logging, sound
import os, sys, imp, wave, random
import numpy as np
import datetime as dt
from optparse import OptionParser
from pyoperant import hwio, misc
from scipy.io import wavfile

class GoodNite(Exception):
    """ exception for when the lights should be off """
    pass

def parse_commandline(args=sys.argv[1:]):
    # parse command line arguments
    # note: optparse is depreciated w/ v2.7 in favor of argparse
    parser=OptionParser()
    parser.add_option('-B','--box',
                      action='store',type='int',dest='box',
                      help='(int) box identifier')
    parser.add_option('-S','--subject',
                      action='store',type='string',dest='subj',
                      help='(string) subject ID and folder name')
    parser.add_option('-c','--config',
                      action='store',type='string',dest='config_file',default='config.py',
                      help='(string) configuration file [default: %default]')
    parser.set_defaults()
    (options, args) = parser.parse_args(args)
    return (options,args)
  
def do_trials(schedule):
    """ determine whether trials should be done given the current time and the light schedule"""
    if 'sun' in schedule:
        return misc.is_day()
    else:
        pass
        # TODO: check if the time is during an interval defined by tuples

# def concat_wav(input_file_list,output_filename='temp.wav'):
#     """ concat a set of wav files into a single wav file and return the output filename"""
#     # TODO: rewrite this without scipy's wavfile module
#     out_data = np.array([],dtype=np.int16)
#     out_fs = 44100
#     toe = 0
#     timestamps = [toe]
#     for item in input_file_list:
#         if isinstance(item,str):
#             (fs,data) = wavfile.read(item)
#         elif isinstance(item,float):
#             data = np.zeros(item*out_fs,dtype=np.int16)

#         out_data = np.append(out_data,data)
#         toe += len(data)
#         timestamps.append(toe)

#     timestamps = [float(t)/out_fs for t in timestamps]
#     wavfile.write(output_filename,out_fs,out_data)
#     return (output_filename,timestamps)

def concat_wav(input_file_list,output_filename='temp_concat.wav'):
    """ concat a set of wav files into a single wav file and return the output filename"""
    # TODO: add checks for sampling rate, number of channels, etc.
    output = wave.open(output_filename,'wb')

    toe = 0
    timestamps = [toe]
    for item in input_file_list:
        if isinstance(item,str):
            w = wave.open(item,'rb')
            output.setparams(w.getparams())
            data = w.readframes(w.getnframes())
            w.close()

        elif isinstance(item,float):
            fs = output.getframerate()
            data = ''.join([chr(fr) for fr in [0]*int(fs*item)])
        
        output.append(data)
        toe += len(data)
        timestamps.append(toe)

    timestamps = [float(t)/out_fs for t in timestamps]
    output.close()
    return (output_filename,timestamps)


def get_stimulus(trial_class,options):
    """ take trial class and experimental options and return a tuple containing the wav filename & additional info to play """
    # determine stimulus for next trial, based on class
    trial_string = []
    trial_isi = []
    stim = 0
    for item in range(options['strlen_max']):
        stim = (np.cumsum(options['models'][trial_class][stim]) < random.random()).sum()
        trial_string.append(stim)
        trial_isi.append(random.gauss(options['isi_mean'],options['isi_stdev']))

    # make the stimulus and save as temp wav file
    stim_full = []
    for loc, stim_id in enumerate(trial_string):
        stim_full.append(options['stims'].values()[stim_id-1])
        stim_full.append(trial_isi[loc])
    stim_full.pop(len(stim_full)-1)

    return concat_wav(stim_full, os.path.join(options['stim_path'],'temp_concat.wav') )


if __name__ == "__main__":

    (cmd_line,args) = parse_commandline()

    # set path variables
    CODE_PATH = os.path.dirname(os.path.realpath(__file__))
    USER_PATH = os.path.expanduser('~')
    BIRD_PATH = os.path.join(USER_PATH,'opdat',cmd_line.subj)
    STIM_PATH = os.path.join(BIRD_PATH,'stims')  

    config = {}; 
    execfile(os.path.join(BIRD_PATH,cmd_line.config_file),config)
    options = config.get('options')
    options['subject_id'] = cmd_line.subj
    options['code_path'] = CODE_PATH
    options['user_path'] = USER_PATH
    options['bird_path'] = BIRD_PATH
    options['stim_path'] = STIM_PATH

    # run through stim files
    for name,filename in options['stims'].items():
        filename_full = os.path.join(options['stim_path'],filename)
        options['stims'][name] = filename_full

    # define log files, rDAT files
    filetime_fmt = '%Y-%m-%d_%H:%M:%S'
    options['log_file'] = options['subject_id'] + '_log.txt'
    options['rDAT_file'] = options['subject_id'] + dt.datetime.now().strftime(filetime_fmt)

    # initialize box
    box = hwio.OperantBox(cmd_line.box)
    box.reset()

    trial_cum_correct = 0
    trial_num_correct_thresh = options['variable_ratio']

    # start experiment
    do_experiment = True
    while do_experiment:

        try:
            # first, check if we should be running trials, otherwise lightsout
            if not do_trials(options['light_schedule']):
                raise GoodNite()

            # make sure lights are on at the beginning of each trial, prep for trial
            box.lights_on()
            
            trial_class = random.choice(options['models'].keys())
            wav = {}
            (wav['filename'],wav['timestamps']) = get_stimulus(trial_class,options)
            wav['dur'] = wav['timestamps'][-1]
            
            # wait for bird to peck
            no_peck = True
            box.write(box.id_LEDcenter,True)
            while no_peck:
                no_peck = not box.read(box.id_IRcenter)

                if not do_trials(options['light_schedule']):
                    raise GoodNite()

            trial_start_peck = dt.datetime.now()
            box.write(box.id_LEDcenter,False)
            # TODO: note trial initiation in event file

            hwio.wait(1.0)

            # play temp stimulus
            trial_stimstart = dt.datetime.now()
            wave_proc = box.play_wav(wav['filename'])
            # TODO: note wave played in event file

            # wait for response
            wait_min = wav['timestamps'][2*options['strlen_min']-1]
            print wav['timestamps']
            hwio.wait(wait_min)
            check_peck = True
            box.write(box.id_LEDleft,True)
            box.write(box.id_LEDright,True)
            while check_peck:
                elapsed_time = dt.datetime.now() - trial_stimstart
                if elapsed_time > dt.timedelta(seconds=(options['response_win'] + wav['dur'])):
                    trial_resp = 'none'
                    check_peck = False
                elif box.read(box.id_IRleft):
                    trial_peck_time = dt.datetime.now()
                    wave_proc.terminate()
                    trial_resp = 'L'
                    check_peck = False
                elif box.read(box.id_IRright):
                    trial_peck_time = dt.datetime.now()
                    wave_proc.terminate()
                    trial_resp = 'R'
                    check_peck = False 
            # TODO: note response in event file
            box.write(box.id_LEDleft,False)
            box.write(box.id_LEDright,False)
            trial_rt = elapsed_time

            if trial_resp == 'none':
                pass
            elif trial_resp == trial_class: 
                if trial_cum_correct >= trial_num_correct_thresh:
                    trial_feed_time = (dt.datetime.now(),[])
                    box.feed(options['feed_dur'], options['secondary_reinf'])
                    trial_feed_time[1] = dt.datetime.now()
                    
                    trial_cum_correct = 0
                    trial_num_correct_thresh = random.uniform(1,2*options['variable_ratio']-1)

                elif options['secondary_reinf']:
                    box.flash(dur=options['feed_dur'])
                    trial_cum_correct += 1
            else:
                box.timeout(options['timeout_dur'])
                trial_cum_correct = 0

            # write trial results to rDAT
                

        except GoodNite:
            box.lights_off()
            hwio.wait(60.0)



