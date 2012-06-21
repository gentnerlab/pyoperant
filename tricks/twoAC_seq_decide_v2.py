#!/usr/bin/python

## TODO:
# Save rDAT and trial info
# Implement Error Handling
# Add support for correction trials
# Add support for probe trials

import os, sys, random, csv, logging, json
import numpy as np
import datetime as dt
from pyoperant import hwio, utils

class GoodNite(Exception):
    """ exception for when the lights should be off """
    pass

def get_stimulus(trial_class,options):
    """ take trial class and experimental options and return a tuple containing the wav filename & additional info to play 

    take in the trial class and the options dict
    returns a stimulus dictionary

    """
    # determine stimulus for next trial, based on class
    stim = dict()
    stim['class'] = trial_class

    stim['string'] = []
    input_file_list = []
    trial_isi = []
    motif_id = 0
    cum_matrix = np.cumsum(options['models'][trial_class], axis=1)
    for item in range(options['strlen_max']):
        motif_id = (cum_matrix[motif_id] < random.random()).sum()
        motif_name = options['stim_map'][motif_id]
        isi = random.gauss(options['isi_mean'], options['isi_stdev'])
        if isi < 0.0: isi = 0.0
        input_file_list.append((options['stims'][motif_name], isi))
        stim['string'].append(motif_name)
    input_file_list[-1] = (input_file_list[-1][0], 0.0)
    stim['input_file_list'] = input_file_list

    (stim['filename'], stim['epochs']) = utils.concat_wav(stim['input_file_list'], os.path.join(options['stim_path'], 'temp_concat.wav'))

    stim['dur'] = stim['epochs'][-1][-1]
  
    return stim


def get_options((cmd_line,args)):
    """ get all of the configuration options for the experiment """

    # set path variables
    CODE_PATH = os.path.dirname(os.path.realpath(__file__))
    USER_PATH = os.path.expanduser('~')
    BIRD_PATH = os.path.join(USER_PATH,'opdat', 'B' + cmd_line.subj)
    STIM_PATH = os.path.join(BIRD_PATH,'stims')

    with open(os.path.join(BIRD_PATH, cmd_line.config_file)) as config_f:
        options = json.load(config_f)
    options['box_id'] = cmd_line.box
    options['subject_id'] = cmd_line.subj
    options['code_path'] = CODE_PATH
    options['user_path'] = USER_PATH
    options['bird_path'] = BIRD_PATH
    options['stim_path'] = STIM_PATH
    options['script_fname'] = os.path.basename(__file__)

    # run through stim files
    for name, filename in options['stims'].items():
        filename_full = os.path.join(options['stim_path'], filename)
        options['stims'][name] = filename_full

    # run through the transitions for each stimulus and generate transition matrixes
    n = len(options['stims'])
    options['models'] = {}
    for stim_class, pair_set in options['diagnostic_transitions'].items():
        mat = np.zeros((n+1,n+1))
        mat[0][1:] = 1.0/n
        for pair in pair_set:
            mat[pair[0]][1:] = (1-options['alpha'])/(n-1)
            mat[pair[0]][pair[1]] = options['alpha']
        options['models'][stim_class] = mat
   
    # define log files, rDAT files
    filetime_fmt = '%Y%m%d%H%M%S'
    options['log_file'] = os.path.join(options['bird_path'], options['subject_id'] + '.log')
    options['data_csv'] = os.path.join(options['bird_path'], options['subject_id'] + '_' + options['script_fname'] + '_' + dt.datetime.now().strftime(filetime_fmt) + '.csv')
    options['summaryDAT'] = os.path.join(options['bird_path'], options['subject_id'] + '.summaryDAT')
    options['fields_to_save'] = ['trial_start','class','stim_start','stim_string','response','feed','timeout','cum_correct','cum_correct_thresh']
    with open(options['data_csv'], 'wb') as data_fh:
        trialWriter = csv.writer(data_fh)
        trialWriter.writerow(options['fields_to_save'])

    return options

if __name__ == "__main__":

    options = get_options(utils.parse_commandline())

    if options['debug']:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    logging.basicConfig(filename=options['log_file'], 
                        level=log_level,
                        format='%(asctime)s:%(levelname)s:%(message)s')
    log = logging.getLogger()

    # initialize box
    box = hwio.OperantBox(options['box_id'])
    box.reset()

    trial = dict()
    trial['cum_correct'] = 0
    trial['cum_correct_thresh'] = 1

    summary = {'trials': 0,
               'feeds': 0,
               'hopper_failures': 0,
               'hopper_wont_go_down': 0,
               'hopper_already_up': 0,
               'responses_during_feed': 0,
               'responses': 0,
               'last_trial_time': [],
               }

    # start experiment
    do_experiment = True
    while do_experiment:
        
        try:
            # first, check if we should be running trials, otherwise lightsout
            if not utils.check_time(options['light_schedule']):
                raise GoodNite()

            # make sure lights are on at the beginning of each trial, prep for trial
            box.lights_on()
            
            trial['class'] = random.choice(options['models'].keys())
            trial_stim = get_stimulus(trial['class'],options)
            log.debug("trial class is %s" % trial['class'])
            
            # wait for bird to peck
            no_peck = True
            box.write(box.id_LEDcenter,True)
            while no_peck:
                no_peck = not box.read(box.id_IRcenter)

                if not utils.check_time(options['light_schedule']):
                    raise GoodNite()

            trial['trial_start'] = dt.datetime.now()
            summary['trials'] += 1
            summary['last_trial_time'] = trial['trial_start'].ctime()
            # TODO: note trial initiation in event file

            # play temp stimulus
            trial['stim_start'] = dt.datetime.now()
            wave_proc = box.play_wav(trial_stim['filename'])

            check_hold = (options['hold_time'] > 0.0)
            while check_hold:
                elapsed_time = dt.datetime.now() - trial['stim_start']
                if elapsed_time < dt.timedelta(seconds=options['hold_time']):

            box.write(box.id_LEDcenter,False)
            # TODO: note wave played in event file

            # wait for response
            wait_min = trial_stim['epochs'][options['strlen_min']-1][-1]
            hwio.wait(wait_min)

            # check for responses
            wait_max = trial_stim['epochs'][-1][-1] + options['response_win']
            check_peck = True
            box.write(box.id_LEDleft,True)
            box.write(box.id_LEDright,True)
            while check_peck:
                elapsed_time = dt.datetime.now() - trial['stim_start']
                if elapsed_time > dt.timedelta(seconds=wait_max):
                    trial['response'] = 'none'
                    check_peck = False
                elif box.read(box.id_IRleft):
                    trial['response_time'] = dt.datetime.now()
                    wave_proc.terminate()
                    trial['response'] = 'L'
                    check_peck = False
                    summary['responses'] += 1
                elif box.read(box.id_IRright):
                    trial['response_time'] = dt.datetime.now()
                    wave_proc.terminate()
                    trial['response'] = 'R'
                    check_peck = False 
                    summary['responses'] += 1
            # TODO: note response in event file
            box.write(box.id_LEDleft,False)
            box.write(box.id_LEDright,False)
            trial['response_timedelta'] = elapsed_time

            # determine the number of motifs the bird heard
            num_mots = 0
            for epoch in trial_stim['epochs']:
                if elapsed_time > dt.timedelta(seconds=epoch[0]):
                    num_mots += 1
            # determine the string of motifs the bird heard
            trial['stim_string'] = '\"%s\"' % ';'.join(trial_stim['string'][0:num_mots])
            trial['stim_epochs'] = trial_stim['epochs'][0:num_mots]

            trial['feed'] = False
            trial['timeout'] = False

            # decide how to respond to the subject
            if trial['response'] == trial['class']: 
                trial['cum_correct'] += 1
                if options['secondary_reinf']:
                    trial['flash_epoch'] = box.flash(dur=1.0)
                if trial['cum_correct'] >= trial['cum_correct_thresh']: 
                    trial['feed_epoch'] = box.feed(options['feed_dur'])

                    trial['cum_correct'] = 0
                    trial['cum_correct_thresh'] = random.randint(1, 2*options['variable_ratio']-1)
            elif (not options['punish_non_resp']) and (trial['response'] == 'none'):
                trial['cum_correct'] = 0
            else:
                trial['timeout_epoch'] = box.timeout(options['timeout_dur'])
                trial['cum_correct'] = 0

            if trial['feed_epoch']:
                trial['feed'] = True
                summary['feeds'] += 1
            if trial['timeout_epoch']:
                trial['timeout'] = True

            # write trial results to CSV
            with open(options['data_csv'],'ab') as data_fh:
                trialWriter = csv.DictWriter(data_fh,fieldnames=options['fields_to_save'],extrasaction='ignore')
                trialWriter.writerow(trial)

        except GoodNite:
            poll_int = 60.0
            box.lights_off()
            summary = {'trials': 0,
                       'feeds': 0,
                       'hopper_failures': 0,
                       'hopper_wont_go_down': 0,
                       'hopper_already_up': 0,
                       'responses_during_feed': 0,
                       'responses': 0,
                       'last_trial_time': [],
                       }
            log.debug('waiting 60 seconds before checking light schedule...' % (poll_int))
            hwio.wait(poll_int)

        except ComediError as err:
            log.critical(err + ", terminating operant control script")
            do_experiment = False

        except OperantError as err:
            log.error(err)

        except RespondDuringFeedError as err:
            summary['responses_during_feed'] += 1
            log.error(err)

        except HopperAlreadyUpError as err:
            log.warning("hopper already up on box %i" & err)
            box.reset()
            box.lights_on()

        except HopperAlreadyUpError as err:
            log.error("hopper didn't come up on box %i" & err)

        except HopperAlreadyUpError as err:
            log.warning("hopper didn't go down on box %i" & err)
            box.reset()
            box.lights_on()
                
        except Exception as err:
            log.exception()

        finally:
            utils.write_summaryDAT(summary,options['summaryDAT'])



