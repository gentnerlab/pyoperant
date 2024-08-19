import os
import csv
import copy
import datetime as dt
from pyoperant.behavior import base, shape
from pyoperant.errors import EndSession, EndBlock
from pyoperant import components, utils, reinf, queues

import serial
import random

class PlacePrefExp24hr(base.BaseExp):
    '''
    A place preference experiment. This version is identical to PlacePrefExp,
    except that it is modified to record 24/7.

    In this paradigm, a bird is released into a cage with three nestbox perches.
    The logic of this experiment is that when a bird lands on a perch for
    sufficiently long enough, a trial will start and the stimulus will start
    playing from a library, shuffling through the library as the bird continues
    to perch. When the bird leaves the perch, the song will stop.

    Nighttime activity is also recorded.

    The data that need to be recorded are
    1. When did the bird land on the perch?
    2. Which perch did the bird land on?
    3. How long did the bird land?
    4. Did this bird land long enough for the songs to trigger?
    5. Which category of song was the perch playing?
    6. What actual stimuli were playing?


    Parameters
    ----------

    Attributes
    ----------
    req_panel_attr : list
        list of the panel attributes that are required for this behavior
    fields_to_save : list
        list of the fields of the Trial object that will be saved
    trials : list
        all the trials that have run
    parameter : dict
        all additional parameters for the experiment
    data_csv : string
        path to csv file to save data_csv
    '''

    def __init__(self, *args, **kwargs):
        super(PlacePrefExp24hr, self).__init__(*args, **kwargs)

        ## assign stim files full names
        for name, filename in self.parameters['stims_A'].items():
            filename_full = os.path.join(self.parameters['stims_A_path'], filename)
            self.parameters['stims_A'][name] = filename_full

        ## assign stim files full names
        for name, filename in self.parameters['stims_B'].items():
            filename_full = os.path.join(self.parameters['stims_B_path'], filename)
            self.parameters['stims_B'][name] = filename_full

        self.req_panel_attr += [
            'speaker',
            'left',
            'center',
            'right',
            'house_light',
            'reset'
        ]

        self.fields_to_save = [
            'perch_strt',
            'perch_end',
            'perch_dur',
            'perch_loc',
            'valid',
            'class_',
            'stimuli',
            'events',
            'vr',
            'reinforcement'
        ]

        if 'add_fields_to_save' in self.parameters.keys():
            self.fields_to_save += self.parameters['add_fields_to_save']

        self.exp_strt_date = dt.date(
            year = self.parameters['experiment_start_year'],
            month = self.parameters['experiment_start_month'],
            day = self.parameters['experiment_start_day']
        )

        self.daylight = None

        self.current_perch = {'IR': None, 'IRName': None, 'speaker': None}
        self.current_visit = None
        self.stimulus_event = None

        self.reinforcement_counter = {'L': None, 'R': None, 'C': None}  ## set up separate reinforcement counters for all perches

        self.arduino = serial.Serial(self.parameters['arduino_address'], self.parameters['arduino_baud_rate'], timeout = 1)
        self.arduino.reset_input_buffer()

        self.data_csv = os.path.join(self.parameters['experiment_path'],
                                     self.parameters['subject']+'_trialdata_'+self.timestamp+'.csv')

        self.make_data_csv()

    def make_data_csv(self):
        """ Create the csv file to save trial data

        This creates a new csv file at experiment.data_csv and writes a header row
        with the fields in experiment.fields_to_save
        """
        with open(self.data_csv, 'wb') as data_fh:
            trialWriter = csv.writer(data_fh)
            trialWriter.writerow(self.fields_to_save)

def open_all_perches(self):
        """
        At down state (no active trials), open IR on all perches
        """
        self.log.debug("Opening all perches!")

        ## normally IR status returns false if a beam is not broken.
        ## If one of them is broken, return true
        while self.current_perch['IR'] == None:

            ## check if a daylight cycle shift should occur
            if self.check_session_schedule() :
                return

            ## for each iteration, check for perching behavior.
            left_perched = self.panel.left.status()
            center_perched = self.panel.center.status()
            right_perched = self.panel.right.status()

            if left_perched:
                self.current_perch['IR'] = self.panel.left
                self.current_perch['IRName'] = 'L'
                self.current_perch['speaker'] = 0
                break
            if center_perched:
                self.current_perch['IR'] = self.panel.center
                self.current_perch['IRName'] = 'C'
                self.current_perch['speaker'] = 1
                break
            if right_perched:
                self.current_perch['IR'] = self.panel.right
                self.current_perch['IRName'] = 'R'
                self.current_perch['speaker'] = 2
                break

        ## Record time of break
        self.log.debug("Beam-break sensed on %s" % (self.current_perch))
        self.current_visit = utils.Visit()
        self.current_visit.perch_strt = dt.datetime.now()
        self.current_visit.perch_loc = self.current_perch['IRName']
        self.current_visit.class_ = self.current_perch_stim_class()

        ## pre populate
        self.current_visit.reinforcement = False ## default do nothing
        self.current_visit.vr = self.current_variable_ratio()

        ## if validate perching fails, reset perches and open
        if (self.validate_perching() == False):
            self.end_visit()
            self.reset_perches()
            try:
                self.open_all_perches()
            except RuntimeError:
                self.log.debug("RuntimeError: max recursion")
                return
        else:
            self.log.debug("Perch valid at %s" % (self.current_perch))

    def light_switch():
        '''
        This checks if paradigm daylight is incongruent with system time
        '''
        return self.daylight != utils.check_time(self.parameters['light_schedule'])

    def session_pre(self):
        """
        Check if session should start in daylight or night.
        If daylight, state machine will transition to day loop in session_main.
        If night, state machine will transition to night loop in session_post.
        """

        ## assign light schedule to
        self.daylight = utils.check_time(self.parameters['light_schedule'])

        if self.daylight:
            return "main"
        else:
            return "post"


    def session_main(self):
        """
        Inside session_pre, maintain a loop that controls *day* behavior.
        """

        while True:

            '''
            Try to open all perches. The program loops in open_all_perches
            until a valid perching has been detected.
            '''
            self.open_all_perches()
