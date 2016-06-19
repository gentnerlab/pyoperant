import logging
import traceback
import logging.handlers
import os
import sys
import socket
import datetime as dt
from pyoperant import utils, components, local, hwio, configure
from pyoperant import ComponentError, InterfaceError, EndExperiment
from pyoperant import states, subjects, queues
from pyoperant.events import events, EventLogHandler
import pyoperant.blocks as blocks_
import pyoperant.trials as trials_

logger = logging.getLogger(__name__)


def _log_except_hook(*exc_info):
    text = "".join(traceback.format_exception(*exc_info))
    logger.error("Unhandled exception: %s", text)


class BaseExp(object):
    """ Base class for an experiment. This controls most of the experiment logic
    so you only have to implement specifics for your behavior.

    Parameters
    ----------
    panel: Panel instance or string
        Instance of a panel or the name of a panel from local.py. It must
        implement all required attributes for the current experiment.
    block_queue: BlockHandler instance or a queue function or Class
        The queue for looping over blocks. If this is not defined, the
        block_queue will be used.
    subject: Subject instance
        The subject that will handle data storage. If this is not defined, one
        will be created using subject_name, filename, and datastore
        parameters. If those aren't provided, you can add a subject using the
        "set_subject" method
    conditions: list
        A list of stimulus conditions instances. These currently need to be
        defined explicitly.
    blocks: list
        A list of Block instances. If this is not provided, a single block will
        be created using the "conditions", "queue" and "queue_parameters"
        parameters.
    sleep: Sleep state instance
        Controls when the experiment is in the sleep state. If not provided,
        one will be created from the "sleep_schedule" and "poll_interval"
        parameters, if set, or can be added using the "add_sleep_schedule"
        method.
    session: Session state instance
        Controls the scheduling and running of an experimental session. If not
        provided, one will be created from the "max_trials", "session_duration",
        and "session_interval" parameters. The session duration/interval and
        trial limit can be set using the "set_session_time_limits" and
        "set_session_trial_limit" methods.
    idle: Idle state instance
        Controls how the experiment behaves while idling. If not provided, one
        will be created from the "poll_interval" parameter.
    name: string
        Name of this experiment
    description: string
        Long description of this experiment
    debug: bool
        Flag for debugging, switches the logging stream handler between to DEBUG level
    num_sessions: int
        The number of sessions to run.
    filetime_fmt: string
        The format for the time string in the name of the file.
    experiment_path: string
        Path to the experiment data directory. Provides the default location to store subject data.
    log_handlers: list of dictionaries
        Currently supported handler types are file and email (in addition to
        the default stream handler)
    sleep_schedule: string or tuple
        The sleep schedule for the experiment. either 'night' or a tuple of
        (starttime,endtime) in (hhmm,hhmm) form defining the time interval for
        the experiment to sleep.
    max_trials: int
        The maximum number of trials for each experimental session. Can also be
        set using the "set_session_trial_limit" method.
    session_duration: int
        The maximum duration, in minutes, of each experimental session. Can also
        be set using the "set_session_time_limits" method.
    session_interval: int
        The minimum intersession interval in minutes. Can also be set using the
        "set_session_time_limits" method.
    poll_interval: int
        The number of seconds to wait between successive checks regarding when
        to start/stop sleeping or start an experimental session.
    queue: a queue name, function, or Class
        The queue to use to loop over stimulus conditions within a block.
    queue_parameters: dictionary
        Any additional parameters to provide the "queue".
    reinforcement: a reinforcement name or Class
        The type of reinforcement to use for a block
    subject_name: string
        The name of the subject performing the experiment
    datastore: string
        The type of file to store data in (e.g. "csv")
    filename: string
        The name of the file in which to store data. If the full path is not
        provided, it will be in the path given by the "experiment_path"
        parameter.

    All other key-value pairs get placed into the parameters attribute

    Methods
    -------
    run() -- runs the experiment

    Required Panel Attributes
    -------------------------
    sleep - Puts the panel to sleep
    reset - Sets the panel back to a nice initial state
    ready - Prepares the panel to run the behavior (e.g. turn on the
            response_port light and put the feeder down)
    idle - Sets the panel into an idle state for when the experiment is not
           running

    Fields To Save
    --------------
    session - The index of the current session
    index - The index of the current trial
    time - The start time of the trial
    """

    # All panels should have these methods, but it's best to include them in every experiment just in case
    req_panel_attr = ["sleep",
                      "reset",
                      "idle",
                      "ready"]

    # All experiments should store at least these fields but probably more
    fields_to_save = ['session',
                      'index',
                      'time']

    def __init__(self,
                 panel,
                 block_queue=queues.block_queue,
                 subject=None,
                 conditions=None,
                 blocks=None,
                 sleep=None,
                 session=None,
                 idle=None,
                 name='Experiment',
                 description='A pyoperant experiment',
                 debug=False,
                 num_sessions=1,
                 filetime_fmt='%Y%m%d%H%M%S',
                 experiment_path='',
                 log_handlers=None,
                 sleep_schedule=None,
                 max_trials=None,
                 session_duration=None,
                 session_interval=None,
                 poll_interval=60,
                 queue=queues.random_queue,
                 queue_parameters=None,
                 reinforcement=None,
                 subject_name=None,
                 datastore="csv",
                 filename=None,
                 *args, **kwargs):

        super(BaseExp, self).__init__()

        # Initialize the experiment directory to start storing data
        if not os.path.exists(experiment_path):
            logger.debug("Creating %s" % experiment_path)
            os.makedirs(experiment_path)
        self.experiment_path = experiment_path

        # Set up logging
        if log_handlers is None:
            log_handlers = dict()

        # Stream handler is the console and takes level as it's only config
        stream_handler = log_handlers.pop("stream", dict())
        # Initialize the logging
        self.configure_logging(debug=debug, **stream_handler)

        # Event logging takes filename, format, and component as arguments
        event_handler = log_handlers.pop("event", dict())
        self.configure_event_logging(**event_handler)

        # File handler has keywords of filename and level
        if "file" in log_handlers:
            self.add_file_handler(**log_handlers["file"])

        # Email handler has keywords of mailhost, toaddrs, fromaddr, subject, credentials, secure, and level
        if "email" in log_handlers:
            self.add_email_handler(**log_handlers["email"])

        # Experiment descriptors
        self.name = name
        self.description = description
        self.timestamp = dt.datetime.now().strftime(filetime_fmt)
        logger.debug("Initializing experiment: %s" % self.name)
        logger.debug(self.description)
        logger.debug("This experiment will store the following trial " +
                     "parameters:\n%s" % ", ".join(self.fields_to_save))

        # Initialize the panel
        logger.debug("Panel must support these attributes: " +
                     "%s" % ", ".join(self.req_panel_attr))
        if isinstance(panel, str) and hasattr(local, panel):
            panel = getattr(local, panel)
        self.panel = panel
        # Verify the panel can support this behavior
        self.check_panel_attributes(panel)
        logger.debug('Initialized panel: %s' % self.panel.__class__.__name__)

        # Initialize the subject
        if subject is not None:
            subject = subject_name
        logger.info("Preparing subject and data storage")
        self.set_subject(subject_name, filename, datastore)
        logger.debug("Data will be stored at %s" % self.subject.filename)

        # Initialize blocks and block_queue
        logger.debug("Preparing blocks and block_queue")
        if isinstance(block_queue, blocks_.BlockHandler):
            self.block_queue = block_queue
            self.blocks = block_queue.blocks
        elif blocks is not None:
            if isinstance(blocks, blocks_.Block):
                blocks = [blocks]
            self.blocks = blocks
            logger.debug("Creating block_queue from blocks")
            self.block_queue = blocks_.BlockHandler(blocks, queue=block_queue)
        elif conditions is not None:
            logger.debug("Creating block_queue from stimulus conditions")
            if queue_parameters is None:
                queue_parameters = dict()
            self.blocks = [blocks_.Block(conditions,
                                         queue=queue,
                                         reinforcement=reinforcement,
                                         **queue_parameters)]
            self.block_queue = blocks_.BlockHandler(self.blocks,
                                                    queue=block_queue)
        else:
            raise ValueError("Could not create blocks for the experiment. " +
                             "Please provide conditions, blocks, or block_queue")

        # Initialize the states
        if sleep is not None:
            self.add_sleep_schedule(sleep)
        elif sleep_schedule is not None:
            self.add_sleep_schedule(sleep_schedule,
                                    poll_interval=poll_interval)
        else:
            self._sleep = None

        if session is None:
            session = states.Session()
        self.session = session
        self.session.experiment = self
        if max_trials is not None:
            self.set_session_trial_limit(max_trials)
        if session_duration is not None or session_interval is not None:
            self.set_session_time_limits(duration=session_duration,
                                         interval=session_interval)
        self.num_sessions = num_sessions

        if idle is None:
            idle = states.Idle(poll_interval=poll_interval)
        self._idle = idle
        self._idle.experiment = self

        self.parameters = kwargs

        # Get ready to run!
        self.session_id = 0
        self.finished = False

    def set_subject(self, subject, filename=None, datastore="csv"):
        """ Creates a subject for the current experiment.

        Parameters
        ----------
        subject: string or instance of Subject class
            The name of the subject or an already created Subject instance to use.
        filename: string
            The path to the file in which to store data.
        datastore: string
            The type of file in which to store data (e.g. "csv")
        """
        if subject is None:
            raise ValueError("Subject has not yet been defined. " +
                             "Provide a value to either the subject " +
                             "or subject_name parameter for the behavior.")
        if not isinstance(subject, subjects.Subject):
            subject = subjects.Subject(subject)

        if subject.datastore is None:
            if filename is None:
                filename = "%s_trialdata_%s.%s" % (subject.name,
                                                   self.timestamp,
                                                   datastore)
            # Add directory if filename is not a full path
            if len(os.path.split(filename)[0]) == 0:
                filename = os.path.join(self.experiment_path,
                                        filename)
            subject.filename = filename
            subject.create_datastore(self.fields_to_save)

        logger.debug("Creating subject")
        self.subject = subject

    def add_sleep_schedule(self, time_period, poll_interval=60):
        """ Add a sleep schedule between start and end times

        Parameters
        ----------
        time_period: string, tuple, or instance of Sleep state
            Can be a string of "night", a tuple of ("HH:MM", "HH:MM"), or a
            pre-created instance of Sleep state
        poll_interval: int
            The number of seconds to wait between successive checks regarding
            when to start/stop sleeping
        """

        if isinstance(start, states.Sleep):
            self._sleep = start
        else:
            self._sleep = states.Sleep(time_period=time_period,
                                       poll_interval=poll_interval)
        logger.debug("Adding sleep state")
        self._sleep.experiment = self

    # Logging configure methods
    def configure_logging(self, level=logging.INFO, debug=False):
        """ Configures the basic logging for the experiment. This creates a handler for logging to the console, sets it at the appropriate level (info by default unless overridden in the config file or by the debug flag) and creates the default formatting for log messages.
        """

        if debug is True:
            self.log_level = logging.DEBUG
        else:
            self.log_level = level

        sys.excepthook = _log_except_hook  # send uncaught exceptions to file

        logging.basicConfig(
            level=self.log_level,
            format='"%(asctime)s","%(levelname)s","%(message)s"'
            )

        # Make sure that the stream handler has the requested log level.
        root_logger = logging.getLogger()
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setLevel(self.log_level)

    def configure_event_logging(self, filename="events.log", format=None,
                                component=None):
        """ Sets up the logging of component events to a file. See events.py for
        more details.

        Parameters
        ----------
        filename
        format
        component

        TODO: If one already exists, don't create another!

        """

        # Add directory if filename is not a full path
        if len(os.path.split(filename)[0]) == 0:
            filename = os.path.join(self.experiment_path, filename)
        log_handler = EventLogHandler(filename=filename, format=format,
                                      component=component)
        events.add_handler(log_handler)

    def add_file_handler(self, filename="experiment.log",
                         format='"%(asctime)s","%(levelname)s","%(message)s"',
                         level=logging.INFO):
        """ Add a file handler to the root logger

        Parameters
        ----------
        filename: string
            name of the experiment log file
        format: string
            format for log messages
        level: logging level
            defaults to logging.INFO, but could be set to logging.DEBUG
        """

        # Add directory if filename is not a full path
        if len(os.path.split(filename)[0]) == 0:
            filename = os.path.join(self.experiment_path, filename)

        file_handler = logging.FileHandler(filename)
        file_handler.setLevel(level)
        file_handler.setFormatter(logging.Formatter(format))

        # Make sure the root logger's level is not too high
        root_logger = logging.getLogger()
        if root_logger.level > level:
            root_logger.setLevel(level)
        root_logger.addHandler(file_handler)
        logger.debug("File handler added to %s with level %d" % (filename,
                                                                 level))

    def add_email_handler(self, toaddrs, mailhost="localhost",
                          fromaddr="Pyoperant <experiment@pyoperant.com",
                          subject="Pyoperant notice", level=logging.ERROR,
                          **kwargs):
        """Add an email handler to the root logger using configurations from the
        config file.

        Parameters
        ----------
        toaddrs: list
            A list of email addresses to send notifications
        mailhost: string
            The mail server
        fromaddr: string
            The from address for the email
        subject: string
            Subject of the email
        level: logging level
            The level of log messages that should send an email. Probably want
            logging.ERROR or something similarly high
        """
        email_handler = logging.handlers.SMTPHandler(toaddrs=toaddrs,
                                                     mailhost=mailhost,
                                                     fromaddr=fromaddr,
                                                     subject=subject,
                                                     **kwargs)
        email_handler.setLevel(level)

        formatter = logging.Formatter('%(levelname)s at %(asctime)s:\n%(message)s')
        email_handler.setFormatter(formatter)
        root_logger = logging.getLogger()
        # Make sure the root logger's level is not too high
        if root_logger.level > level:
            root_logger.setLevel(level)
        root_logger.addHandler(email_handler)
        logger.debug("Email handler added to %s with level %d" % (",".join(email_handler.toaddrs), level))

    # Scheduling methods
    def check_sleep_schedule(self):
        """returns true if the experiment should be sleeping"""
        if self._sleep is None:
            return False

        to_sleep = self._sleep.check()
        logger.debug("Checking sleep schedule: %s" % to_sleep)
        return to_sleep

    def check_session_schedule(self):
        """returns True if the subject should be running sessions"""

        return self.session.check()

    def set_session_time_limits(self, duration=None, interval=None):
        """ Sets the duration for the current or next session

        Parameters
        ----------
        duration: int
            Time, in minutes, that the session should last
        interval: int
            Time, in minutes, between consecutive sessions
        """
        scheduler = states.TimeScheduler(duration=duration, interval=interval)
        self.session.schedulers.append(scheduler)

    def set_session_trial_limit(self, max_trials):
        """ Sets the number of trials for the current or upcoming session

        Parameters
        ----------
        max_trials: int
            Maximum number of trials that should be run
        """

        scheduler = states.CountScheduler(max_trials=max_trials)
        self.session.schedulers.append(scheduler)

    def end(self):
        """ Finish the experiment and put the panel to sleep """

        # Close the event handlers because they are in separate threads
        events.close_handlers()
        self.finished = True
        self.panel.sleep()

    def shape(self):
        """
        This will house a method to run shaping.
        """

        pass

    @classmethod
    def check_panel_attributes(cls, panel, raise_on_fail=True):
        """ Check if the panel has all required attributes

        Parameters
        ----------
        panel: panel instance
            The panel to check
        raise_on_fail: bool
            True causes an AttributeError to be raised if the panel doesn't contain all required attributes

        Returns
        -------
        True if panel has all required attributes, False otherwise
        """

        missing_attrs = list()
        for attr in cls.req_panel_attr:
            logger.debug("Checking that panel has attribute %s" % attr)
            if not hasattr(panel, attr):
                missing_attrs.append(attr)

        if len(missing_attrs) > 0:
            logger.critical("Panel is missing attributes: %s" % ", ".join(missing_attrs))
            if raise_on_fail:
                raise AttributeError("Panel is missing attributes: %s" % ", ".join(missing_attrs))
            return False

        else:
            return True

    def run(self):
        """ Run shaping and then star the experiment """

        logger.info("Preparing to run experiment %s" % self.name)
        logger.debug("Resetting panel")
        self.panel.reset()

        # This still seems very odd to me.
        logger.debug("Running shaping")
        self.shape()

        # Run until self.end() is called
        while self.finished == False:
            # The idle state checks whether it's time to sleep or time to start the session, so start in that state.
            self._idle.start()

    ## Session Flow
    def session_pre(self):
        """ Runs before the session starts. Initializes the block queue and
        records the session start time.
        """
        logger.debug("Beginning session")

        # Reinitialize the block queue
        self.block_queue.reset()
        self.session_id += 1
        self.session_start_time = dt.datetime.now()
        self.panel.ready()

    def session_main(self):
        """ Runs the session by looping over the block queue and then running
        each trial in each block.
        """

        for self.this_block in self.block_queue:
            self.this_block.experiment = self
            logger.info("Beginning block #%d" % self.this_block.index)
            for trial in self.this_block:
                trial.run()

    def session_post(self):
        """ Closes out the sessions
        """

        self.panel.idle()
        self.session_end_time = dt.datetime.now()
        logger.info("Finishing session %d at %s" % (self.session_id, self.session_end_time.ctime()))
        if self.session_id >= self.num_sessions:
            logger.info("Finished all sessions.")
            self.end()

    # Defining the different trial states. If any of these are not needed by the behavior, just don't define them in your subclass
    def trial_pre(self):
        pass

    def stimulus_pre(self):
        pass

    def stimulus_main(self):
        pass

    def stimulus_post(self):
        pass

    def response_pre(self):
        pass

    def response_main(self):
        pass

    def response_post(self):
        pass

    def reward_pre(self):
        pass

    def reward_main(self):
        pass

    def reward_post(self):
        pass

    def punish_pre(self):
        pass

    def punish_main(self):
        pass

    def punish_post(self):
        pass

    def trial_post(self):
        pass

    # gentner-lab specific functions
    def init_summary(self):
        """ initializes an empty summary dictionary """
        self.summary = {'trials': 0,
                        'feeds': 0,
                        'hopper_failures': 0,
                        'hopper_wont_go_down': 0,
                        'hopper_already_up': 0,
                        'responses_during_feed': 0,
                        'responses': 0,
                        'last_trial_time': [],
                        }

    def write_summary(self):
        """ takes in a summary dictionary and options and writes to the bird's summaryDAT"""
        summary_file = os.path.join(self.parameters['experiment_path'],self.parameters['subject'][1:]+'.summaryDAT')
        with open(summary_file,'wb') as f:
            f.write("Trials this session: %s\n" % self.summary['trials'])
            f.write("Last trial run @: %s\n" % self.summary['last_trial_time'])
            f.write("Feeder ops today: %i\n" % self.summary['feeds'])
            f.write("Hopper failures today: %i\n" % self.summary['hopper_failures'])
            f.write("Hopper won't go down failures today: %i\n" % self.summary['hopper_wont_go_down'])
            f.write("Hopper already up failures today: %i\n" % self.summary['hopper_already_up'])
            f.write("Responses during feed: %i\n" % self.summary['responses_during_feed'])
            f.write("Rf'd responses: %i\n" % self.summary['responses'])

    def log_error_callback(self, err):
        if err.__class__ is InterfaceError or err.__class__ is ComponentError:
            logger.critical(str(err))
