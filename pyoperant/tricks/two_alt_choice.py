#!/usr/bin/python

# from psychopy import core, data, logging, sound
from pyoperant.tricks import base
from pyoperant

class TwoAltChoiceExp(base.BaseExp):
    """docstring for Experiment"""
    def __init__(self,summaryDAT, *args, **kwargs):
        super(Experiment,  self).__init__(self, *args, **kwargs)

        # assign stim files full names
        for name, filename in self.parameters['stims'].items():
            filename_full = os.path.join(self.parameters['stim_path'], filename)
            self.parameters['stims'][name] = filename_full

        self.req_panel_attr.append(['speaker',
                                    'left',
                                    'center',
                                    'right',
                                    'reward',
                                    'punish',
                                    ])

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
                               'timeout',
                               'time',
                               ]

        self.trials = []
        self.session_id = 0

        self.data_csv = os.path.join(self.parameters['subject_path'], 
                                     self.parameters['subject_id']+'_trialdata_'+self.exp_timestamp+'.csv')

        if 'reinforcement' in self.parameters.keys():
            reinf = self.parameters['reinforcement']
            if reinf['schedule'] == 'variable_ratio':
                self.reinf_sched = reinf.VariableRatioSchedule(ratio=reinf['ratio'])
            elif reinf['schedule'] == 'fixed_ratio':
                self.reinf_sched = reinf.FixedRatioSchedule(ratio=reinf['ratio'])
            else:
                self.reinf_sched = reinf.ContinuousReinforcement()

        else:
            self.reinf_sched = reinf.ContinuousReinforcement()

    def make_data_csv(self):
        with open(self.data_csv, 'wb') as data_fh:
            trialWriter = csv.writer(data_fh)
            trialWriter.writerow(self.fields_to_save)

    ## session flow
    def check_session_schedule(self):
        return not self.check_light_schedule()

    def session_pre(self):
        self.trials = []
        self.session_id += 1

        self.class_assoc = {}
        for class_, class_params in self.parameters['classes'].items():
            try:
                resp_port[class_] = getattr(self.panel,class_params['component'])
            except KeyError:
                pass

        return 'main'

    def session_main(self):
        try:
            self._trial_flow()
            return 'main'
        except utils.GoodNite:
            return 'post'

    ## trial flow
    def new_trial(self):
        '''create a new trial and append it to the trial list'''
        try:
            last_trial = self.trials[-1]
            index = last_trial.index+1
        except IndexError:
            last_trial = None
            index = 0

        do_correction = False
        if last_trial is not None:
            if self.parameters['correction_trials'] and last_trial.response and (last_trial.correct==False):
                do_correction = True
                    
        if do_correction:
            trial = Trial(tr_type='correction',
                          index=index,
                          tr_class=last_trial.tr_class)
            for ev in last_trial.events:
                if ev.label is 'wav':
                    trial.events.append(ev[:])
                    trial.stimulus_event = correction.events[-1]
                    trial.stimulus = trial.stimulus_event.name
                elif ev.label is 'motif':
                    correction.events.append(ev[:])
            self.log.debug("correction trial: class is %s" % trial.tr_class)
        else:
            trial = Trial(index=index)
            trial.tr_class = random.choice(self.models.keys())
            trial_stim, trial_motifs = self.get_stimuli(trial['class'])
            trial.events.append(trial_stim)
            trial.stim_event = trial.events[-1]
            trial.stimulus = trial.stim_event.name
            for mot in trial_motifs:
                trial.events.append(mot)

        self.trials.append(trial)
        self.this_trial = self.trials[-1]
        self.this_trial_index = selfz.trials.index(self.this_trial)
        self.log.debug("trial %i: %s, %s" % (trial['index'],trial['type'],trial['class']))

        return True

    def get_stimuli(self,trial_class):
        # TODO: default stimulus selection
        pass

    def analyze_trial(self,trial_class):
        # TODO: calculate reaction times
        pass

    def save_trial(self,trial):
        '''write trial results to CSV'''

        trial_dict = {}
        for field in self.fields_to_save:
            try:
                trial_dict[field] = getattr(trial,field)
            except AttributeError:
                try:
                    trial_dict[field] = trial.annotations[field]
                except KeyError:
                    trial_dict[field] = None


        with open(self.data_csv,'ab') as data_fh:
            trialWriter = csv.DictWriter(data_fh,fieldnames=self.fields_to_save,extrasaction='ignore')
            trialWriter.writerow(trial_dict)

    def trial_pre(self):
        ''' this is where we initialize a trial'''
        # make sure lights are on at the beginning of each trial, prep for trial

        self.new_trial()

        self.this_trial = self.trials[-1]
        min_epoch = self.this_trial.events[self.strlen_min-1]
        self.this_trial.annotate(min_epoch=min_epoch)
        self.this_trial.annotate(min_wait=min_epoch.time+min_epoch.duration)
        stim = trial.events[]
        max_wait = trial_stim.duration + self.parameters['response_win']
        self.this_trial.annotate(max_wait=max_wait)
        return 'main'

    def trial_main(self):
        self._stimulus_flow()
        self._response_flow()
        self._consequence_flow()
        return 'post'

    def trial_post(self):
        '''things to do at the end of a trial'''

        self.analyze_trial()
        self.save_trial(self.this_trial)
        self.write_summary()
        utils.wait(self.intertrial_min)
        return None

    def _trial_flow(self):
        try: 
            utils.do_flow(pre=self.trial_pre,
                         main=self.trial_main,
                         post=self.trial_post)

        except hwio.CriticalError as err:
            self.log.critical(str(err))
            self.trial_post()

        except hwio.Error as err:
            self.log.error(str(err))
            self.trial_post()


    ## stimulus flow
    def stimulus_pre(self):
        # wait for bird to peck
        self.log.debug('waiting for peck...')
        self.panel.center.on()
        self.this_trial.time = panel.center.poll()
        self.panel.center.off()

        # record trial initiation
        self.summary['trials'] += 1
        self.summary['last_trial_time'] = self.this_trial.time.ctime()
        self.log.info("trial started at %s" % self.this_trial.time.ctime())
        return 'main'

    def stimulus_main(self):
        ## 1. play stimulus
        stim_start = dt.datetime.now()
        self.this_trial.stimulus_event.time = (stim_start - self.this_trial.time).total_seconds()
        self.wave_stream = panel.speaker.play_wav(trial.stimulus_event.file_origin)
        return 'post'

    def stimulus_post(self):
        utils.wait(self.this_trial.annotations['min_wait'])
        return None

    def _stimulus_flow(self):
        utils.do_flow(pre=self.stimulus_pre,
                      main=self.stimulus_main,
                      post=self.stimulus_post)

    #response flow
    def response_pre(self):
        self.panel.left.on()
        self.panel.right.on()
        return 'main'

    def response_main(self):

        while True:
            elapsed_time = (dt.datetime.now() - stim_start).total_seconds()
            if elapsed_time > self.max_wait:
                self.this_trial.response = 'none'
                break
            for class_, port in self.class_assoc.items():
                if port.status():
                    trial.rt = trial.time + elapsed_time
                    wave_stream.close()
                    trial.response = class_
                    self.summary['responses'] += 1
                    break

        return 'post'

    def response_post(self):
        self.panel.left.off()
        self.panel.right.off()
        return None

    def response_flow(self):
        utils.do_flow(pre=self.response_pre,
                      main=self.response_main,
                      post=self.response_post)

    ## consequence flow
    def consequence_pre(self):
        return 'main'

    def consequence_main(self):
        # correct trial
        if self.this_trial.response is self.this_trial.tr_class:
            self.this_trial.correct = True
            
            if self.parameters['reinforcement']['secondary']:
                secondary_reinf_event = self.secondary_reinforcement()
                self.this_trial.events.append(secondary_reinf_event)

            if self.trial.type == 'correction':
                pass
            elif self.reinf_sched.consequate(trial=self.this_trial):
                self._reward_flow() # provide a reward
        # no response
        elif self.trial.response is 'none':
            pass

        # incorrect trial
        else:
            self.this_trial.correct = False
            if self.reinf_sched.consequate(trial=self.this_trial):
                self._punish_flow()
        return 'post'

    def consequence_post(self):
        self.this_trial.duration = (dt.datetime.now() - self.this_trial.time).total_seconds()
        return None

    def _consequence_flow(self):
        utils.do_flow(pre=self.consequence_pre,
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
            value = self.parameters[self.this_trial.class_]['reward_value']
            reward_event = self.panel.reward(value=value)
            self.this_trial.reward = True
            ## TODO: make rewards into events
            # self.this_trial.events.append(reward_event)

        # but catch the reward errors

        except components.HopperAlreadyUpError as err:
            self.this_trial.reward = True
            self.summary['hopper_already_up'] += 1
            self.log.warning("hopper already up on panel %s" % str(err))
            utils.wait(self.parameters[self.this_trial.class_]['reward_value'])
            self.panel.reset()

        except components.HopperWontComeUpError as err:
            self.this_trial.reward = 'error'
            self.summary['hopper_failures'] += 1
            self.log.error("hopper didn't come up on panel %s" % str(err))
            utils.wait(self.parameters[self.this_trial.class_]['reward_value'])
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

    def _reward_flow(self):
        utils.do_flow(pre=self.reward_pre,
                      main=self.reward_main,
                      post=self.reward_post)

    ## punishment flow
    def punish_pre(self):
        return 'main'

    def punish_main(self):
        punish_event = self.panel.punish(value=self.timeout_dur[trial['class']])
        self.this_trial.events.append(punish_event)
        self.this_trial.punish = True
        return 'post'

    def punish_post(self):
        return None

    def _punish_flow(self):
        utils.do_flow(pre=self.punish_pre,
                      main=self.punish_main,
                      post=self.punish_post)


            



