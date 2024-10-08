import os
import csv
import copy
import datetime as dt
from pyoperant.behavior import base, shape
from pyoperant.errors import EndSession, EndBlock
from pyoperant import components, utils, reinf, queues

import serial
import random

class Visit(utils.Event):
    """docstring for Visit, a variant of trial for place preference paradigm """
    def __init__(self,
                 class_=None,
                 *args, **kwargs):
        super(Visit, self).__init__(*args, **kwargs)
        self.label = 'visit'
        self.perch_strt = None
        self.perch_end = None
        self.perch_loc = None
        self.perch_dur = None
        self.valid = None
        self.class_ = class_
        self.stimuli = []
        self.events = []

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
                if self.light_switch():
                    ## exit current loop
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

    def current_perch_stim_class(self):
        """
        Look in self.parameters for the order of randomized perch orders
        depending on what day of experiment we are on
        Can be "S" for silence, "A" for category A, "B" for category B
        """

        return self.parameters['perch_sequence'][str(self.experiment_day())][self.current_perch['speaker']]

    def current_variable_ratio(self):
        """
        Look in self.parameters for current reinforcement ratio of the day
        """

        return self.parameters['perch_sequence'][str(self.experiment_day())][3] ## index 3 is always the variable ratio
    
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
            ## if current perch is no longer broken, record perch end time, give a grace period
            else:
                self.current_visit.perch_end = dt.datetime.now()
                ## if there is no grace_tokens left, immediately terminate visit
                if grace_tokens <= 0:
                    self.log.debug("Perching not valid. Out of grace tokens.")
                    return False

                ## while the current perch is unperched,
                while (self.current_perch["IR"].status() == False):
                    ## if the grace period has ended
                    grace_period = (dt.datetime.now() - self.current_visit.perch_end).total_seconds()
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
            ## if the current perch is no longer broken, record perch_end time, and give a grace period
            else:
                self.current_visit.perch_end = dt.datetime.now()
                ## if there is no grace_tokens left, immediately terminate visit
                if grace_tokens <= 0:
                    self.log.debug("Perching Unstable. Out of grace tokens.")
                    return True

                ## while the current perch is unperched,
                while (self.current_perch['IR'].status() == False):
                    ## if the grace period has ended, bird has deperched
                    grace_period = (dt.datetime.now() - self.current_visit.perch_end).total_seconds()
                    if grace_period > self.parameters['perch_grace_period']:
                        self.log.debug("Subject Deperched. Exceed grace period.")
                        return True
                    else:
                        grace_tokens = grace_tokens - 1
                        continue

    def switch_speaker(self):
        """
        Use serial communication with the connected Arduino to switch
        """
        self.log.debug("Switching speaker relay to %s" % self.current_perch['speaker'])
        self.arduino.write(str(self.current_perch['speaker'] + 1).encode('utf-8'))
    
    def reinforcement_logic(self):
        """
        Figure out if current trial should be reinforced based on
        reinforcement schedule of the day and previous reinforcement
        """

        if not self.daylight:
            self.log.info("No reinforcement at night.")
            return False

        if self.reinforcement_counter[self.current_visit.perch_loc] == None:
            ## start new reinforcement_counter
            self.log.info("Reinforcement empty at current perch. Calling in reinforcement at ratio %s." % str(self.current_variable_ratio()))
            self.reinforcement_counter[self.current_visit.perch_loc] = random.randint(1, 2*self.current_variable_ratio() - 1) - 1
            self.log.info("Reinforcement inbound in %s visits." % str(self.reinforcement_counter[self.current_visit.perch_loc]))

        ## If there are reinforcement counter is 0, reinforce
        if self.reinforcement_counter[self.current_visit.perch_loc] == 0:
            self.log.info("Reinforcement available at current perch. Reinforcing...")
            self.reinforcement_counter[self.current_visit.perch_loc] = None ## wipe reinforcement
            return True
        else:
            self.log.info("Reinforcement not available at current perch, inbound in %s visits. " % str(self.reinforcement_counter[self.current_visit.perch_loc]))
            self.reinforcement_counter[self.current_visit.perch_loc] = self.reinforcement_counter[self.current_visit.perch_loc] - 1
            return False

    def stimulus_shuffle(self):
        """
        While perched, shuffle stimuli from a library
        """

        ## decide if reinforcement should be given
        self.current_visit.reinforcement = self.reinforcement_logic()

        ## if the current class is silence, or if reinforcement is not given, don't do shit except checking for light schedule
        if (
            self.current_visit.class_ == "S" or ## silence class
            self.current_visit.reinforcement == False or ## don't reinforce
            self.daylight == False ## or night-time
            ):
            self.log.debug("Silence Perching")
            while True:
                if (self.validate_deperching() == True or self.light_switch()):
                    if self.light_switch():
                        self.current_visit.perch_end = dt.datetime.now()
                    return
                
        ## if the current class is not silence, prep and play stimuli
        else:
            self.prep_stimuli()
            self.play_stimuli()

        while True:
            ## if deperching has been detected, or light schedule expires, quit this function
            if (self.validate_deperching() == True or self.light_switch()):
                if self.light_switch:
                    self.current_visit.perch_end = dt.datetime.now()
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
                        self.log.debug("Stimuli finished and inter_stim_interval has passed. ")
                        self.stop_stimuli()
                        ## find another clip to play
                        self.prep_stimuli()
                        self.play_stimuli()       

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
        stim_file = random.sample(self.perch_playlist().items(), k = 1)[0][1]
        self.log.debug(stim_file)
        stim = utils.auditory_stim_from_wav(stim_file)

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
        self.log.debug("Stop stimuli and flush stimulus event.")
        self.panel.speaker.stop()
        self.current_visit.stimuli.append(self.stimulus_event.file_origin)
        self.current_visit.events.append(self.stimulus_event)
        self.stimulus_event = None

    def end_visit(self):
        """
        End visit and write data of current visit to csv
        """
        self.log.debug("Ending visit and record end time.")
        try:
            self.current_visit.perch_dur = (self.current_visit.perch_end - self.current_visit.perch_strt).total_seconds()
        except:
            self.current_visit.perch_dur = 0
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

        self.current_perch = {'IR': None, 'IRName': None, 'speaker': None}
        self.stimulus_event = None
        self.current_visit = None

    def check_session_schedule(self):
        """
        Check if perches should be open

        returns
        -------
        bool
            True, if sessions should be running
        """
        return utils.check_time(self.parameters['light_schedule'])
    
    def light_switch(self):
        '''
        This checks if paradigm daylight is incongruent with system time
        '''
        return self.daylight != self.check_light_schedule()

    def run(self):

        for attr in self.req_panel_attr:
            assert hasattr(self.panel,attr)
        self.panel_reset()
        self.save()
        self.init_summary()

        self.log.info('%s: running %s with parameters in %s' % (self.name,
                                                                self.__class__.__name__,
                                                                self.snapshot_f,
                                                                )
                      )

        while True: # modify to start in pre instead of idle (this script deprecates idle)
            utils.run_state_machine(
                start_in='pre',
                error_state='post',
                error_callback=self.log_error_callback,
                pre=self.session_pre,
                main=self.session_main,
                post=self.session_post
                )

    def session_pre(self):
        """
        Check if session should start in daylight or night.
        If daylight, 
        """

        self.log.info('Entering session_pre for daylight logic.')
        ## assign light schedule to
        self.daylight = self.check_light_schedule()
        self.reinforcement_counter = {'L': None, 'R': None, 'C': None} ## flush reinforcement
        self.log.info('Set paradigm to be congruent to system light. Flushing reinforcement counter. ')

        if self.daylight:
            self.log.info('Wakey wakey the sun is shining!')
            self.panel.house_light.on()
        else:
            self.log.info('Sleepy sleepy the moon is rising!')
            self.panel.house_light.off()

        return "main"

    def session_main(self):
        """
        Inside session_main, maintain a loop that controls looping behavior.
        """

        self.log.info("Entering session_main for experiment")

        while True:

            '''
            Try to open all perches. The program loops in open_all_perches until a valid perching has been detected.
            '''
            self.open_all_perches()

            ## check light switch
            if self.light_switch():
                return "pre"
            
            '''
            Once perching has been detected, switch speaker to the current perch and start stimuli shuffle.
            The program loops in stimulus_shuffle() until a valid deperching has been detected.
            '''
            if (self.current_perch['IR'] != None): ## 
                if (self.current_perch['IR'].status() == True):
                    self.switch_speaker()
                    self.stimulus_shuffle()
            '''
            Once deperched, end visit and reset
            '''
            self.end_visit()
            self.reset_perches()

            ## check if time of day is appropriate for a trial to commence
            if self.light_switch():
                return "pre"
            
    def session_post(self):
        return "pre"
