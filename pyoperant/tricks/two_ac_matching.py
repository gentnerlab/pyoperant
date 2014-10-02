#!/usr/bin/python

import random, os
from pyoperant import utils, components
from pyoperant.tricks import two_alt_choice, shape

class TwoACMatchingExp(two_alt_choice.TwoAltChoiceExp):
    """docstring for TwoACMatchingExp"""
    def __init__(self, *args, **kwargs):
        super(TwoACMatchingExp, self).__init__(*args, **kwargs)

        self.num_stims = len(self.parameters['stims'].items())
        self.stim_sources = sort(self.parameters['stims'].keys())

        if 'reduced_stims' not in self.parameters or not self.parameters['reduced_stims']:
            self.parameters['reduced_stims'] = False
            self.log.debug('Using full stimuli set')
        else:
            try:
                self.parameters['reduced_stims'] = int(self.parameters['reduced_stims'])
            except ValueError:
                self.parameters['reduced_stims'] = False
                self.log.debug('Invalid reduced_stims value, using full stimuli set')
            else:
                assert self.parameters['reduced_stims'] >= 2 and self.parameters['reduced_stims'] < self.num_stims
                self.log.debug('Using reduced stimuli set only')
                self.stim_sources = self.stim_sources[:self.parameters['reduced_stims']]

        #self.shaper = shape.Shaper2ACMatching(self.panel, self.log, self.parameters, self.get_stimuli, self.log_error_callback)
        self.shaper = shape.Shaper(self.panel, self.log, self.parameters, self.get_stimuli, self.log_error_callback)

    def get_stimuli(self, trial_class):
        """ take trial class and return a tuple containing the stimulus event to play and a list of additional events

        """
        form = random.sample(self.parameters['classes'][trial_class]['patterns'], 1)[0].encode('ascii')
        symbols = list(set(form))
        mids = random.sample(self.stim_sources, len(symbols))

        sym_map = {symbols[i]:mids[i] for i in range(len(symbols))}

        motif_names = [sym_map[f] for f in form]

        motif_files = [parameters['stims'][mid] for mid in a]

        motif_isi = [max(random.gauss(self.parameters['isi_mean'], self.parameters['isi_stdev']), 0.0) for mot in motif_names]
        motif_isi[-1] = 0.0

        input_files = zip(motif_files, motif_isi)
        filename = os.path.join(self.parameters['stim_path'], ''.join(motif_names) + '.wav')
        stim, epochs = utils.concat_wav(input_files, filename)

        for ep in epochs:
            for stim_name, f_name in self.parameters['stims'].items():
                if ep.name in f_name:
                    ep.name = stim_name

        return stim, epochs

    def analyze_trial(self):
        super(TwoACMatchingExp)

    def correction_reward_pre(self):
        self.summary['feeds'] += .5
        return 'main'

    def correction_reward_main(self):
        try:
            value = self.parameters['classes'][self.this_trial.class_]['reward_value'] * .5
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

    def correction_reward_post(self):
        return None

    def _run_correction_reward(self):
        utils.run_state_machine(start_in='pre',
                                error_callback=self.log_error_callback,
                                pre=self.correction_reward_pre,
                                main=self.correction_reward_main,
                                post=self.correction_reward_post)

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

    exp = TwoACMatchingExp(panel=panel,**parameters)
    exp.run()


