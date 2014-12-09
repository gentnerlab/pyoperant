#!/usr/bin/env python
import os
from pyoperant import utils, components
from pyoperant.behavior import base

class Lights(base.BaseExp):
    """docstring for Lights"""
    def __init__(self,  *args, **kwargs):
        super(Lights, self).__init__(*args, **kwargs)

    def panel_reset(self):
        try:
            self.panel.reset()
        except components.HopperWontDropError:
            pass

if __name__ == "__main__":

    try: import simplejson as json
    except ImportError: import json

    from pyoperant.local import PANELS

    try:
        from pyoperant.local import DATAPATH
    except ImportError:
        DATAPATH = '/home/bird/opdat'


    cmd_line = utils.parse_commandline()

    experiment_path = os.path.join(DATAPATH,'B'+cmd_line['subj'])
    config_file = os.path.join(experiment_path,cmd_line['config_file'])
    stimuli_path = os.path.join(experiment_path,'Stimuli')

    with open(config_file, 'rb') as config:
            parameters = json.load(config)

    if parameters['debug']:
        print parameters
        print PANELS

    BehaviorProtocol = Lights

    behavior = BehaviorProtocol(
        panel=PANELS[str(cmd_line['box'])](),
        subject='B'+cmd_line['subj'],
        panel_name=cmd_line['box'],
        experiment_path=experiment_path,
        stim_path=stimuli_path,
        **parameters
        )

    behavior.run()
