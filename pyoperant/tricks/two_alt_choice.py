#!/usr/bin/python

import os
import csv
import copy
import datetime as dt
from pyoperant.tricks import base, shape
from pyoperant import components, utils, reinf, queues

class TwoAltChoiceExp(base.BaseExp):
    """docstring for Experiment"""
    def __init__(self, *args, **kwargs):
        super(TwoAltChoiceExp,  self).__init__(*args, **kwargs)
        self.shaper = shape.Shaper2AC(self.panel, self.log, self.parameters, self.log_error_callback)

        # # assign stim files full names
        for name, filename in self.parameters['stims'].items():
            filename_full = os.path.join(self.parameters['stim_path'], filename)
            self.parameters['stims'][name] = filename_full

        self.req_panel_attr += ['speaker',
                                'left',
                                'center',
                                'right',
                                'reward',
                                'punish',
                                ]

        # configure csv file for data
        self.fields_to_save = ['session',
                               'index',
                               'type_',
                               'stimulus',
                               'class_',
                               'response',
                               'correct',
                               'rt',
                               'reward',
                               'punish',
                               'time',
                               ]

        self.trials = []
        self.session_id = 0

        self.data_csv = os.path.join(self.parameters['experiment_path'],
                                     self.parameters['subject']+'_trialdata_'+self.timestamp+'.csv')
        self.make_data_csv()

        if 'reinforcement' in self.parameters.keys():
            reinforcement = self.parameters['reinforcement']
            if reinforcement['schedule'] == 'variable_ratio':
                self.reinf_sched = reinf.VariableRatioSchedule(ratio=reinforcement['ratio'])
            elif reinf['schedule'] == 'fixed_ratio':
                self.reinf_sched = reinf.FixedRatioSchedule(ratio=reinforcement['ratio'])
            else:
                self.reinf_sched = reinf.ContinuousReinforcement()

        else:
            self.reinf_sched = reinf.ContinuousReinforcement()

        if 'block_design' not in self.parameters:
            self.parameters['block_design'] = {
                'blocks': {
                    'default': {
                        'queue': 'random',
                        'conditions': self.parameters['classes'].keys()
                        }
                    },
                'order': ['default'],
                }

    def make_data_csv(self):
        with open(self.data_csv, 'wb') as data_fh:
            trialWriter = csv.writer(data_fh)
            trialWriter.writerow(self.fields_to_save)

    ## session flow
    def check_session_schedule(self):
        return self.check_light_schedule()

    def session_pre(self):
        self.trials = []
        self.session_id += 1
        self.log.info('starting session %s' % self.session_id)

        self.class_assoc = {}
        for class_, class_params in self.parameters['classes'].items():
            try:
                self.class_assoc[class_] = getattr(self.panel,class_params['component'])
            except KeyError:
                pass

        n_blocks = len(self.parameters['block_design']['order'])
        blk_name = self.parameters['block_design']['order'][self.session_id % n_blocks]
        blk = self.parameters['block_design']['blocks'][blk_name]

        q_type = blk.pop('queue')
        self.trial_q = None
        if q_type=='random':
            self.trial_q = queues.random_queue(**blk)
        elif q_type=='block':
            self.trial_q = queues.block_queue(**blk)
        elif q_type=='staircase':
            self.trial_q = queues.staircase_queue(self,**blk)

        return 'main'

    def session_main(self):

        if self.check_session_schedule():
            try:
                self._run_trial()
                return 'main'
            except StopIteration:
                return 'post'

        else:
            return 'post'

    def session_post(self):
        self.log.info('ending session')
        return None

    ## trial flow
    def new_trial(self):
        '''create a new trial and append it to the trial list'''
        do_correction = True
        if len(self.trials) > 0:
            last_trial = self.trials[-1]
            index = last_trial.index+1
            if self.parameters['correction_trials']:
                if last_trial.correct == True:
                    do_correction = False
                elif last_trial.response == 'none':
                    if last_trial.type_ == 'normal':
                        do_correction = False
            else:
                do_correction = False
        else:
            last_trial = None
            index = 0
            do_correction = False

        if do_correction:
            trial = utils.Trial(type_='correction',
                                index=index,
                                class_=last_trial.class_)
            for ev in last_trial.events:
                if ev.label is 'wav':
                    trial.events.append(copy.copy(ev))
                    trial.stimulus_event = trial.events[-1]
                    trial.stimulus = trial.stimulus_event.name
                elif ev.label is 'motif':
                    trial.events.append(copy.copy(ev))
            self.log.debug("correction trial: class is %s" % trial.class_)
        else:
            conditions = next(self.trial_q)

            # if last_trial is not None:
            #     os.remove(last_trial.stimulus_event.file_origin)
            trial = utils.Trial(index=index)
            trial.class_ = conditions.pop(0)
            trial_stim, trial_motifs = self.get_stimuli(trial.class_,*conditions)
            trial.events.append(trial_stim)
            trial.stimulus_event = trial.events[-1]
            trial.stimulus = trial.stimulus_event.name
            for mot in trial_motifs:
                trial.events.append(mot)

        trial.session=self.session_id

        self.trials.append(trial)
        self.this_trial = self.trials[-1]
        self.this_trial_index = self.trials.index(self.this_trial)
        self.log.debug("trial %i: %s, %s" % (self.this_trial.index,self.this_trial.type_,self.this_trial.class_))

        return True

    def get_stimuli(self,trial_class,*conditions):
        # TODO: default stimulus selection
        stim_name = conditions[0]
        stim_file = self.parameters['stims'][stim_name]
        self.log.debug(stim_file)

        stim = utils.auditory_stim_from_wav(stim_file)
        epochs = []
        return stim, epochs

    def analyze_trial(self):
        # TODO: calculate reaction times
        pass

    def save_trial(self,trial):
        '''write trial results to CSV'''

        trial_dict = {}
        for field in self.fields_to_save:
            try:
                trial_dict[field] = getattr(trial,field)
            except AttributeError:
                trial_dict[field] = trial.annotations[field]

        with open(self.data_csv,'ab') as data_fh:
            trialWriter = csv.DictWriter(data_fh,fieldnames=self.fields_to_save,extrasaction='ignore')
            trialWriter.writerow(trial_dict)

    def trial_pre(self):
        ''' this is where we initialize a trial'''
        # make sure lights are on at the beginning of each trial, prep for trial

        self.new_trial()

        self.this_trial = self.trials[-1]
        min_wait = self.this_trial.stimulus_event.duration
        max_wait = self.this_trial.stimulus_event.duration + self.parameters['response_win']
        self.this_trial.annotate(min_wait=min_wait)
        self.this_trial.annotate(max_wait=max_wait)
        self.log.debug('created new trial')
        return 'main'

    def trial_main(self):
        self._run_stimulus()
        self._run_response()
        self._run_consequence()
        return 'post'

    def trial_post(self):
        '''things to do at the end of a trial'''

        self.analyze_trial()
        self.save_trial(self.this_trial)
        self.write_summary()
        utils.wait(self.parameters['intertrial_min'])
        return None

    def _run_trial(self):
        self.log.debug('running trial')
        self.log.debug("number of open file descriptors: %d" %(utils.get_num_open_fds()))
        utils.run_state_machine(start_in='pre',
                                error_state='post',
                                error_callback=self.log_error_callback,
                                pre=self.trial_pre,
                                main=self.trial_main,
                                post=self.trial_post)

    ## stimulus flow
    def stimulus_pre(self):
        # wait for bird to peck
        self.log.debug("presenting stimulus %s" % self.this_trial.stimulus)
        self.log.debug("from file %s" % self.this_trial.stimulus_event.file_origin)
        self.panel.speaker.queue(self.this_trial.stimulus_event.file_origin)
        self.log.debug('waiting for peck...')
        self.panel.center.on()
        self.this_trial.time = self.panel.center.poll() ## need to add a 1 minute timeout to check the sched
        self.panel.center.off()
        self.this_trial.events.append(utils.Event(name='center',
                                                  label='peck',
                                                  time=0.0,
                                                  )
                                            )

        # record trial initiation
        self.summary['trials'] += 1
        self.summary['last_trial_time'] = self.this_trial.time.ctime()
        self.log.info("trial started at %s" % self.this_trial.time.ctime())
        return 'main'

    def stimulus_main(self):
        ## 1. play stimulus
        stim_start = dt.datetime.now()
        self.this_trial.stimulus_event.time = (stim_start - self.this_trial.time).total_seconds()
        self.panel.speaker.play() # already queued in stimulus_pre()
        return 'post'

    def stimulus_post(self):
        self.log.debug('waiting %s secs...' % self.this_trial.annotations['min_wait'])
        utils.wait(self.this_trial.annotations['min_wait'])
        return None

    def _run_stimulus(self):
        utils.run_state_machine(start_in='pre',
                                error_callback=self.log_error_callback,
                                pre=self.stimulus_pre,
                                main=self.stimulus_main,
                                post=self.stimulus_post)

    #response flow
    def response_pre(self):
        for class_, port in self.class_assoc.items():
            port.on()
        self.log.debug('waiting for response')
        return 'main'

    def response_main(self):
        elapsed_time = (dt.datetime.now() - self.this_trial.time).total_seconds()
        rt = elapsed_time - self.this_trial.stimulus_event.time
        if rt > self.this_trial.annotations['max_wait']:
            self.panel.speaker.stop()
            self.this_trial.response = 'none'
            self.log.info('no response')
            return 'post'
        for class_, port in self.class_assoc.items():
            if port.status():
                self.this_trial.rt = rt
                self.panel.speaker.stop()
                self.this_trial.response = class_
                self.summary['responses'] += 1
                response_event = utils.Event(name=self.parameters['classes'][class_]['component'],
                                             label='peck',
                                             time=elapsed_time,
                                             )
                self.this_trial.events.append(response_event)
                self.log.info('response: %s' % (self.this_trial.response))
                return 'post'
        utils.wait(.015)
        return 'main'

    def response_post(self):
        for class_, port in self.class_assoc.items():
            port.off()
        return None

    def _run_response(self):
        utils.run_state_machine(start_in='pre',
                                error_callback=self.log_error_callback,
                                pre=self.response_pre,
                                main=self.response_main,
                                post=self.response_post)

    ## consequence flow
    def consequence_pre(self):
        return 'main'

    def consequence_main(self):
        # correct trial
        if self.this_trial.response==self.this_trial.class_:
            self.this_trial.correct = True

            if self.parameters['reinforcement']['secondary']:
                secondary_reinf_event = self.secondary_reinforcement()
                # self.this_trial.events.append(secondary_reinf_event)

            if self.this_trial.type_ == 'correction':
                self._run_correction_reward()
            elif self.reinf_sched.consequate(trial=self.this_trial):
                self._run_reward() # provide a reward
        # no response
        elif self.this_trial.response is 'none':
            pass

        # incorrect trial
        else:
            self.this_trial.correct = False
            if self.reinf_sched.consequate(trial=self.this_trial):
                self._run_punish()
        return 'post'

    def consequence_post(self):
        self.this_trial.duration = (dt.datetime.now() - self.this_trial.time).total_seconds()
        return None

    def _run_consequence(self):
        utils.run_state_machine(start_in='pre',
                                error_callback=self.log_error_callback,
                                pre=self.consequence_pre,
                                main=self.consequence_main,
                                post=self.consequence_post)


    def secondary_reinforcement(self,value=1.0):
        return self.panel.center.flash(dur=value)

    ## reward flow
    def reward_pre(self):
        self.summary['feeds'] += 1
        return 'main'

    def reward_main(self):
        try:
            value = self.parameters['classes'][self.this_trial.class_]['reward_value']
            reward_event = self.panel.reward(value=value)
            self.this_trial.reward = True
            ## TODO: make rewards into events
            # self.this_trial.events.append(reward_event)

        # but catch the reward errors

        ## note: this is quite specific to the Gentner Lab. consider
        ## ways to abstract this
        except components.HopperAlreadyUpError as err:
            self.this_trial.reward = True
            self.summary['hopper_already_up'] += 1
            self.log.warning("hopper already up on panel %s" % str(err))
            utils.wait(self.parameters['classes'][self.this_trial.class_]['reward_value'])
            self.panel.reset()

        except components.HopperWontComeUpError as err:
            self.this_trial.reward = 'error'
            self.summary['hopper_failures'] += 1
            self.log.error("hopper didn't come up on panel %s" % str(err))
            utils.wait(self.parameters['classes'][self.this_trial.class_]['reward_value'])
            self.panel.reset()

        # except components.ResponseDuringFeedError as err:
        #     trial['reward'] = 'Error'
        #     self.summary['responses_during_reward'] += 1
        #     self.log.error("response during reward on panel %s" % str(err))
        #     utils.wait(self.reward_dur[trial['class']])
        #     self.panel.reset()

        except components.HopperWontDropError as err:
            self.this_trial.reward = 'error'
            self.summary['hopper_wont_go_down'] += 1
            self.log.warning("hopper didn't go down on panel %s" % str(err))
            self.panel.reset()

        finally:
            self.panel.house_light.on()

            # TODO: add errors as trial events

        return 'post'

    def reward_post(self):
        return None

    def _run_reward(self):
        utils.run_state_machine(start_in='pre',
                                error_callback=self.log_error_callback,
                                pre=self.reward_pre,
                                main=self.reward_main,
                                post=self.reward_post)

    def _run_correction_reward(self):
        pass

    ## punishment flow
    def punish_pre(self):
        return 'main'

    def punish_main(self):
        value = self.parameters['classes'][self.this_trial.class_]['punish_value']
        punish_event = self.panel.punish(value=value)
        # self.this_trial.events.append(punish_event)
        self.this_trial.punish = True
        return 'post'

    def punish_post(self):
        return None

    def _run_punish(self):
        utils.run_state_machine(start_in='pre',
                                error_callback=self.log_error_callback,
                                pre=self.punish_pre,
                                main=self.punish_main,
                                post=self.punish_post)

if __name__ == "__main__":

    try: import simplejson as json
    except ImportError: import json

    from pyoperant.local import PANELS

    cmd_line = utils.parse_commandline()
    with open(cmd_line['config_file'], 'rb') as config:
            parameters = json.load(config)


    if parameters['debug']:
        print parameters
        print PANELS

    panel = PANELS[parameters['panel_name']]()

    exp = TwoAltChoiceExp(panel=panel,**parameters)
    exp.run()
