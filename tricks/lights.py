#!/usr/bin/python

import os,sys
import datetime
from optparse import OptionParser
from pyoperant import hwio, misc

class Config():
    def __init__(self):
        self.options = []
        self.args = []

def parse_commandline(args=sys.argv[1:]):
    # parse command line arguments
    # note: optparse is depreciated w/ v2.7 in favor of argparse
    parser=OptionParser()
    parser.add_option('-B', '--box',
                      action='store', type='int', dest='box',
                      help='(int) box identifier')
    parser.add_option('--on',
                      action='store', type='string', dest='ontime', default='sunrise',
                      help='define hour:min to turn on lights')
    parser.add_option('--off',
                      action='store', type='string', dest='offtime', default='sunset',
                      help='define hour:min to turn off lights')
    (options, args) = parser.parse_args(args)
    return (options,args)

def run(exp,config):
    """Runs the experiment"""
    sun_check = True
    
    box = hwio.OperantBox(config.options.box)

    on_time_s = config.options.ontime
    off_time_s = config.options.offtime

    if (on_time_s=='sunrise' or on_time_s=='99') and (off_time_s=='sunset' or off_time_s=='99'):
        sun_check = True 
    else:
        sun_check = False
        on_time = datetime.datetime.strptime(on_time_s,"%H:%S").time()
        off_time = datetime.datetime.strptime(off_time_s,"%H:%S").time()

    time_freq = 1.0 # check time every minute
    do_lights = True
    
    box.lights_on(False)
    
    while do_lights:
        if sun_check:
            box.lights_on(misc.is_day())
        else:
            now_time = datetime.datetime.today().time()

            if (now_time > on_time) and (now_time < off_time):
                box.lights_on(True)
            else:
                box.lights_on(False)
        hwio.wait(60.0)


if __name__ == "__main__":
  
    config = Config()

    # set path variables
    CODE_ROOT = os.path.dirname(os.path.realpath(__file__))
  
    # read the arguments
    (config.options,config.args) = parse_commandline()
  
    # define experiment
    exp = []

    run(exp,config)
