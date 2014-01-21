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

class Flow(object):
    """docstring for Flow"""
    def __init__(self, *args, **kwargs):
        super(Flow, self).__init__()
        self.state = 'init'
        self.flow_map = {'init': self.init,
                          'main': self.main,
                          'post': self.post,
                          }

    def init(self):
        return 'main'

    def main(self):
        return 'post'

    def post(self):
        return None

    def run(self):
        while self.state is not None:
            self.state = self.flow_map[self.state]()
        

class ReinforcementSchedule(object):
    """docstring for ReinforcementSchedule"""
    def __init__(self):
        super(ReinforcementSchedule, self).__init__()

    def consequate(self,correct):
        if correct:
            return True
        else:
            return False

class FixedRatioSchedule(ReinforcementSchedule):
    """docstring for FixedSchedule"""
    def __init__(self, ratio=1):
        super(FixedSchedule, self).__init__()
        self.ratio = ratio
        self.cum_correct = 0
        self.update()

    def update(self):
        self.min_correct = ratio

    def consequate(self,correct):
        if correct:
            self.cum_correct += 1
            if self.cum_correct >= self.min_correct:
                self.update()
                return True
            else:
                return False
        else:
            self.cum_correct = 0
            return False

class VariableRatioSchedule(FixedRatioSchedule):
    """docstring for VariableRatioSchedule"""
    def __init__(self, ratio=1):
        super(VariableRatioSchedule, self).__init__(ratio=ratio)

    def update(self):
        ''' update min correct by randomly sampling from interval [1:2*ratio-1)'''
        self.min_correct = random.randint(1, 2*exp.variable_ratio-1)


class Trial(utils.Event):
    """docstring for Trial"""
    def __init__(self,
                 state='queued',
                 correct=False,
                 trial_type='normal', 
                 *args, **kwargs):
        super(Trial, self).__init__(*args, **kwargs)
        self.state = state
        self.correct = correct
        self.trial_type = trial_type
        self.events = []
        self.stimulus = None
        self.response = None
        self.reward = None
        self.punish = None
    

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

        self.reinf_sched = VariableRatioSchedule(VR=self.variable_ratio)
        self.trials = []
        self.panel = None


    def build_transition_matrices(self): 
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
            trans = trans / trans[:,-1][:,None] # I don't get why it suddenly works to append '[:,None]'
            self.transition_cdf[this_class] = trans

    def reward(self):
        self.summary['feeds'] += 1
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
                

    def secondary_reinforcement(self,value=1.0):
        return self.panel.center.flash(dur=value)

    def punish(self):
        trial['timeout_epoch'] = self.panel.punish(value=self.timeout_dur[trial['class']])
        trial['timeout'] = True
        trial['cum_correct'] = 0
        do_correction = True

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

    def trial_init(self):
        ''' this is where we initialize a trial'''
        # make sure lights are on at the beginning of each trial, prep for trial
        self.panel.house_light.set_by_schedule()

        self.new_trial()

        self.this_trial = self.trials[-1]

        trial.min_epoch = trial_motifs[self.strlen_min-1]
        trial.min_wait = min_epoch.time + min_epoch.duration

        trial.max_wait = trial_stim.time + trial_stim.duration + self.response_win

    def trial_run(self,trial):

        self.stimulus_init()
        self.stimulus_run()
        self.stimulus_end()

        self.response_init()
        self.response_run()
        self.response_end()

        self.consequence_init()
        self.consequence_run()
        self.consequence_end()

    def stimulus_init(self):
        # wait for bird to peck
        self.log.debug('waiting for peck...')
        self.panel.center.on()
        trial['trial_start'] = panel.center.wait_for_peck()
        self.panel.center.off()

        # record trial initiation
        self.summary['trials'] += 1
        self.summary['last_trial_time'] = trial['trial_start'].ctime()
        self.log.info("trial started at %s" % trial['trial_start'].ctime())

    def stimulus_run(self):
        ## 1. play stimulus
        stim_start = dt.datetime.now()
        trial['stim_start'] = (stim_start- trial['trial_start']).total_seconds()
        self.wave_stream = panel.speaker.play_wav(trial_stim.file_origin)
        utils.wait(min_wait)

    def stimulus_post(self):
        pass

    def response_init(self):
        self.panel.left.on()
        self.panel.right.on()

    def response_run(self):
        while True:
            elapsed_time = (dt.datetime.now() - stim_start).total_seconds()
            if elapsed_time > max_wait:
                trial['response'] = 'none'
                break
            elif panel.left.status():
                trial['response_time'] = trial['stim_start'] + elapsed_time
                wave_stream.close()
                trial['response'] = 'L'
                self.summary['responses'] += 1
                break
            elif panel.right.status():
                trial['response_time'] = trial['stim_start'] + elapsed_time
                wave_stream.close()
                trial['response'] = 'R'
                self.summary['responses'] += 1
                break
    def response_post(self):
        self.panel.left.off()
        self.panel.right.off()

    def consequence_init(self):
        pass

    def consequence_run(self):
        # correct trial
        if trial['response'] is trial['class']:
            
            if self.secondary_reinf:
                trial['flash_epoch'] = self.secondary_reinforcement()

            self.do_correction = False # we don't want the next trial to be a correction trial

            if trial['type'] == 'correction':
                pass

            elif self.reinf_sched.consequate(correct=True):
                trial['feed'] = True
                self.reward()
        # no response
        elif trial['response'] is 'none':
            pass

        # incorrect trial
        else:
            self.reinf_sched.cum_correct = 0
            self.punish()

    def consequence_post(self):
        trial['trial_duration'] = (dt.datetime.now() - trial['trial_start']).total_seconds()
        

    def analyze_trial(self,trial):
        '''after the trial is complete, perform additional analyses that will be saved'''
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
            trial['stim_string'] += next((name for name, wav in self.stims.iteritems() if wav == motif.name), '')


    def save_trial(self,trial_dict):
        '''write trial results to CSV'''
        with open(self.data_csv,'ab') as data_fh:
            trialWriter = csv.DictWriter(data_fh,fieldnames=self.fields_to_save,extrasaction='ignore')
            trialWriter.writerow(trial_dict)

    def trial_post(self):
        '''things to do at the end of a trial'''

        self.analyze_trial()
        self.save_trial(trial)
        self.write_summary()
        utils.wait(self.intertrial_min)

    def sleep_init(self):
        self.sleep_poll_interval = 60.0

    def sleep_run(self):
        """ reset expal parameters for the next day """
        poll_int = self.sleep_poll_interval
        panel.lights_off()
        self.log.debug('waiting %f seconds before checking light schedule...' % (poll_int))
        utils.wait(poll_int)

    def sleep_post(self):
        self.init_summary()

    def run(self):

        self.do_correction = False

        # start exp
        while True:

            # trial loop
            try:
                self.trial_init()
                self.trial_run()
            except components.GoodNite:
                self.sleep_init()
                self.sleep_run()
                self.sleep_post()

            except hwio.ComediError as err:
                self.log.critical(str(err))

            except hwio.AudioError as err:
                self.log.error(str(err))

            finally:
                self.trial_post()


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



