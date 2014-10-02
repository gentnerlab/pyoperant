#!/usr/bin/env python

def parse_commandline(arg_str=sys.argv[1:]):
    """ parse command line arguments

    """
    parser=ArgumentParser()
    parser.add_argument('protocol', 
                        action='store', 
                        type=str, 
                        required=True,
                        help='(str) experiment protocol'
                        )
    parser.add_argument('-P', '--panel',
                        action='store', 
                        type=str, 
                        dest='panel', 
                        required=True,
                        help='(string) panel identifier'
                        )
    parser.add_argument('-S', '--subject',
                        action='store', 
                        type=str, 
                        dest='subject', 
                        required=True,
                        help='subject identifier'
                        )
    parser.add_argument('-c','--config',
                        action='store', 
                        type=str, 
                        dest='config_file', 
                        default='config.json', 
                        required=False,
                        help='configuration file [default: %(default)s]'
                        )
    args = parser.parse_args(arg_str)
    return vars(args)

if __name__ == "__main__":

    try: import simplejson as json
    except ImportError: import json

    from pyoperant.local import PANELS

    try:
        from pyoperant.local import BEHAVIORS:
    except ImportError:
        BEHAVIORS = ['pyoperant.behavior']

    cmd_line = parse_commandline()
    with open(cmd_line['config_file'], 'rb') as config:
            parameters = json.load(config)

    for package in BEHAVIORS:
        try:
            BehaviorProtocol = getattr(__import__(package, fromlist=[cmd_line.protocol]), cmd_line.protocol)
            break
        except ImportError:
            continue

    if parameters['debug']:
        print parameters
        print PANELS

    behavior = BehaviorProtocol(panel=PANELS[parameters[cmd_line.panel]](),
                                subject=cmd_line.subject,
                                **parameters,
                                )
    behavior.run()
