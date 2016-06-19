import logging
import datetime as dt
import numpy as np
from pyoperant.behavior import base
from pyoperant.errors import EndSession
from pyoperant import utils, stimuli, queues
from pyoperant import blocks as blocks_

logger = logging.getLogger(__name__)


class SimpleStimulusPlayback(base.BaseExp):
    """ Simply plays back stimuli with a random or fixed intertrial interval

    Additional Parameters
    ---------------------
    intertrial_interval: float or 2-element list
        If the value is a float, then the intertrial interval is fixed. If it is a list, then the interval is taken as from a uniform random distribution between the first and second elements.
    stimulus_directory: string or list
        Full path to the stimulus directory. If given, a stimulus condition will be created and passed in to BaseExp. Can also be a list of dictionaries with name and directory keys.

    For all other parameters, see pyoperant.behavior.base.BaseExp

    Required Panel Attributes
    -------------------------
    sleep - Puts the panel to sleep
    reset - Sets the panel back to a nice initial state
    ready - Prepares the panel to run the behavior (e.g. turn on the
            response_port light and put the feeder down)
    idle - Sets the panel into an idle state for when the experiment is not
           running
    speaker - A speaker for sound output

    Fields To Save
    --------------
    session - The index of the current session
    index - The index of the current trial
    time - The start time of the trial
    stimulus_name - The filename of the stimulus
    intertrial_interval - The intertrial interval preceding the trial
    """

    req_panel_attr = ["sleep",
                      "reset",
                      "idle",
                      "ready",
                      "speaker"]

    fields_to_save = ['session',
                      'index',
                      'time',
                      'stimulus_name',
                      'intertrial_interval']

    def __init__(self, intertrial_interval=2.0, stimulus_directory=None,
                 queue=queues.random_queue, reinforcement=None,
                 queue_parameters=None, *args, **kwargs):

        # let's parse any stimulus directories provided
        if stimulus_directory is not None:
            # Append to any existing blocks
            blocks = kwargs.pop("blocks", list())

            if queue_parameters is None:
                queue_parameters = dict()

            # If a path is given, convert it to the list of dictionaries
            if isinstance(stimulus_directory, str):
                stimulus_directory = [dict(name="Playback",
                                           directory=stimulus_directory)]

            for ii, stim_dict in enumerate(stimulus_directory):
                # Default name is Playback#
                name = stim_dict.get("name", "Playback%d" % ii)
                directory = stim_dict["directory"]
                # Create a stimulus condition for this directory
                condition = stimuli.StimulusConditionWav(name=name,
                                                         file_path=directory,
                                                         is_rewarded=False,
                                                         is_punished=False,
                                                         response=False)

                # Create a block for this condition
                block = blocks_.Block([condition],
                                      queue=queue,
                                      reinforcement=reinforcement,
                                      **queue_parameters)
                blocks.append(block)

        self.intertrial_interval = intertrial_interval

        super(SimpleStimulusPlayback, self).__init__(blocks=blocks,
                                                     *args, **kwargs)


    def trial_pre(self):
        """ Store data that is specific to this experiment, and compute a wait time for an intertrial interval
        """

        stimulus = self.this_trial.stimulus.file_origin
        if isinstance(self.intertrial_interval, (list, tuple)):
            iti = np.random.uniform(*self.intertrial_interval)
        else:
            iti = self.intertrial_interval

        logger.debug("Waiting for %1.3f seconds" % iti)
        self.this_trial.annotate(stimulus_name=stimulus,
                                 intertrial_interval=iti)
        utils.wait(iti)

    def stimulus_main(self):
        """ Queue the sound and play it """

        logger.info("Trial %d - %s - %s" % (
                                     self.this_trial.index,
                                     self.this_trial.time.strftime("%H:%M:%S"),
                                     self.this_trial.stimulus.name
                                     ))

        self.panel.speaker.queue(self.this_trial.stimulus.file_origin)
        self.panel.speaker.play()

        # Wait for stimulus to finish
        utils.wait(self.this_trial.stimulus.duration)

        # Stop the sound
        self.panel.speaker.stop()
