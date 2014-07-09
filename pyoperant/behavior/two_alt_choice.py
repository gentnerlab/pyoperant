#!/usr/local/bin/python

import os
import csv
import copy
import datetime as dt
from pyoperant.behavior import base, shape
from pyoperant.errors import EndSession
from pyoperant import components, utils, reinf, queues

class TwoAltChoiceExp(base.BaseExp):
    """A two alternative choice experiment

    Parameters
    ----------


    Attributes
    ----------
    req_panel_attr : list
        list of the panel attributes that are required for this behavior
    fields_to_save : list
        list of the fields of the Trial object that will be saved
    trials : list
        all of the trials that have run
    shaper : Shaper
        the protocol for shaping 
    parameters : dict 
        all additional parameters for the experiment
    data_csv : string 
        path to csv file to save data
    reinf_sched : object
        does logic on reinforcement



    """
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

        if 'add_fields_to_save' in self.parameters.keys():
            self.fields_to_save += self.parameters['add_fields_to_save']

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
                        'conditions': [{'class': k} for k in self.parameters['classes'].keys()]
                        }
                    },
                'order': ['default']
                }

    def make_data_csv(self):
        """ Create the csv file to save trial data

        This creates a new csv file at experiment.data_csv and writes a header row 
        with the fields in experiment.fields_to_save
        """
        with open(self.data_csv, 'wb') as data_fh:
            trialWriter = csv.writer(data_fh)
            trialWriter.writerow(self.fields_to_save)

    ## session flow
    def check_session_schedule(self):
        """ Check the session schedule

        Returns
        -------
        bool
            True if sessions should be running
        """
        return self.check_light_schedule()

    def session_pre(self):
        """ Runs before the session starts

        For each stimulus class, if there is a component associated with it, that
        component is mapped onto `experiment.class_assoc[class]`. For example, 
        if the `left` port is registered with the 'L' class, you can access the response 
        port through `experiment.class_assoc['L']`.

        """
        self.class_assoc = {}
        for class_, class_params in self.parameters['classes'].items():
            try:
                self.class_assoc[class_] = getattr(self.panel,class_params['component'])
            except KeyError:
                pass

        return 'main'

    def session_main(self):
        """ Runs the sessions

        Inside of `session_main`, we loop through sessions and through the trials within
        them. This relies heavily on the 'block_design' parameter, which controls trial
        conditions and the selection of queues to generate trial conditions.

        """

        self.session_q = queues.block_queue(self.parameters['block_design']['order'])

        for sn_cond in self.session_q:

            self.trials = []
            self.do_correction = False
            self.session_id += 1
            self.log.info('starting session %s: %s' % (self.session_id,sn_cond))

            # grab the block details
            blk = copy.deepcopy(self.parameters['block_design']['blocks'][sn_cond])

            # load the block details into the trial queue
            self.trial_q = None
            q_type = blk.pop('queue')
            if q_type=='random':
                self.trial_q = queues.random_queue(**blk)
            elif q_type=='block':
                self.trial_q = queues.block_queue(**blk)
            elif q_type=='staircase':
                self.trial_q = queues.staircase_queue(self,**blk)


            for tr_cond in self.trial_q:
                try:
                    self.new_trial(tr_cond)
                    self.run_trial()
                    while self.do_correction:
                        self.new_trial(tr_cond)
                        self.run_trial()
                except EndSession:
                    return 'post'

        return 'post'

    def session_post(self):
        """ Closes out the sessions

        """
        self.log.info('ending session')
        return None

    ## trial flow
    def new_trial(self,conditions=None):
        """Creates a new trial and appends it to the trial list

        If `self.do_correction` is `True`, then the conditions are ignored and a new
        trial is created which copies the conditions of the last trial.

        Parameters
        ----------
        conditions : dict
            The conditions dict must have a 'class' key, which specifys the trial
            class. The entire dict is passed to `exp.get_stimuli()` as keyword
            arguments and saved to the trial annotations.

        """
        if len(self.trials) > 0:
            index = self.trials[-1].index+1
        else:
            index = 0

        if self.do_correction:
            # for correction trials, we want to use the last trial as a template
            trial = utils.Trial(type_='correction',
                                index=index,
                                class_=self.trials[-1].class_)
            for ev in self.trials[-1].events:
                if ev.label is 'wav':
                    trial.events.append(copy.copy(ev))
                    trial.stimulus_event = trial.events[-1]
                    trial.stimulus = trial.stimulus_event.name
                elif ev.label is 'motif':
                    trial.events.append(copy.copy(ev))
            self.log.debug("correction trial: class is %s" % trial.class_)
        else:
            # otherwise, we'll create a new trial
            trial = utils.Trial(index=index)
            trial.class_ = conditions['class']
            trial_stim, trial_motifs = self.get_stimuli(**conditions)
            trial.events.append(trial_stim)
            trial.stimulus_event = trial.events[-1]
            trial.stimulus = trial.stimulus_event.name
            for mot in trial_motifs:
                trial.events.append(mot)

        trial.session=self.session_id
        trial.annotate(**conditions)

        self.trials.append(trial)
        self.this_trial = self.trials[-1]
        self.this_trial_index = self.trials.index(self.this_trial)
        self.log.debug("trial %i: %s, %s" % (self.this_trial.index,self.this_trial.type_,self.this_trial.class_))

        return True

    def get_stimuli(self,**conditions):
        """ Get the trial's stimuli from the conditions

        Returns
        -------
        stim, epochs : Event, list 


        """
        # TODO: default stimulus selection
        stim_name = conditions['stim_name']
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

    def run_trial(self):
        self.trial_pre()

        self.stimulus_pre()
        self.stimulus_main()
        self.stimulus_post()

        self.response_pre()
        self.response_main()
        self.response_post()

        self.consequence_pre()
        self.consequence_main()
        self.consequence_post()

        self.trial_post()

    def trial_pre(self):
        ''' this is where we initialize a trial'''
        # make sure lights are on at the beginning of each trial, prep for trial
        self.log.debug('running trial')
        self.log.debug("number of open file descriptors: %d" %(utils.get_num_open_fds()))

        self.this_trial = self.trials[-1]
        min_wait = self.this_trial.stimulus_event.duration
        max_wait = self.this_trial.stimulus_event.duration + self.parameters['response_win']
        self.this_trial.annotate(min_wait=min_wait)
        self.this_trial.annotate(max_wait=max_wait)
        self.log.debug('created new trial')
        self.log.debug('min/max wait: %s/%s' % (min_wait,max_wait))


    def trial_post(self):
        '''things to do at the end of a trial'''
        self.this_trial.duration = (dt.datetime.now() - self.this_trial.time).total_seconds()
        self.analyze_trial()
        self.save_trial(self.this_trial)
        self.write_summary()
        utils.wait(self.parameters['intertrial_min'])

        # determine if next trial should be a correction trial
        self.do_correction = True
        if len(self.trials) > 0:
            if self.parameters['correction_trials']:
                if self.this_trial.correct == True:
                    self.do_correction = False
                elif self.this_trial.response == 'none':
                    if self.this_trial.type_ == 'normal':
                        self.do_correction = False
            else:
                self.do_correction = False
        else:
            self.do_correction = False

        if self.check_session_schedule()==False:
            raise EndSession

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

    def stimulus_main(self):
        ## 1. play cue
        cue = self.this_trial.annotations["cue"]
        if  len(cue) > 0:
            self.log.debug("cue light turning on")
            cue_start = dt.datetime.now()
            if cue=="red":
                self.panel.cue.red()
            elif cue=="green":
                self.panel.cue.green()
            elif cue=="blue":
                self.panel.cue.blue()
            utils.wait(self.parameters["cue_duration"])
            self.panel.cue.off()
            cue_dur = (dt.datetime.now() - cue_start).total_seconds()
            cue_time = (cue_start - self.this_trial.time).total_seconds()
            cue_event = utils.Event(time=cue_time,
                                    duration=cue_dur,
                                    label='cue',
                                    name=cue,
                                    )
            self.this_trial.events.append(cue_event)
            utils.wait(self.parameters["cuetostim_wait"])

        ## 2. play stimulus
        stim_start = dt.datetime.now()
        self.this_trial.stimulus_event.time = (stim_start - self.this_trial.time).total_seconds()
        self.panel.speaker.play() # already queued in stimulus_pre()

    def stimulus_post(self):
        self.log.debug('waiting %s secs...' % self.this_trial.annotations['min_wait'])
        utils.wait(self.this_trial.annotations['min_wait'])

    #response flow
    def response_pre(self):
        for class_, port in self.class_assoc.items():
            port.on()
        self.log.debug('waiting for response')

    def response_main(self):
        while True:
            elapsed_time = (dt.datetime.now() - self.this_trial.time).total_seconds()
            rt = elapsed_time - self.this_trial.stimulus_event.time
            if rt > self.this_trial.annotations['max_wait']:
                self.panel.speaker.stop()
                self.this_trial.response = 'none'
                self.log.info('no response')
                return
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
                    return
            utils.wait(.015)

    def response_post(self):
        for class_, port in self.class_assoc.items():
            port.off()

    ## consequence flow
    def consequence_pre(self):
        pass

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
                self.reward_pre()
                self.reward_main() # provide a reward
                self.reward_post()

        # no response
        elif self.this_trial.response is 'none':
            pass

        # incorrect trial
        else:
            self.this_trial.correct = False
            if self.reinf_sched.consequate(trial=self.this_trial):
                self.punish_pre()
                self.punish_main()
                self.punish_post()

    def consequence_post(self):
        pass


    def secondary_reinforcement(self,value=1.0):
        return self.panel.center.flash(dur=value)

    ## reward flow
    def reward_pre(self):
        pass

    def reward_main(self):
        self.summary['feeds'] += 1
        try:
            value = self.parameters['classes'][self.this_trial.class_]['reward_value']
            reward_event = self.panel.reward(value=value)
            self.this_trial.reward = True

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

    def reward_post(self):
        pass

    def _run_correction_reward(self):
        pass

    ## punishment flow
    def punish_pre(self):
        pass

    def punish_main(self):
        value = self.parameters['classes'][self.this_trial.class_]['punish_value']
        punish_event = self.panel.punish(value=value)
        self.this_trial.punish = True

    def punish_post(self):
        pass

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
