#!/usr/bin/env python
import os
import sys
import logging
import csv
import datetime as dt
import random
import numpy as np
from pyoperant.behavior import base
from pyoperant.errors import EndSession
from pyoperant import states, trials, blocks
from pyoperant import components, utils, reinf, queues, configure, stimuli, subjects

logger = logging.getLogger(__name__)


class RewardedCondition(stimuli.StimulusConditionWav):
    """ Rewarded stimuli are rewarded if the subject does *not* respond (i.e.
    No-Go stimuli).
    """
    def __init__(self, file_path="", recursive=False):
        super(RewardedCondition, self).__init__(name="Rewarded",
                                                response=False,
                                                is_rewarded=True,
                                                is_punished=False,
                                                file_path=file_path,
                                                recursive=recursive)


class UnrewardedCondition(stimuli.StimulusConditionWav):
    """ Unrewarded stimuli are not consequated and should be pecked through
    (i.e. Go stimuli)
    """
    def __init__(self, file_path="", recursive=False):

        super(UnrewardedCondition, self).__init__(name="Unrewarded",
                                                  response=True,
                                                  is_rewarded=False,
                                                  is_punished=False,
                                                  file_path=file_path,
                                                  recursive=recursive)


class GoNoGoInterrupt(base.BaseExp):
    """A go no-go interruption experiment

    Additional Parameters
    ---------------------
    reward_value: int
        The value to pass as a reward (e.g. feed duration)

    For all other parameters, see pyoperant.behavior.base.BaseExp

    Required Panel Attributes
    -------------------------
    sleep - Puts the panel to sleep
    reset - Sets the panel back to a nice initial state
    ready - Prepares the panel to run the behavior (e.g. turn on the
            response_port light and put the feeder down)
    idle - Sets the panel into an idle state for when the experiment is not
           running
    reward - Method for supplying a reward to the subject. Should take a reward
             value as an argument
    response_port - The input through which the subject responds
    speaker - A speaker for sound output

    Fields To Save
    --------------
    session - The index of the current session
    index - The index of the current trial
    time - The start time of the trial
    stimulus_name - The filename of the stimulus
    condition_name - The condition of the stimulus
    response - Whether or not there was a response
    correct - Whether the response was correct
    rt - If there was a response, the time from sound playback
    max_wait - The duration of the sound and thus maximum rt to be counted as a
               response.
    """

    req_panel_attr = ["sleep",
                      "reset",
                      "ready",
                      "idle",
                      "reward",
                      "response_port",
                      "speaker"]

    fields_to_save = ['session',
                      'index',
                      'time',
                      'stimulus_name',
                      'condition_name',
                      'response',
                      'correct',
                      'rt',
                      'reward',
                      'max_wait',
                      ]

    def __init__(self, reward_value=12, *args, **kwargs):

        super(GoNoGoInterrupt,  self).__init__(*args, **kwargs)
        self.start_immediately = False
        self.reward_value = reward_value

    def trial_pre(self):
        """ Initialize the trial and, if necessary, wait for a peck before
        starting stimulus playback.
        """

        logger.debug("Starting trial #%d" % self.this_trial.index)
        stimulus = self.this_trial.stimulus
        condition = self.this_trial.condition.name
        self.this_trial.annotate(stimulus_name=stimulus.file_origin,
                                 condition_name=condition,
                                 max_wait=stimulus.duration)

        if not self.start_immediately:
            logger.debug("Begin polling for a response")
            self.panel.response_port.poll()

    def stimulus_main(self):
        """ Queue the stimulus and play it back """

        logger.info("Trial %d - %s - %s - %s" % (
                                     self.this_trial.index,
                                     self.this_trial.time.strftime("%H:%M:%S"),
                                     self.this_trial.condition.name,
                                     self.this_trial.stimulus.name))
        self.panel.speaker.queue(self.this_trial.stimulus.file_origin)
        self.this_trial.annotate(stimulus_time=dt.datetime.now())
        self.panel.speaker.play()

    def response_main(self):
        """ Poll for an interruption for the duration of the stimulus. """

        self.this_trial.response_time = self.panel.response_port.poll(self.this_trial.stimulus.duration)
        logger.debug("Received peck or timeout. Stopping playback")

        self.panel.speaker.stop()
        logger.debug("Playback stopped")

        if self.this_trial.response_time is None:
            logger.debug("No peck was received")
            self.this_trial.response = False
            self.start_immediately = False  # Next trial will poll for a response before beginning
            self.this_trial.rt = np.nan
        else:
            logger.debug("Peck was received")
            self.this_trial.response = True
            self.start_immediately = True  # Next trial will begin immediately
            self.this_trial.rt = self.this_trial.response_time - \
                                 self.this_trial.annotations["stimulus_time"]

    def reward_main(self):
        """ Reward a correct non-interruption """

        value = self.parameters.get('reward_value', 12)
        logger.info("Supplying reward for %3.2f seconds" % value)
        reward_event = self.panel.reward(value=value)
        if isinstance(reward_event, dt.datetime): # There was a response during the reward period
            self.start_immediately = True


if __name__ == "__main__":

    # Load config file
    config_file = "/path/to/config"
    if config_file.lower().endswith(".json"):
        parameters = configure.ConfigureJSON.load(config_file)
    elif config_file.lower().endswith(".yaml"):
        parameters = configure.ConfigureYAML.load(config_file)

    # Create experiment object
    exp = GoNoGoInterrupt(**parameters)
    exp.run()
