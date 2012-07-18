#!/usr/bin/python

## TODO:
# Save rDAT and trial info
# Implement Error Handling
# Add support for correction trials
# Add support for probe trials

import os, sys, random, csv, logging, logging.handlers, json
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
        motif_name = options['stim_map'][str(motif_id)]
        isi = random.gauss(options['isi_mean'], options['isi_stdev'])
        if isi < 0.0: isi = 0.0
        input_file_list.append((options['stims'][motif_name], isi))
        stim['string'].append(motif_name)
    input_file_list[-1] = (input_file_list[-1][0], 0.0)
    stim['input_file_list'] = input_file_list

    (stim['filename'], stim['epochs']) = utils.concat_wav(stim['input_file_list'], os.path.join(options['stim_path'], 'temp_concat.wav'))

    stim['dur'] = stim['epochs'][-1][-1]
  
    return stim


def get_options(cmd_line):
    """ get all of the configuration options for the experiment """

    # set path variables
    CODE_PATH = os.path.dirname(os.path.realpath(__file__))
    USER_PATH = os.path.expanduser('~')
    BIRD_PATH = os.path.join(USER_PATH,'opdat', 'B' + cmd_line['subj'])
    STIM_PATH = os.path.join(BIRD_PATH,'stims')

    with open(os.path.join(BIRD_PATH, cmd_line['config_file'])) as config_f:
        options = json.load(config_f)
    options['box_id'] = cmd_line['box']
    options['subject_id'] = cmd_line['subj']
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
    timestamp = dt.datetime.now().strftime(filetime_fmt)

    options['log_file'] = os.path.join(options['bird_path'], options['subject_id'] + '.log')
    options['data_csv'] = os.path.join(options['bird_path'], options['subject_id'] + '_' + options['script_fname'] + '_trials_' + timestamp + '.csv')
    options['config_snapshot'] = os.path.join(options['bird_path'], options['subject_id'] + '_' + options['script_fname'] + '_config_' + timestamp + '.json')
    options['summaryDAT'] = os.path.join(options['bird_path'], options['subject_id'] + '.summaryDAT')
    options['fields_to_save'] = ['trial_start','class','stim_start','stim_string','response','feed','timeout','cum_correct','cum_correct_thresh']
    
    # oreo
    with open(options['data_csv'], 'wb') as data_fh:
        trialWriter = csv.writer(data_fh)
        trialWriter.writerow(options['fields_to_save'])
    with open(options['config_snapshot'], 'wb') as config_snap:
        json.dump(options, config_snap, sort_keys=True, indent=4)

    return options

def run_trial(trial, options):
    pass

def save_trial(trial, options):
    # write trial results to CSV
    with open(options['data_csv'],'ab') as data_fh:
        trialWriter = csv.DictWriter(data_fh,fieldnames=options['fields_to_save'],extrasaction='ignore')
        trialWriter.writerow(trial)

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
    #email_handler = logging.handlers.SMTPHandler(mailhost='localhost',
    #                                             fromaddr='bird@vogel.ucsd.edu',
    #                                             toaddrs=[options['experimenter']['email'],],
    #                                             subject='error notice',
    #                                             )
    #email_handler.setlevel(logging.ERROR)
    #log.addHandler(email_handler)

    # initialize box
    box = hwio.OperantBox(options['box_id'])
    log.debug('box %i initialized' % options['box_id'])
    box.reset()
    
    trial = dict()
    trial['correct'] = False
    trial['cum_correct'] = 0
    trial['cum_correct_thresh'] = 1

    summary = utils.init_summary()

    # start experiment
    do_experiment = True
    while do_experiment:
        
        try:
            # first, check if we should be running trials, otherwise lightsout
            if not utils.check_time(options['light_schedule']):
                raise GoodNite()

            # make sure lights are on at the beginning of each trial, prep for trial
            box.lights_on()
            log.info('lights on')

            if trial['correct'] and options['correction_trials']:
                log.debug("correction trial: class is %s" % trial['class'])
            else:
                trial['class'] = random.choice(options['models'].keys())
                trial_stim = get_stimulus(trial['class'],options)
                log.debug("trial class is %s" % trial['class'])
            
            # wait for bird to peck
            no_peck = True
            box.write(box.dio['LED_center'],True)
            log.debug('waiting for peck...')
            while no_peck:
                no_peck = not box.read(box.dio['IR_center'])

                if not utils.check_time(options['light_schedule']):
                    raise GoodNite()

            trial['trial_start'] = dt.datetime.now()
            log.info("trial started at %s" % trial['trial_start'].ctime())
            summary['trials'] += 1
            summary['last_trial_time'] = trial['trial_start'].ctime()

            # play temp stimulus
            trial['stim_start'] = dt.datetime.now()
            wave_proc = box.play_wav(trial_stim['filename'])

            #check_hold = (options['hold_time'] > 0.0)
            #while check_hold:
            #    elapsed_time = dt.datetime.now() - trial['stim_start']
            #    if elapsed_time < dt.timedelta(seconds=options['hold_time']):
            #        check_hold = True
            
            box.write(box.dio['LED_center'],False)
            # TODO: note wave played in event file

            # wait for response
            wait_min = trial_stim['epochs'][options['strlen_min']-1][-1]
            hwio.wait(wait_min)

            # check for responses
            wait_max = trial_stim['epochs'][-1][-1] + options['response_win']
            check_peck = True
            box.write(box.dio['LED_left'],True)
            box.write(box.dio['LED_right'],True)
            while check_peck:
                elapsed_time = dt.datetime.now() - trial['stim_start']
                if elapsed_time > dt.timedelta(seconds=wait_max):
                    trial['response'] = 'none'
                    check_peck = False
                elif box.read(box.dio['IR_left']):
                    trial['response_time'] = dt.datetime.now()
                    wave_proc.terminate()
                    trial['response'] = 'L'
                    check_peck = False
                    summary['responses'] += 1
                elif box.read(box.dio['IR_right']):
                    trial['response_time'] = dt.datetime.now()
                    wave_proc.terminate()
                    trial['response'] = 'R'
                    check_peck = False 
                    summary['responses'] += 1
            # TODO: note response in event file
            box.write(box.dio['LED_left'],False)
            box.write(box.dio['LED_right'],False)
            trial['response_timedelta'] = elapsed_time

            # determine the number of motifs the bird heard
            num_mots = 0
            for epoch in trial_stim['epochs']:
                if elapsed_time > dt.timedelta(seconds=epoch[0]):
                    num_mots += 1
            # determine the string of motifs the bird heard
            trial['stim_string'] = ';'.join(trial_stim['string'][0:num_mots])
            trial['stim_epochs'] = trial_stim['epochs'][0:num_mots]

            trial['feed'] = False
            trial['timeout'] = False

            # decide how to respond to the subject
            if trial['response'] == trial['class']:
                trial['correct'] == True
                trial['cum_correct'] += 1 
                
                if options['secondary_reinf']:
                    trial['flash_epoch'] = box.flash(dur=1.0)

                if trial['cum_correct'] >= trial['cum_correct_thresh']: 
                    # then feed, but catch errors
                    summary['feeds'] += 1
                    trial['feed'] = True

                    try:
                        trial['feed_epoch'] = box.feed(options['feed_dur'][trial['class']])
                    
                    # catch the feed errors
                    except hwio.ResponseDuringFeedError as err:
                        trial['feed'] = 'Error'
                        summary['responses_during_feed'] += 1
                        log.error("response during feed on box %s" % str(err))
                        hwio.wait(options['feed_dur'][trial['class']])
                        box.reset()
                        box.lights_on()

                    except hwio.HopperAlreadyUpError as err:
                        trial['feed'] = 'Error'
                        log.warning("hopper already up on box %s" % str(err))
                        summary['hopper_already_up'] += 1
                        hwio.wait(options['feed_dur'][trial['class']])
                        box.reset()
                        box.lights_on()

                    except hwio.HopperDidntRaiseError as err:
                        trial['feed'] = 'Error'
                        log.error("hopper didn't come up on box %s" % str(err))
                        summary['hopper_failures'] += 1
                        hwio.wait(options['feed_dur'][trial['class']])
                        box.reset()
                        box.lights_on()

                    except hwio.HopperDidntDropError as err:
                        trial['feed'] = 'Error'
                        log.warning("hopper didn't go down on box %s" % str(err))
                        summary['hopper_wont_go_down'] += 1
                        box.reset()
                        box.lights_on()
                    
                    finally:
                        
                        trial['cum_correct_thresh'] = random.randint(1, 2*options['variable_ratio']-1)
                else:

            else:
                trial['timeout_epoch'] = box.timeout(options['timeout_dur'][trial['class']])
                trial['timeout'] = True
                trial['cum_correct'] = 0

            trial['trial_end'] = dt.datetime.now()
            save_trial(trial, options)

            if trial['feed']:
                trial['cum_correct'] = 0

        except GoodNite:
            """ reset experimental parameters for the next day """
            poll_int = 60.0
            box.lights_off()
            summary = utils.init_summary()
            log.debug('waiting %f seconds before checking light schedule...' % (poll_int))
            hwio.wait(poll_int)

        except hwio.ComediError as err:
            log.critical(str(err) + ", terminating operant control script")
            do_experiment = False

        except hwio.OperantError as err:
            log.error(str(err))

        finally:
            utils.write_summary(summary,options['summaryDAT'])



