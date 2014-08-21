#!/usr/local/bin/python
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

    cmd_line = utils.parse_commandline()
    with open(cmd_line['config_file'], 'rb') as config:
            parameters = json.load(config)


    if parameters['debug']:
        print parameters
        print PANELS

    panel = PANELS[parameters['panel_name']]()

    exp = Lights(panel=panel,**parameters)
    exp.run()
