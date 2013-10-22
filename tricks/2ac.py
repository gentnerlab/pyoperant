#!/usr/bin/python

# from psychopy import core, data, logging, sound
import os,sys
import numpy as np
from optparse import OptionParser
from pyoperant import hwio, misc

def parse_commandline(args=sys.argv[1:]):
    # parse command line arguments
    # note: optparse is depreciated w/ v2.7 in favor of argparse
    parser=OptionParser()
    parser.add_option('-B','--box',
                      action='store',type='int',dest='box',
                      help='(int) box identifier')
    parser.add_option('-S','--subject',
                      action='store',type='string',dest='subj',
                      help='(string) subject ID and folder name')
    parser.add_option('-c','--config',
                      action='store',type='string',dest='config_file',default='config.py',
                      help='(string) configuration file [default: %default]')
    
    #parser.add_option('-s','--stimfile',
    #                  action='store',type='string',dest='stimfile',
    #                  help='(string) define stim file')
    #parser.add_option('-x','--xtrials',
    #                  action='store_true',dest='xtrials',default=False,
    #                  help='turn on correction trials for incorrent responses')
    #parser.add_option('-w','--window',
    #                  action='store',type='float',dest='resp_win',
    #                  help='(float) define response window in seconds [default: %default]')
    #parser.add_option('-t','--timeout',
    #                  action='store',type='float',dest='timeout',
    #                  help='(float) define timeout duration in seconds [default: %default]')
    #parser.add_option('-f','--flash',
    #                  action='store_true',dest='flash',default=False,
    #                  help='flash response lights to encourage trial initiation')
    #parser.add_option('-q','--cue',
    #                  action='store_true',dest='cue',default=False,
    #                  help='turn on cue')
    #parser.add_option('--on',
    #                  action='store',type='string',dest='ontime',default='sunrise',
    #                  help='define hour:min to turn on lights')
    #parser.add_option('--off',
    #                  action='store',type='string',dest='offtime',default='sunset',
    #                  help='define hour:min to turn off lights')
    #parser.add_option('-r','--reinf',
    #                  action='store_true',dest='reinf',default=False,
    #                  help='turn on secondary reinforcement')
    parser.set_defaults()
    (options, args) = parser.parse_args(args)
    return (options,args)

def read_stim(stimfile):
    dt=[('class','i8'),('wavname','|S128'),('relfreq','i8'),('reinf_pos','i8'),('reinf_neg','i8')]
    stimdata = np.genfromtxt(stimfile,dtype=dt) 
    return stimdata
  
def doTrial(exp,config):
    pass


def run(exp,config):
    pass
  

def main():

    if trial.ready():
        panel.reset() # reset everything
        trial.time = panel.wait_for_start()
        stimulus_event = panel.
        trial.response = panel.response.poll(min=2.0,max=5.0) # poll for a response from anything w/ "response" role
        panel.reward(value=2.0) # should cause hopper to raise for 2 seconds
        panel.aversive(value=30.0) #should cause timeout for 30 seconds
    else
        wait()

if __name__ == "__main__":
  
    # set path variables
    CODE_ROOT = os.path.dirname(os.path.realpath(__file__))
    USER_ROOT = os.path.expanduser('~')
    OPDAT_ROOT = os.path.join(USER_ROOT,'opdat')
  
    (options,args) = parse_commandline()
  
    print 'Options:',options

    BIRD_ROOT = os.path.join(OPDAT_ROOT,options.subj)
    STIM_ROOT = os.path.join(BIRD_ROOT,'stims')  

    # load stim file
    stimdata = read_stim(os.path.join(BIRD_ROOT, options.stimfile))
    print stimdata['wavname']

    # TODO: check for existance of stim files

