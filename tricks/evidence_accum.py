#!/usr/bin/python

import os, sys, random, csv, time
import numpy as np
import datetime as dt
from pyoperant import utils, components, local, hwio

try:
    import simplejson as json
except ImportError:
    import json

def get_options(cmd_line):
    """ get all of the configuration options for the experiment """

    options = {}
    # set path variables
    options['code_path'] = os.path.dirname(os.path.realpath(__file__))
    options['user_path'] = os.path.expanduser('~')
    options['bird_path'] = os.path.join(options['user_path'],'opdat', 'B' + cmd_line['subj'])
    options['stim_path'] = os.path.join(options['bird_path'],'Stimuli')

    with open(os.path.join(options['bird_path'], cmd_line['config_file'])) as config_f:
        options.update(json.load(config_f))

    options['box_id'] = cmd_line['box']
    options['subject_id'] = cmd_line['subj']

    options['script_fname'] = os.path.basename(__file__)

    return options

class EvidenceAccumExperiment(utils.Experiment):
    """docstring for Experiment"""
    def __init__(self, *args, **kwargs):
        super(EvidenceAccumExperiment, self).__init__(*args, **kwargs)

        # assign stim files full names
        for name, filename in self.stims.items():
            filename_full = os.path.join(self.stim_path, filename)
            self.stims[name] = filename_full

        # configure logging
        self.log_file = os.path.join(self.bird_path, self.subject_id + '.log')
        self.log_config()

        # configure csv file for data
        self.data_csv = os.path.join(self.bird_path, self.subject_id + '_' + self.script_fname + '_trials_' + self.exp_timestamp + '.csv')
        self.fields_to_save = ['index','type','trial_start','class','stim_start','stim_string','response','response_time','feed','timeout','cum_correct','cum_correct_thresh']
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
        n = len(self.stim_map)
        self.evidence_arrays = {}
        for stim_class, pair_set in self.models.items():
            arr = np.zeros((n,n),np.float_)
            for a,b in pair_set:
                arr[a,b] = 1.0

            self.evidence_arrays[stim_class] = arr

        self.stim_classes = self.models.keys()
        assert len(self.stim_classes) == 2
        self.transition_cdf = {}
        for this_class in self.stim_classes:
            other_class = [cl for cl in self.stim_classes if cl is not this_class][0]
            trans = self.odds * self.evidence_arrays[stim_class] + self.evidence_arrays[other_class]
            trans[0,1:] = 1.0
            trans = np.cumsum(trans,axis=1)
            trans = trans / trans[:,-1][:,None] # I don't get why this works
            self.transition_cdf[this_class] = trans

        self.trials = []
        self.panel = None

    def reward(self):
        try:
            trial['feed_epoch'] = self.panel.reward(value=self.feed_dur[trial['class']])

        # but catch the feed errors
        # except components.ResponseDuringFeedError as err:
        #     trial['feed'] = 'Error'
        #     exp.summary['responses_during_feed'] += 1
        #     exp.log.error("response during feed on panel %s" % str(err))
        #     utils.wait(exp.feed_dur[trial['class']])
        #     panel.reset()

        except components.HopperActiveError as err:
            trial['feed'] = 'Error'
            self.summary['hopper_already_up'] += 1
            self.log.warning("hopper already up on panel %s" % str(err))
            utils.wait(exp.feed_dur[trial['class']])
            self.panel.reset()

        except components.HopperInactiveError as err:
            trial['feed'] = 'Error'
            self.summary['hopper_failures'] += 1
            self.log.error("hopper didn't come up on panel %s" % str(err))
            utils.wait(exp.feed_dur[trial['class']])
            self.panel.reset()

        # except components.HopperDidntDropError as err:
        #     trial['feed'] = 'Error'
        #     exp.summary['hopper_wont_go_down'] += 1
        #     exp.log.warning("hopper didn't go down on panel %s" % str(err))
        #     panel.reset()

        finally:
            self.panel.house_light.on()
            if trial['type'] is not 'correction':
                trial['cum_correct_thresh'] = random.randint(1, 2*exp.variable_ratio-1)

    def punish(self):
        trial['timeout_epoch'] = self.panel.punish(value=self.timeout_dur[trial['class']])
        trial['timeout'] = True
        trial['cum_correct'] = 0
        do_correction = True

    def present_stimulus(self):
        pass

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

        motifs = [self.stim_map[mid] for mid in motif_ids]

        motif_isi = [max(random.gauss(self.isi_mean, self.isi_stdev),0.0) for mot in motifs]
        motif_isi[-1] = 0.0

        input_files = [(self.stims[motif_name], isi) for motif_name, isi in zip(motifs,motif_isi)]
        filename =  os.path.join(self.stim_path, ''.join(motifs) + '.wav')
        stim, epochs = utils.concat_wav(input_files,filename)

        return stim, epochs

    def save_trial(self,trial_dict):
        '''write trial results to CSV'''
        with open(self.data_csv,'ab') as data_fh:
            trialWriter = csv.DictWriter(data_fh,fieldnames=self.fields_to_save,extrasaction='ignore')
            trialWriter.writerow(trial_dict)

    def new_trial(self):
        '''create a new trial and append it to the trial list'''
        trial = {}
        try:
            if self.correction_trials:
                if self.trials[-1]['response'] and self.trials[-1]['correct']:
                    trial['type'] = 'correction'
                    trial['class'] = self.trials[-1]['class']
                    exp.log.debug("correction trial: class is %s" % trial['class'])
                else:
                    trial['type'] = 'normal'
                    trial['class'] = random.choice(exp.models.keys())
                    trial_stim, trial_motifs = exp.get_stimuli(trial['class'])

            trial['index'] = self.trials[-1]['index'] + 1

        except IndexError:
            trial['index'] = 0

        self.trials.append(trial)

        self.log.debug("trial %i: %s, %s" % (trial['index'],trial['type'],trial['class']))

        return True

    def run(self):

        self.do_correction = False

        # start exp
        while True:
            try:
                # make sure lights are on at the beginning of each trial, prep for trial
                self.panel.house_light.set_by_schedule()

                
                trial['index'] += 1

                self.new_trial()

                min_epoch = trial_motifs[exp.strlen_min-1]
                min_wait = min_epoch.time + min_epoch.duration

                max_wait = trial_stim.time + trial_stim.duration + exp.response_win

                # wait for bird to peck
                utils.wait(exp.intertrial_min)
                self.log.debug('waiting for peck...')
                self.panel.center.on()
                trial['trial_start'] = panel.center.wait_for_peck()
                self.panel.center.off()

                # record trial initiation
                self.summary['trials'] += 1
                self.summary['last_trial_time'] = trial['trial_start'].ctime()
                self.log.info("trial started at %s" % trial['trial_start'].ctime())

                # play stimulus
                stim_start = dt.datetime.now()
                trial['stim_start'] = (stim_start- trial['trial_start']).total_seconds()
                wave_stream = panel.speaker.play_wav(trial_stim.file_origin)
                utils.wait(min_wait)

                # check for responses
                check_peck = True
                self.panel.left.on()
                self.panel.right.on()
                while check_peck:
                    elapsed_time = (dt.datetime.now() - stim_start).total_seconds()
                    if elapsed_time > max_wait:
                        trial['response'] = 'none'
                        check_peck = False
                    elif panel.left.status():
                        trial['response_time'] = trial['stim_start'] + elapsed_time
                        wave_stream.close()
                        trial['response'] = 'L'
                        check_peck = False
                        exp.summary['responses'] += 1
                    elif panel.right.status():
                        trial['response_time'] = trial['stim_start'] + elapsed_time
                        wave_stream.close()
                        trial['response'] = 'R'
                        check_peck = False
                        exp.summary['responses'] += 1
                # TODO: note response in event file
                self.panel.left.off()
                self.panel.right.off()


                trial_stim.time = trial_stim.time + trial['stim_start']
                for motif in trial_motifs:
                    motif.time = motif.time + trial['stim_start']

                # calculate the number of motifs the bird heard
                if trial['response'] == 'none':
                    num_mots = len(trial_motifs)
                else:
                    num_mots = 0
                    for motif in trial_motifs:
                        if trial['response_time'] > motif.time:
                            num_mots += 1
                # determine the string of motifs the bird heard

                trial['stim_motifs'] = trial_motifs[:num_mots]

                trial['stim_string'] = ''
                for motif in trial['stim_motifs']:
                    trial['stim_string'] += next((name for name, wav in exp.stims.iteritems() if wav == motif.name), '')

                # decide how to respond to the subject for normal trials
                if trial['type'] is 'normal':
                    if trial['response'] is trial['class']:
                        # correct response
                        self.do_correction = False

                        if trial['type'] is not 'correction':
                            trial['cum_correct'] += 1

                        if exp.secondary_reinf:
                            # give secondary reinforcer
                            trial['flash_epoch'] = panel.center.flash(dur=0.5)

                        if (trial['cum_correct'] >= trial['cum_correct_thresh']):
                            # if cum currect reaches feed threshold, then feed
                            exp.summary['feeds'] += 1
                            trial['feed'] = True

                            self.reward()

                    elif trial['response'] is 'none':
                        # ignore non-responses
                        pass

                    else:
                        self.punish()

                trial['trial_duration'] = (dt.datetime.now() - trial['trial_start']).total_seconds()
                exp.save_trial(trial)

                if trial['feed']:
                    trial['cum_correct'] = 0

            except components.GoodNite:
                """ reset expal parameters for the next day """
                poll_int = 60.0
                panel.lights_off()
                exp.init_summary()
                exp.log.debug('waiting %f seconds before checking light schedule...' % (poll_int))
                utils.wait(poll_int)

            except hwio.ComediError as err:
                exp.log.critical(str(err) + ", terminating operant control script")
                do_exp = False

<<<<<<< Updated upstream
        except components.GoodNite:
            """ reset experimental parameters for the next day """
            poll_int = 60.0
            box.house_light.off()
            experiment.init_summary()
            experiment.log.debug('waiting %f seconds before checking light schedule...' % (poll_int))
            utils.wait(poll_int)
=======
            except hwio.AudioError as err:
                exp.log.error(str(err))
>>>>>>> Stashed changes

            finally:
                exp.write_summary()


# def run_trial(trial, options):
#     pass

# class VRTrial(utils.Event):
#     """docstring for Trial"""
#     def __init__(self, correct=False,cum_correct=0,cum_correct_thresh=1, *args, **kwargs):
#         super(Trial, self, *args, **kwargs).__init__()


def main(options):

    exp = EvidenceAccumExperiment(**options)

    # initialize box
    if exp.box_id == 1:
        exp.panel = local.Vogel1()
    elif exp.box_id == 2:
        exp.panel = local.Vogel2()
    if exp.box_id == 3:
        exp.panel = local.Vogel3()
    elif exp.box_id == 4:
        exp.panel = local.Vogel4()
    if exp.box_id == 7:
        exp.panel = local.Vogel7()
    elif exp.box_id == 8:
        exp.panel = local.Vogel8()

    panel.house_light.schedule = exp.light_schedule
    exp.panel.reset()

    exp.log.debug('panel %i initialized' % exp.box_id)

    exp.run()

if __name__ == "__main__":

    cmd_line = utils.parse_commandline()
    options = get_options(cmd_line)

    main(options)



