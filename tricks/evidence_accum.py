#!/usr/bin/python

## TODO:
# Save rDAT and trial info
# Implement Error Handling
# Add support for correction trials
# Add support for probe trials

import os, sys, random, csv, logging, logging.handlers, json, time
import numpy as np
import datetime as dt
from pyoperant import utils
from pyoperant.components import GoodNite

class GNGSeqExperiment(utils.Experiment):
    """docstring for Experiment"""
    def __init__(self, *args, **kwargs):
        super(Experiment, self, *args, **kwargs).__init__()
        self.options = self.get_options()
        self.log_config()
        self.init_summary()

    def get_stimulus(self,trial_class):
        """ take trial class and return a tuple containing the wav filename & additional info to play 

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
        cum_matrix = np.cumsum(self.options['models'][trial_class], axis=1)
        for item in range(self.options['strlen_max']):
            motif_id = (cum_matrix[motif_id] < random.random()).sum()
            motif_name = self.options['stim_map'][str(motif_id)]
            isi = random.gauss(self.options['isi_mean'], options['isi_stdev'])
            if isi < 0.0: isi = 0.0
            input_file_list.append((self.options['stims'][motif_name], isi))
            stim['string'].append(motif_name)
        input_file_list[-1] = (input_file_list[-1][0], 0.0)
        stim['input_file_list'] = input_file_list

        (stim['filename'], stim['epochs']) = utils.concat_wav(stim['input_file_list'], os.path.join(self.options['stim_path'], 'temp_concat.wav'))

        stim['dur'] = stim['epochs'][-1][-1]
      
        return stim

    def save_trial(self,trial_dict):
        # write trial results to CSV
        with open(self.options['data_csv'],'ab') as data_fh:
            trialWriter = csv.DictWriter(data_fh,fieldnames=self.options['fields_to_save'],extrasaction='ignore')
            trialWriter.writerow(trial_dict)

    def get_options(self):
        """ get all of the configuration options for the experiment """

        cmd_line = utils.parse_commandline())

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

        # define log files, rDAT files
        filetime_fmt = '%Y%m%d%H%M%S'
        timestamp = dt.datetime.now().strftime(filetime_fmt)

        options['log_file'] = os.path.join(options['bird_path'], options['subject_id'] + '.log')
        options['data_csv'] = os.path.join(options['bird_path'], options['subject_id'] + '_' + options['script_fname'] + '_trials_' + timestamp + '.csv')
        options['config_snapshot'] = os.path.join(options['bird_path'], options['subject_id'] + '_' + options['script_fname'] + '_config_' + timestamp + '.json')
        options['summaryDAT'] = os.path.join(options['bird_path'], options['subject_id'] + '.summaryDAT')
        options['fields_to_save'] = ['number','type','trial_start','class','stim_start','stim_string','response','feed','timeout','cum_correct','cum_correct_thresh']
        
        # oreo
        with open(options['data_csv'], 'wb') as data_fh:
            trialWriter = csv.writer(data_fh)
            trialWriter.writerow(options['fields_to_save'])
        with open(options['config_snapshot'], 'wb') as config_snap:
            json.dump(options, config_snap, sort_keys=True, indent=4)

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

        return options

def run_trial(trial, options):
    pass

if __name__ is "__main__":


    experiment = GNGSeqExperiment()

    # initialize box
    box = hwio.OperantBox(options['box_id'])
    box.house_light.schedule = experiment.options['light_schedule']
    box.reset()
    
    experiment.log.debug('box %i initialized' % experiment.options['box_id'])
    
    trial = dict()
    trial['correct'] = False
    trial['cum_correct'] = 0
    trial['cum_correct_thresh'] = 1
    trial['number'] = 0

    do_correction = False

    # start experiment
    do_experiment = True
    while do_experiment:
        
        try:
            # make sure lights are on at the beginning of each trial, prep for trial
            box.house_light.set_by_schedule()

            trial['feed'] = False
            trial['timeout'] = False
            trial['number'] += 1

            if do_correction and options['correction_trials']:
                trial['type'] = 'correction'
                experiment.log.debug("correction trial: class is %s" % trial['class'])
            else:
                trial['type'] = 'normal'
                trial['class'] = random.choice(options['models'].keys())
                trial_stim = experiment.get_stimulus(trial['class'])
                experiment.log.debug("trial class is %s" % trial['class'])
            
            # wait for bird to peck
            experiment.log.debug('waiting for peck...')
            trial['trial_start'] = box.center.wait_for_peck()

            # record trial initiation
            experiment.summary['trials'] += 1
            experiment.summary['last_trial_time'] = trial['trial_start'].ctime()
            experiment.log.info("trial started at %s" % trial['trial_start'].ctime())

            # play temp stimulus
            trial['stim_start'] = dt.datetime.now()
            wave_stream = box.speaker.play_wav(trial_stim['filename'])
            box.center.off()

            # wait for response
            min_wait = trial_stim['epochs'][options['strlen_min']-1][-1]
            utils.wait(min_wait)

            # check for responses
            max_wait = trial_stim['epochs'][-1][-1] + options['response_win']
            check_peck = True
            box.left.on()
            box.right.on()
            while check_peck:
                elapsed_time = dt.datetime.now() - trial['stim_start']
                if elapsed_time > dt.timedelta(seconds=max_wait):
                    trial['response'] = 'none'
                    check_peck = False
                elif box.left.get():
                    trial['response_time'] = dt.datetime.now()
                    wave_stream.close()
                    trial['response'] = 'L'
                    check_peck = False
                    experiment.summary['responses'] += 1
                elif box.right.get():
                    trial['response_time'] = dt.datetime.now()
                    wave_stream.close()
                    trial['response'] = 'R'
                    check_peck = False 
                    experiment.summary['responses'] += 1
            # TODO: note response in event file
            box.left.off()
            box.right.off()

            trial['response_timedelta'] = elapsed_time

            # calculate the number of motifs the bird heard
            num_mots = 0
            for epoch in trial_stim['epochs']:
                if elapsed_time > dt.timedelta(seconds=epoch[0]):
                    num_mots += 1
            # determine the string of motifs the bird heard
            trial['stim_string'] = ';'.join(trial_stim['string'][0:num_mots])
            trial['stim_epochs'] = trial_stim['epochs'][0:num_mots]


            # decide how to respond to the subject for normal trials
            if trial['type'] is 'normal':
                if trial['response'] is trial['class']:
                    # correct response
                    do_correction = False

                    if trial['type'] is not 'correction':
                        trial['cum_correct'] += 1 
                    
                    if options['secondary_reinf']:
                        # give secondary reinforcer
                        trial['flash_epoch'] = box.center.flash(dur=0.5)

                    if (trial['cum_correct'] >= trial['cum_correct_thresh']): 
                        # if cum currect reaches feed threshold, then feed
                        experiment.summary['feeds'] += 1
                        trial['feed'] = True

                        try:
                            trial['feed_epoch'] = box.reward(value=experiment.options['feed_dur'][trial['class']])
                        
                        # but catch the feed errors
                        except hwio.ResponseDuringFeedError as err:
                            trial['feed'] = 'Error'
                            experiment.summary['responses_during_feed'] += 1
                            experiment.log.error("response during feed on box %s" % str(err))
                            utils.wait(options['feed_dur'][trial['class']])
                            box.reset()

                        except hwio.HopperAlreadyUpError as err:
                            trial['feed'] = 'Error'
                            experiment.summary['hopper_already_up'] += 1
                            experiment.log.warning("hopper already up on box %s" % str(err))
                            utils.wait(options['feed_dur'][trial['class']])
                            box.reset()

                        except hwio.HopperDidntRaiseError as err:
                            trial['feed'] = 'Error'
                            experiment.summary['hopper_failures'] += 1
                            experiment.log.error("hopper didn't come up on box %s" % str(err))
                            utils.wait(options['feed_dur'][trial['class']])
                            box.reset()

                        except hwio.HopperDidntDropError as err:
                            trial['feed'] = 'Error'
                            experiment.summary['hopper_wont_go_down'] += 1
                            experiment.log.warning("hopper didn't go down on box %s" % str(err))
                            box.reset()
                        
                        finally:
                            box.house_light.on()
                            if trial['type'] is not 'correction':
                                trial['cum_correct_thresh'] = random.randint(1, 2*experiment.options['variable_ratio']-1)
                
                elif trial['response'] is 'none':
                    # ignore non-responses
                    pass

                else:
                    trial['timeout_epoch'] = box.punish(value=options['timeout_dur'][trial['class']])
                    trial['timeout'] = True
                    trial['cum_correct'] = 0
                    do_correction = True

            trial['trial_end'] = dt.datetime.now()
            experiment.save_trial(trial, options)

            if trial['feed']:
                trial['cum_correct'] = 0

        except GoodNite:
            """ reset experimental parameters for the next day """
            poll_int = 60.0
            box.lights_off()
            experiment.summary = utils.init_summary()
            experiment.log.debug('waiting %f seconds before checking light schedule...' % (poll_int))
            utils.wait(poll_int)

        except hwio.ComediError as err:
            experiment.log.critical(str(err) + ", terminating operant control script")
            do_experiment = False

        except hwio.AudioError as err:
            experiment.log.error(str(err))

        finally:
            experiment.write_summary()



