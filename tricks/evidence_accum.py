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

def get_options(cmd_line):
    """ get all of the configuration options for the experiment """

    # set path variables
    options['code_path'] = os.path.dirname(os.path.realpath(__file__))
    options['user_path'] = os.path.expanduser('~')
    options['bird_path'] = os.path.join(USER_PATH,'opdat', 'B' + cmd_line['subj'])
    options['stim_path'] = os.path.join(options['bird_path'],'stims')

    with open(os.path.join(options['bird_path'], cmd_line['config_file'])) as config_f:
        options = json.load(config_f)

    options['box_id'] = cmd_line['box']
    options['subject_id'] = cmd_line['subj']

    options['script_fname'] = os.path.basename(__file__)

    return options

class EvidenceAccumExperiment(utils.Experiment):
    """docstring for Experiment"""
    def __init__(self, *args, **kwargs):
        super(Experiment, self, *args, **kwargs).__init__()

        for key, value in kwargs.items():
            setattr(self, key, value)

        # assign stim files full names
        for name, filename in self.stims.items():
            filename_full = os.path.join(self.stim_path, filename)
            self.stims[name] = filename_full

        # define log files, rDAT files
        self.filetime_fmt = '%Y%m%d%H%M%S'
        self.exp_timestamp = dt.datetime.now().strftime(self.filetime_fmt)

        # configure logging
        self.log_file = os.path.join(self.bird_path, self.subject_id + '.log')
        self.log_config()

        # configure csv file for data
        self.data_csv = os.path.join(self.bird_path, self.subject_id + '_' + self.script_fname + '_trials_' + self.exp_timestamp + '.csv')
        self.fields_to_save = ['number','type','trial_start','class','stim_start','stim_string','response','feed','timeout','cum_correct','cum_correct_thresh']
        with open(self.data_csv, 'wb') as data_fh:
            trialWriter = csv.writer(data_fh)
            trialWriter.writerow(self.fields_to_save)

        # # save a snapshot of the configuration
        # # TODO: pickle this object
        # self.config_snapshot = os.path.join(self.bird_path, self.subject_id + '_' + self.script_fname + '_config_' + timestamp + '.json')
        # with open(self.config_snapshot, 'wb') as config_snap:
        #     json.dump(options, config_snap, sort_keys=True, indent=4)

        self.summaryDAT = os.path.join(self.bird_path,self.subject_id + '.summaryDAT')
        self.init_summary()
        

        # run through the transitions for each stimulus and generate transition matrixes
        n = len(self.stims)
        self.evidence_arrays = {}
        for stim_class, pair_set in self.model_evidence.items():
            arr = np.zeros((n+1,n+1),np.float_)
            for a,b in pair_set:
                arr[a,b] = 1.0

            self.evidence_arrays[stim_class] = arr

        self.stim_classes = self.model_evidence.keys()
        assert len(self.stim_classes) == 2
        self.transition_cdf = {}
        for this_class in self.stim_classes:
            other_class = [cl for cl in self.stim_classes if cl is not this_class][0]
            trans = self.odds * self.evidence_arrays[stim_class] + self.evidence_arrays[other_class]
            trans[0,1:] = 1.0
            trans = np.cumsum(trans,axis=1)
            trans = trans / trans[:,-1]
            self.transition_cdf[this_class] = trans

    def get_stimuli(self,trial_class):
        """ take trial class and return a tuple containing the wav filename & additional info to play 

        take in the trial class and the options dict
        returns a stimulus dictionary

        """
        from pyoperant.utils import AuditoryStimulus, Event

        input_files = []
        motif_ids = []

        # use transition CDF to get iteratively get next motif id
        mid = 0
        for pos in range(self.strlen_max):
            mid = (self.transition_cdf[trial_class][mid] < random.random()).sum()
            motif_ids.append(mid)

        assert len(motif_ids) == self.strlen_max

        motifs = [self.stim_map[str(mid)] for mid in motif_ids]

        motif_isi = [max(random.gauss(self.isi_mean, self.isi_stdev),0.0) for mot in motifs]
        motif_isi[-1] = 0.0

        input_files = [(self.stims[motif_name], isi) for motif_name, isi in zip(motifs,motif_isi)]
        filename =  os.path.join(self.stim_path, ''.join(motifs) + '.wav')
        stim, epochs = utils.concat_wav(input_files,filename)
      
        return stim, epochs

    def save_trial(self,trial_dict):
        # write trial results to CSV
        with open(self.data_csv,'ab') as data_fh:
            trialWriter = csv.DictWriter(data_fh,fieldnames=self.fields_to_save,extrasaction='ignore')
            trialWriter.writerow(trial_dict)


# def run_trial(trial, options):
#     pass

# class VRTrial(utils.Event):
#     """docstring for Trial"""
#     def __init__(self, correct=False,cum_correct=0,cum_correct_thresh=1, *args, **kwargs):
#         super(Trial, self, *args, **kwargs).__init__()
        

def main(options):

    experiment = EvidenceAccumExperiment(**options)

    # initialize box
    box = hwio.OperantBox(experiment.box_id)
    box.house_light.schedule = experiment.light_schedule
    box.reset()
    
    experiment.log.debug('box %i initialized' % experiment.box_id)
    
    trial = {
        'correct': False,
        'cum_correct': 0,
        'cum_correct_thresh': 1,
        'number': 0,
        }

    do_correction = False

    # start experiment
    while True:
        try:
            # make sure lights are on at the beginning of each trial, prep for trial
            box.house_light.set_by_schedule()

            trial['feed'] = False
            trial['timeout'] = False
            trial['number'] += 1

            if do_correction and experiment.correction_trials:
                trial['type'] = 'correction'
                experiment.log.debug("correction trial: class is %s" % trial['class'])
            else:
                trial['type'] = 'normal'
                trial['class'] = random.choice(experiment.models.keys())
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
            min_wait = trial_stim['epochs'][experiment.strlen_min]-1][-1]
            utils.wait(min_wait)

            # check for responses
            max_wait = trial_stim['epochs'][-1][-1] + experiment.response_win
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
                    
                    if experiment.secondary_reinf:
                        # give secondary reinforcer
                        trial['flash_epoch'] = box.center.flash(dur=0.5)

                    if (trial['cum_correct'] >= trial['cum_correct_thresh']): 
                        # if cum currect reaches feed threshold, then feed
                        experiment.summary['feeds'] += 1
                        trial['feed'] = True

                        try:
                            trial['feed_epoch'] = box.reward(value=experiment.feed_dur][trial['class']])
                        
                        # but catch the feed errors
                        except hwio.ResponseDuringFeedError as err:
                            trial['feed'] = 'Error'
                            experiment.summary['responses_during_feed'] += 1
                            experiment.log.error("response during feed on box %s" % str(err))
                            utils.wait(experiment.feed_dur[trial['class']])
                            box.reset()

                        except hwio.HopperAlreadyUpError as err:
                            trial['feed'] = 'Error'
                            experiment.summary['hopper_already_up'] += 1
                            experiment.log.warning("hopper already up on box %s" % str(err))
                            utils.wait(experiment.feed_dur[trial['class']])
                            box.reset()

                        except hwio.HopperDidntRaiseError as err:
                            trial['feed'] = 'Error'
                            experiment.summary['hopper_failures'] += 1
                            experiment.log.error("hopper didn't come up on box %s" % str(err))
                            utils.wait(experiment.feed_dur[trial['class']])
                            box.reset()

                        except hwio.HopperDidntDropError as err:
                            trial['feed'] = 'Error'
                            experiment.summary['hopper_wont_go_down'] += 1
                            experiment.log.warning("hopper didn't go down on box %s" % str(err))
                            box.reset()
                        
                        finally:
                            box.house_light.on()
                            if trial['type'] is not 'correction':
                                trial['cum_correct_thresh'] = random.randint(1, 2*experiment.variable_ratio-1)
                
                elif trial['response'] is 'none':
                    # ignore non-responses
                    pass

                else:
                    trial['timeout_epoch'] = box.punish(value=experiment.timeout_dur[trial['class']])
                    trial['timeout'] = True
                    trial['cum_correct'] = 0
                    do_correction = True

            trial['trial_end'] = dt.datetime.now()
            experiment.save_trial(trial)

            if trial['feed']:
                trial['cum_correct'] = 0

        except GoodNite:
            """ reset experimental parameters for the next day """
            poll_int = 60.0
            box.lights_off()
            experiment.init_summary()
            experiment.log.debug('waiting %f seconds before checking light schedule...' % (poll_int))
            utils.wait(poll_int)

        except hwio.ComediError as err:
            experiment.log.critical(str(err) + ", terminating operant control script")
            do_experiment = False

        except hwio.AudioError as err:
            experiment.log.error(str(err))

        finally:
            experiment.write_summary()



if __name__ is "__main__":

    options = get_options(utils.parse_commandline())

    main(options)



