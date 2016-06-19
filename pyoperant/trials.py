import logging
import datetime as dt
from pyoperant import EndSession
from pyoperant.events import events

logger = logging.getLogger(__name__)


class Trial(object):
    """ Class that implements all basic functionality of a trial

    Parameters
    ----------
    index: int
        Index of the trial
    experiment: instance of Experiment class
        The experiment of which this trial is a part
    block: instance of Block class
        The block that generated this trial
    condition: instance of StimulusCondition
        The condition for the current trial. Provides the trial with a stimulus,
        as well as reinforcement instructions

    Attributes
    ----------
    index: int
        Index of the trial
    experiment: instance of Experiment class
        The experiment of which this trial is a part
    stimulus_condition: instance of StimulusCondition
        The condition for the current trial. Provides the trial with a stimulus,
        as well as reinforcement instructions
    time: datetime
        The time the trial started
    session: int
        Index of the current session

    Methods
    -------
    run() - Runs the trial
    annotate() - Annotates the trial with key-value pairs
    """
    def __init__(self,
                 index=None,
                 experiment=None,
                 condition=None,
                 block=None,
                 *args, **kwargs):

        super(Trial, self).__init__(*args, **kwargs)

        # Object references
        self.experiment = experiment
        self.condition = condition
        self.block = block
        self.annotations = dict()

        # Trial properties
        self.index = index
        self.session = self.experiment.session_id
        self.time = None  # Set just after trial_pre

        # Likely trial details
        self.stimulus = None
        self.response = None
        self.rt = None
        self.correct = False
        self.reward = False
        self.punish = False

        # Trial event information
        self.event = dict(name="Trial",
                          action="",
                          metadata="")

    def annotate(self, **annotations):
        """ Annotate the trial with key-value pairs """

        self.annotations.update(annotations)

    def run(self):
        """ Runs the trial

        Summary
        -------
        The main structure is as follows:

        Get stimulus -> Initiate trial -> Play stimulus -> Receive response ->
        Consequate response -> Finish trial -> Save data.

        The stimulus, response and consequate stages are broken into pre, main,
        and post stages. Only use the stages you need in your experiment.
        """

        self.experiment.this_trial = self

        # Get the stimulus
        self.stimulus = self.condition.get()

        # Any pre-trial logging / computations
        self.experiment.trial_pre()

        # Emit trial event
        self.event.update(action="start", metadata=str(self.index))
        events.write(self.event)

        # Record the trial time
        self.time = dt.datetime.now()

        # Perform stimulus playback
        self.experiment.stimulus_pre()
        self.experiment.stimulus_main()
        self.experiment.stimulus_post()

        # Evaluate subject's response
        self.experiment.response_pre()
        self.experiment.response_main()
        self.experiment.response_post()

        # Consequate the response with a reward, punishment or neither
        if self.response == self.condition.response:
            self.correct = True
            if self.condition.is_rewarded and self.block.reinforcement.consequate(self):
                self.reward = True
                self.experiment.reward_pre()
                self.experiment.reward_main()
                self.experiment.reward_post()
        else:
            self.correct = False
            if self.condition.is_punished and self.block.reinforcement.consequate(self):
                self.punish = True
                self.experiment.punish_pre()
                self.experiment.punish_main()
                self.experiment.punish_post()

        # Emit trial end event
        self.event.update(action="end", metadata=str(self.index))
        events.write(self.event)

        # Finalize trial
        self.experiment.trial_post()

        # Store trial data
        self.experiment.subject.store_data(self)

        # Update session schedulers
        self.experiment.session.update()

        if self.experiment.check_session_schedule() is False:
            logger.debug("Session has run long enough. Ending")
            raise EndSession
