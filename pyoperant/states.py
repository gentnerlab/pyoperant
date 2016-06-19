import logging
import datetime as dt
import numpy as np
from pyoperant import (EndSession,
                       EndExperiment,
                       ComponentError,
                       InterfaceError,
                       utils)

logger = logging.getLogger(__name__)


class State(object):
    """ States provide a nice interface for running experiments and transitioning to sleep/idle phases. By implementing __enter__ and __exit__ methods, they use the "with" statement construct that allows for simple error handling (e.g. session ends, keyboard interrupts to stop an experiment, etc.)

    Parameters
    ----------
    schedulers: list of scheduler objects
        These determine whether or not the state should be running, using their check method

    Methods
    -------
    check() - Check if the state should be active according to its schedulers
    run() - Run the state (should be used within the "with" statement)
    start() - wrapper for run that includes the "with" statement
    """

    def __init__(self, experiment=None, schedulers=None):

        if schedulers is None:
            schedulers = list()
        if not isinstance(schedulers, list):
            schedulers = [schedulers]
        self.schedulers = schedulers
        self.experiment = experiment

    def check(self):
        """ Checks all of the states schedulers to see if the state should be active.

        Returns
        -------
        True if the state should be active and False otherwise.
        """

        # If any scheduler says not to run, then don't run
        for scheduler in self.schedulers:
            if not scheduler.check():
                return False

        return True

    def __enter__(self):
        """ Start all of the schedulers """

        logger.info("Entering %s state" % self.__class__.__name__)
        for scheduler in self.schedulers:
            scheduler.start()

        return self

    def __exit__(self, type_, value, traceback):
        """ Handles KeyboardInterrupt and EndExperiment exceptions to end the experiment, EndSession exceptions to end the session state, and logs all others.
        """
        logger.info("Exiting %s state" % self.__class__.__name__)

        # Stop the schedulers
        for scheduler in self.schedulers:
            scheduler.stop()

        # Handle expected exceptions
        if type_ in [KeyboardInterrupt, EndExperiment]:
            logger.info("Finishing experiment")
            self.experiment.end()
            return True
        elif type_ is EndSession:
            logger.info("Session has ended")
            return True

        # Log all other exceptions and raise them
        if isinstance(value, Exception):
            if type_ in [InterfaceError, ComponentError]:
                logger.critical("There was a critical error in communicating with the hardware!")
            logger.critical(repr(value))

        return False

    def run(self):

        pass

    def start(self):
        """ Implements the "with" context for this state """

        with self as state:
            state.run()


class Session(State):
    """ Session state for running an experiment. Should be used with the "with" statement (see Examples).

    Parameters
    ----------
    schedulers: list of scheduler objects
        These determine whether or not the state should be running, using their check method
    experiment: an instance of a Behavior class
        The experiment whose session methods should be run.

    Methods
    -------
    check() - Check if the state should be active according to its schedulers
    run() - Run the experiment's session_main method
    start() - wrapper for run that includes the "with" statement
    update() - Update schedulers at the end of the trial

    Examples
    --------
    with Session(experiment=experiment) as state: # Runs experiment.session_pre
        state.run() # Runs experiment.session_main
    # Exiting with statement runs experiment.session_post

    # "with" context is also implemented in the start() method
    state = Session(experiment=experiment)
    state.start()
    """

    def __enter__(self):

        self.experiment.session_pre()
        for scheduler in self.schedulers:
            scheduler.start()

        return self

    def run(self):
        """ Runs session main """

        self.experiment.session_main()

    def __exit__(self, type_, value, traceback):

        self.experiment.session_post()

        return super(Session, self).__exit__(type_, value, traceback)

    def update(self):
        """ Updates all schedulers with information on the current trial """

        if hasattr(self.experiment, "this_trial"):
            for scheduler in self.schedulers:
                scheduler.update(self.experiment.this_trial)


class Idle(State):
    """ A simple idle state.

    Parameters
    ----------
    experiment: an instance of a Behavior class
        The experiment whose session methods should be run.
    poll_interval: int
        The interval, in seconds, at which other states should be checked to run

    Methods
    -------
    run() - Run the experiment's session_main method
    """
    def __init__(self, experiment=None, poll_interval=60):

        super(Idle, self).__init__(experiment=experiment,
                                   schedulers=None)
        self.poll_interval = poll_interval

    def run(self):
        """ Checks if the experiment should be sleeping or running a session and kicks off those states. """

        while True:
            if self.experiment.check_sleep_schedule():
                return self.experiment._sleep.start()
            elif self.experiment.check_session_schedule():
                return self.experiment.session.start()
            else:
                logger.debug("idling...")
                utils.wait(self.poll_interval)


class Sleep(State):
    """ A panel sleep state. Turns off all outputs, checking every so often if it should wake up

    Parameters
    ----------
    experiment: an instance of a Behavior class
        The experiment whose session methods should be run.
    schedulers: an instance of TimeOfDayScheduler
        The time of day scheduler to follow for when to sleep.
    poll_interval: int
        The interval, in seconds, at which other states should be checked to run
    time_period: string or tuple
        Either "night" or a tuple of "HH:MM" start and end times. Only used if scheduler is not provided.

    Methods
    -------
    run() - Run the experiment's session_main method
    """
    def __init__(self, experiment=None, schedulers=None, poll_interval=60,
                 time_period="night"):

        if schedulers is None:
            schedulers = TimeOfDayScheduler(time_period)
        self.poll_interval = poll_interval

        super(Sleep, self).__init__(experiment=experiment,
                                    schedulers=schedulers)

    def run(self):
        """ Checks every poll interval whether the panel should be sleeping and puts it to sleep """

        while True:
            logger.debug("sleeping")
            self.experiment.panel.sleep()
            utils.wait(self.poll_interval)
            if not self.check():
                break
        self.experiment.panel.wake()


class BaseScheduler(object):
    """ Implements a base class for scheduling states

    Summary
    -------
    Schedulers allow the state to be started and stopped based on certain critera. For instance, you can start the sleep state when the sun sets, or stop and session state after 100 trials.

    Methods
    -------
    check() - Checks whether the state should be active
    start() - Run when the state starts to initialize any variables
    stop() - Run when the state finishes to close out any variables
    update(trial) - Run after each trial to update the scheduler if necessary
    """

    def __init__(self):

        pass

    def start(self):

        pass

    def stop(self):

        pass

    def update(self, trial):

        pass

    def check(self):
        """ This should really be implemented by the subclass """

        raise NotImplementedError("Scheduler %s does not have a check method" % self.__class__.__name__)


class TimeOfDayScheduler(BaseScheduler):
    """ Schedule a state to start and stop depending on the time of day

    Parameters
    ----------
    time_periods: string or list
        The time periods in which this schedule should be active. The value of "sun" can be passed to use the current day-night schedule. Otherwise, pass a list of tuples (start, end) (e.g. [("5:00", "17:00")] for 5am to 5pm)

    Methods
    -------
    check() - Returns True if the state should be active according to this schedule
    """

    def __init__(self, time_periods="sun"):

        # Any other sanitizations?
        if isinstance(time_periods, tuple):
            time_periods = [time_periods]
        self.time_periods = time_periods

    def check(self):
        """ Returns True if the state should be active according to this schedule
        """

        return utils.check_time(self.time_periods)


class TimeScheduler(BaseScheduler):
    """ Schedules a state to start and stop based on how long the state has been active and how long since the state was previously active.

    Parameters
    ----------
    duration: int
        The duration, in minutes, that the state should be active
    interval: int
        The time since the state was last active before it should become active again.

    Methods
    -------
    start() - Stores the start time of the current state
    stop() - Stores the end time of the current state
    check() - Returns True if the state should activate
    """
    def __init__(self, duration=None, interval=None):

        self.duration = duration
        self.interval = interval

        self.start_time = None
        self.stop_time = None

    def start(self):
        """ Stores the start time of the current state """

        self.start_time = dt.datetime.now()
        self.stop_time = None

    def stop(self):
        """ Stores the end time of the current state """

        self.stop_time = dt.datetime.now()
        self.start_time = None

    def check(self):
        """ Checks if the current time is greater than `duration` minutes after start time or `interval` minutes after stop time """

        current_time = dt.datetime.now()
        # If start_time is None, the state is not active. Should it be?
        if self.start_time is None:
            # No interval specified, always start
            if self.interval is None:
                return True

            # The state hasn't activated yet, always start
            if self.stop_time is None:
                return True

            # Has it been greater than interval minutes since the last time?
            time_since = (current_time - self.stop_time).total_seconds() / 60.
            if time_since < self.interval:
                return False

        # If stop_time is None, the state is currently active. Should it stop?
        if self.stop_time is None:
            # No duration specified, so do not stop
            if self.duration is None:
                return True

            # Has the state been active for long enough?
            time_since = (current_time - self.start_time).total_seconds() / 60.
            if time_since >= self.duration:
                return False

        return True


class CountScheduler(BaseScheduler):
    """ Schedules a state stop after a certain number of trials.

    Parameters
    ----------
    max_trials: int
        The maximum number of trials

    Methods
    -------
    check() - Returns True if the state has not yet reached max_trials

    TODO: This could be expanded to include things like total number of rewards or correct responses.
    """
    def __init__(self, max_trials=None):

        self.max_trials = max_trials
        self.trial_index = 0

    def check(self):
        """ Returns True if current trial index is less than max_trials """

        if self.max_trials is None:
            return True

        return self.trial_index < self.max_trials

    def stop(self):
        """ Resets the trial index since the session is over """

        self.trial_index = 0

    def update(self, trial):
        """ Updates the current trial index """

        self.trial_index = trial.index


available_states = {"idle": Idle,
                    "session": Session,
                    "sleep": Sleep}

available_schedulers = {"day": TimeOfDayScheduler,
                        "timeofday": TimeOfDayScheduler,
                        "time": TimeScheduler}
