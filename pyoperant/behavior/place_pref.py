import os
import csv
import copy
import datetime as dt
from pyoperant.behavior import base, shape
from pyoperant.errors import EndSession, EndBlock
from pyoperant import components, utils, reinf, queues

import serial
import random

class PlacePrefExp(base.BaseExp):
    '''
    A place preference experiment.

    In this paradigm, a bird is released into a cage with three nestbox perches.
    The logic of this experiment is that when a bird lands on a perch for
    sufficiently long enough, a trial will start and the stimulus will start
    playing from a library, shuffling through the library as the bird continues
    to perch. When the bird leaves the perch, the song will stop.
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
        super(PlacePrefExp, self).__init__(*args, **kwargs)

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
            'events'
        ]

        if 'add_fields_to_save' in self.parameters.keys():
            self.fields_to_save += self.parameters['add_fields_to_save']

        self.exp_strt_date = dt.date(
            year = self.parameters['experiment_start_year'],
            month = self.parameters['experiment_start_month'],
            day = self.parameters['experiment_start_day']
        )

        self.current_perch = {'IR': None, 'speaker': None}
        self.current_visit = None
        self.stimulus_event = None

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

            ## check if time of day is appropriate for a trial to commence
            if self.check_session_schedule() == False:
                raise EndSession

            ## for each iteration, check for perching behavior.
            left_perched = self.panel.left.status()
            center_perched = self.panel.center.status()
            right_perched = self.panel.right.status()

            if left_perched:
                self.current_perch['IR'] = self.panel.left
                self.current_perch['speaker'] = 0
                break
            if center_perched:
                self.current_perch['IR'] = self.panel.center
                self.current_perch['speaker'] = 1
                break
            if right_perched:
                self.current_perch['IR'] = self.panel.right
                self.current_perch['speaker'] = 2
                break

        ## Record time of break
        self.log.debug("Beam-break sensed on %s" % (self.current_perch))
        self.current_visit = utils.Visit()
        self.current_visit.perch_strt = dt.datetime.now()
        self.current_visit.perch_loc = self.current_perch['IR']
        self.current_visit.class_ = self.current_perch_stim_class()

        ## if validate perching fails, reset perches and open
        if (self.validate_perching() == False):
            self.end_visit()
            self.reset_perches()
            self.open_all_perches()
        else:
            self.log.debug("Perch valid at %s" % (self.current_perch))

    def current_perch_stim_class(self):
        """
        Look in self.parameters for the order of randomized perch orders
        depending on what day of experiment we are on
        Can be "S" for silence, "A" for category A, "B" for category B
        """

        return self.parameters['perch_sequence'][str(self.experiment_day())][self.current_perch['speaker']]

    def experiment_day(self):
        """
        Figure out what day of experiment we are on.
        """
        return (dt.date.today() - self.exp_strt_date).days


    def validate_perching(self):
        """
        For any perching behavior to be valid,
        the IR needs to be broken for at least one second.
        """
        ## validate current perch
        self.log.debug("Trying to validate perch...")

        ## for each perch validation effort, the beam-break has a certain amount of graces
        ##
        grace_tokens = self.parameters['grace_num']

        while True:
            elapsed_time = (dt.datetime.now() - self.current_visit.perch_strt).total_seconds()
            ## keep asking if the current perch is still broken
            if (self.current_perch['IR'].status() == True):
                ## if elapsed time is more than a minimum perch time, perching is valid
                if elapsed_time > self.parameters['min_perch_time']:
                    return True
                ## if time is not up, continue the loop
                else:
                    continue
            ## if current perch is no longer broken, give a grace period
            else:
                ## if there is no grace_tokens left, immediately terminate visit
                if grace_tokens <= 0:
                    self.log.debug("Perching not valid. Out of grace tokens.")
                    return False

                ## set a time marker for the grace period.
                grace_onset = dt.datetime.now()

                ## while the current perch is unperched,
                while (self.current_perch["IR"].status() == False):
                    ## if the grace period has ended
                    grace_period = (dt.datetime.now() - grace_onset).total_seconds
                    if grace_period > self.parameters['perch_grace_period']:
                        self.log.debug("Perching not valid. Exceed grace period.")
                        return False
                    else:
                        grace_tokens = grace_tokens - 1
                        continue

    def validate_deperching(self):
        """
        For any deperching behavior to be valid,
        the IR needs to be unbroken for at least one second.
        """
        grace_tokens = self.parameters['grace_num']

        while True:
            ## keep asking if the current perch is still broken
            if (self.current_perch['IR'].status() == True):
                ## if the IR is still broken, no deperch
                return False
            ## if the current perch is no longer broken, give a grace period
            else:
                ## if there is no grace_tokens left, immediately terminate visit
                if grace_tokens <= 0:
                    self.log.debug("Perching Unstable. Out of grace tokens.")
                    return True

                ## set a time marker for the grace period.
                grace_onset = dt.datetime.now()

                ## while the current perch is unperched,
                while (self.current_perch['IR'].status() == False):
                    ## if the grace period has ended, bird has deperched
                    grace_period = (dt.datetime.now() - grace_onset).total_seconds
                    if grace_period > self.parameters['perch_grace_period']:
                        self.log.debug("Perching not valid. Exceed grace period.")
                        return True
                    else:
                        grace_tokens = grace_tokens - 1
                        continue



    def switch_speaker(self):
        """
        Use serial communication with the connected Arduino to switch
        """

        self.arduino.write(str(self.current_perch['speaker']).encode('utf-8'))

    def stimulus_shuffle(self):
        """
        While perched, shuffle stimuli from a library
        """

        ## if the current class is silence, don't do shit
        if self.current_visit.class_ == "S":
            self.log.debug("Silence Perching")
            pass
        ## if the current class is not silence, prep and play stimuli
        else:
            self.prep_stimuli()
            self.play_stimuli()

        while True:
            ## if deperching has been detected, quit this function
            if self.validate_deperching == True:
                self.stop_stimuli()
                return
            ## else, play audio until its length runs out,
            else:
                elapsed_time = (dt.datetime.now() - self.stimulus_event.time).total_seconds()
                if elapsed_time < self.stimulus_event.duration:
                    continue
                # when it does, give an inter_stim_interval, and recurse on the function
                else:
                    if elapsed_time < (self.stimulus_event.duration + self.parameters['inter_stim_interval']):
                        continue
                    ## when inter_stim_interval runs out, stop stimuli and go back to the stimulus_shuffle
                    else:
                        self.stop_stimuli()
                        self.stimulus_shuffle()

    def perch_playlist(self):
        """
        depending on the perch and the perch_sequence, find the correct list
        """
        if self.current_perch_stim_class() == "A":
            self.log.debug("Perch stim class A")
            return self.parameters['stims_A']
        if self.current_perch_stim_class() == "B":
            self.log.debug("Perch stim class B")
            return self.parameters['stims_B']

    def prep_stimuli(self):
        """
        Prep stimuli and generate a stimulus event
        """
        ## randomly shuffle from the current perch_playlist
        stim_file = random.sample(self.perch_playlist().items(), k = 1)[0]
        print(stim_file)
        stim = utils.auditory_stim_from_wav(stim_file)
        self.log.debug(stim_file)

        self.stimulus_event = utils.Event(
            time = dt.datetime.now(),
            duration = stim.duration,
            file_origin = stim.file_origin,
        )

        self.log.debug("Queuing stimulus %s" % stim.file_origin)
        self.panel.speaker.queue(self.stimulus_event.file_origin)

    def play_stimuli(self):
        """
        Play stimuli through current_perch speaker
        """

        self.log.debug("Playing %s" % (self.stimulus_event.file_origin))
        ## trigger speaker
        self.panel.speaker.play()

    def stop_stimuli(self):
        """
        Stop stimuli, record event, and clear out event
        """

        self.panel.speaker.stop()
        self.current_visit.stimuli.append(self.stimulus_event)
        self.stimulus_event = None

    def end_visit(self):
        """
        End visit and write data of current visit to csv
        """
        self.log.debug("Ending visit and record end time.")
        self.current_visit.perch_end = dt.datetime.now()
        self.current_visit.perch_dur = (self.current_visit.perch_end - self.current_visit.perch_strt).total_seconds()
        self.current_visit.valid = (self.current_visit.perch_dur >= self.parameters['min_perch_time'])
        self.save_visit(self.current_visit)

    def save_visit(self, visit):
        """
        write visit results to CSV
        """

        self.log.debug("Writing data to %s" % (self.data_csv))
        visit_dict = {}
        for field in self.fields_to_save:
            try:
                visit_dict[field] = getattr(visit,field)
            except AttributeError:
                visit_dict[field] = visit.annotations[field] ## it might be in annotations for some reason

            with open(self.data_csv, 'ab') as data_fh:
                visitWriter = csv.DictWriter(data_fh, fieldnames = self.fields_to_save, extrasaction = 'ignore')
                visitWriter.writerow(visit_dict)

    def reset_perches(self):
        """
        Reset perches
        """

        self.current_perch == {'IR': None, 'speaker': None}
        self.stimulus_event == None
        self.current_visit == None

    def check_session_schedule(self):
        """
        Check if perches should be open

        returns
        -------
        bool
            True, if sessions should be running
        """
        return utils.check_time(self.parameters['light_schedule'])

    def session_main(self):
        """
        Inside session_main, maintain a loop that controls paradigm behavior
        """

        while True:
            '''
            Try to open all perches. The program loops in open_all_perches
            until a valid perching has been detected.
            '''
            self.open_all_perches()

            '''
            Once perching has been detected, switch speaker to the current
            perch, and start stimuli shuffle. The program loops in stimulus_shuffle()
            until a valid deperching has been detected()
            '''
            self.switch_speaker()
            self.stimulus_shuffle()

            '''
            Once deperched, end visit and reset
            '''
            self.end_visit()
            self.reset_perches()
            ##
