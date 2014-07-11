#!/usr/local/bin/python
if __name__ == '__main__' and __package__ is None:
    from os import sys, path
    sys.path.append(path.dirname(path.dirname(path.abspath(__file__))))
import utils

if __name__ == "__main__":

    try: import simplejson as json
    except ImportError: import json

    #from pyoperant.local import PANELS

    cmd_line = utils.parse_commandline()
    with open(cmd_line['config_file'], 'rb') as config:
            parameters = json.load(config)

    assert utils.check_cmdline_params(parameters, cmd_line)

    #if parameters['debug']:
    #    print parameters
    #    print PANELS

    #panel = PANELS[parameters['panel_name']]()

    #exp = TwoAltChoiceExp(panel=panel,**parameters)
    #exp.run()
