import logging, traceback
import os, sys, socket
import datetime as dt
from pyoperant import utils, components, local, hwio
from pyoperant import ComponentError, InterfaceError
from pyoperant.behavior import shape


try:
    import simplejson as json
except ImportError:
    import json

def _log_except_hook(*exc_info):
    text = "".join(traceback.format_exception(*exc_info))
    logging.error("Unhandled exception: %s", text)

class BaseExp(object):
    """Base class for an experiment.

    Keyword arguments:
    name -- name of this experiment
    desc -- long description of this experiment
    debug -- (bool) flag for debugging (default=False)
    light_schedule  -- the light schedule for the experiment. either 'sun' or
        a tuple of (starttime,endtime) tuples in (hhmm,hhmm) form defining
        time intervals for the lights to be on
    experiment_path -- path to the experiment
    stim_path -- path to stimuli (default = <experiment_path>/stims)
    subject -- identifier of the subject
    panel -- instance of local Panel() object

    Methods:
    run() -- runs the experiment

    """
    def __init__(self,
                 name='',
                 description='',
                 debug=False,
                 filetime_fmt='%Y%m%d%H%M%S',
                 light_schedule='sun',
                 idle_poll_interval = 60.0,
                 experiment_path='',
                 stim_path='',
                 subject='',
                 panel=None,
                 log_handlers=[],
                 *args, **kwargs):
        super(BaseExp,  self).__init__()

        self.name = name
        self.description = description
        self.debug = debug
        self.timestamp = dt.datetime.now().strftime(filetime_fmt)
        self.parameters = kwargs
        self.parameters['filetime_fmt'] = filetime_fmt
        self.parameters['light_schedule'] = light_schedule
        self.parameters['idle_poll_interval'] = idle_poll_interval

        self.parameters['experiment_path'] = experiment_path
        if stim_path == '':
            self.parameters['stim_path'] = os.path.join(experiment_path,'stims')
        else:
            self.parameters['stim_path'] = stim_path
        self.parameters['subject'] = subject

        # configure logging
        self.parameters['log_handlers'] = log_handlers
        self.log_config()

        self.req_panel_attr= ['house_light',
                              'reset',
                              ]
        self.panel = panel
        self.log.debug('panel %s initialized' % self.parameters['panel_name'])

        if 'shape' not in self.parameters or self.parameters['shape'] not in ['block1', 'block2', 'block3', 'block4', 'block5']:
            self.parameters['shape'] = None

        self.shaper = shape.Shaper(self.panel, self.log, self.parameters, self.log_error_callback)

    def save(self):
        self.snapshot_f = os.path.join(self.parameters['experiment_path'], self.timestamp+'.json')
        with open(self.snapshot_f, 'wb') as config_snap:
            json.dump(self.parameters, config_snap, sort_keys=True, indent=4)

    def log_config(self):

        self.log_file = os.path.join(self.parameters['experiment_path'], self.parameters['subject'] + '.log')

        if self.debug:
            self.log_level = logging.DEBUG
        else:
            self.log_level = logging.INFO

        sys.excepthook = _log_except_hook # send uncaught exceptions to log file

        logging.basicConfig(filename=self.log_file,
                            level=self.log_level,
                            format='"%(asctime)s","%(levelname)s","%(message)s"')
        self.log = logging.getLogger()

        if 'email' in self.parameters['log_handlers']:
            from pyoperant.local import SMTP_CONFIG
            from logging import handlers
            SMTP_CONFIG['toaddrs'] = [self.parameters['experimenter']['email'],]

            email_handler = handlers.SMTPHandler(**SMTP_CONFIG)
            email_handler.setLevel(logging.ERROR)

            heading = '%s\n' % (self.parameters['subject'])
            formatter = logging.Formatter(heading+'%(levelname)s at %(asctime)s:\n%(message)s')
            email_handler.setFormatter(formatter)

            self.log.addHandler(email_handler)

    def check_light_schedule(self):
        """returns true if the lights should be on"""
        return utils.check_time(self.parameters['light_schedule'])

    def check_session_schedule(self):
        """returns True if the subject should be running sessions"""
        return False

    def panel_reset(self):
        try:
            self.panel.reset()
        except components.ComponentError as err:
            self.log.warning("component error: %s" % str(err))

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
        if self.parameters['shape']:
                self.shaper.run_shape(self.parameters['shape'])
        while True: #is this while necessary
            utils.run_state_machine(start_in='idle',
                                    error_state='idle',
                                    error_callback=self.log_error_callback,
                                    idle=self._run_idle,
                                    sleep=self._run_sleep,
                                    session=self._run_session)

    def _run_idle(self):
        if self.check_light_schedule() == False:
            return 'sleep'
        elif self.check_session_schedule():
            return 'session'
        else:
            self.panel_reset()
            self.log.debug('idling...')
            utils.wait(self.parameters['idle_poll_interval'])
            return 'idle'



    # defining functions for sleep
    def sleep_pre(self):
        self.log.debug('lights off. going to sleep...')
        return 'main'

    def sleep_main(self):
        """ reset expal parameters for the next day """
        self.log.debug('sleeping...')
        self.panel.house_light.off()
        utils.wait(self.parameters['idle_poll_interval'])
        if self.check_light_schedule() == False:
            return 'main'
        else:
            return 'post'

    def sleep_post(self):
        self.log.debug('ending sleep')
        self.panel.house_light.on()
        self.init_summary()
        return None

    def _run_sleep(self):
        utils.run_state_machine(start_in='pre',
                                error_state='post',
                                error_callback=self.log_error_callback,
                                pre=self.sleep_pre,
                                main=self.sleep_main,
                                post=self.sleep_post)
        return 'idle'

    # session

    def session_pre(self):
        return 'main'

    def session_main(self):
        return 'post'

    def session_post(self):
        return None

    def _run_session(self):
        utils.run_state_machine(start_in='pre',
                                error_state='post',
                                error_callback=self.log_error_callback,
                                pre=self.session_pre,
                                main=self.session_main,
                                post=self.session_post)
        return 'idle'


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
            self.log.critical(str(err))
