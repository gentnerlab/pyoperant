import logging
import os
import datetime as dt
from pyoperant import utils, components, local, hwio


try: import simplejson as json
except ImportError: import json

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
        self.log_file = os.path.join(self.parameters['experiment_path'], self.parameters['subject'] + '.log')
        self.log_config()

        self.req_panel_attr= ['house_light',
                              'reset',
                              ]
        self.panel = panel
        self.log.debug('panel %s initialized' % self.parameters['panel_name'])

    def save(self):
        self.snapshot_f = os.path.join(self.parameters['experiment_path'], self.timestamp+'.json')
        with open(self.snapshot_f, 'wb') as config_snap:
            json.dump(self.parameters, config_snap, sort_keys=True, indent=4)

    def log_config(self):
        if self.debug:
            self.log_level = logging.DEBUG
        else:
            self.log_level = logging.INFO

        logging.basicConfig(filename=self.log_file,
                            level=self.log_level,
                            format='"%(asctime)s","%(levelname)s","%(message)s"')
        self.log = logging.getLogger()
        #email_handler = logging.handlers.SMTPHandler(mailhost='localhost',
        #                                             fromaddr='bird@vogel.ucsd.edu',
        #                                             toaddrs=[options['experimenter']['email'],],
        #                                             subject='error notice',
        #                                             )
        #email_handler.setlevel(logging.ERROR)
        #log.addHandler(email_handler)

    def check_light_schedule(self):
        return utils.check_time(self.parameters['light_schedule'])

    def check_session_schedule(self):
        return False


    def run(self):

        for attr in self.req_panel_attr:
            assert hasattr(self.panel,attr)
        self.panel.reset()
        self.save()
        self.init_summary()
        
        self.log.info('%s: running %s with parameters in %s' % (self.name,
                                                                self.__class__.__name__,
                                                                self.snapshot_f,
                                                                )
                      )

        machine = {'idle': self._idle,
                   'sleep': self._sleep_flow,
                   'session': self._session_flow,
                   }
        state = 'idle'
        while state is not None:
            state = machine[state]()

    def _idle(self):
        if not self.check_light_schedule():
            return 'sleep'
        elif self.check_session_schedule():
            return 'session'
        else:
            self.panel.reset()
            self.log.debug('idling...')
            utils.wait(self.parameters['idle_poll_interval'])
            return 'idle'



    # defining functions for sleep flow
    def sleep_pre(self):
        self.log.debug('lights off. going to sleep...')
        return 'main'

    def sleep_main(self):
        """ reset expal parameters for the next day """
        self.log.debug('sleeping...')
        self.panel.house_light.off()
        utils.wait(self.parameters['idle_poll_interval'])
        if self.check_light_schedule():
            return 'main'
        else:
            return 'post'

    def sleep_post(self):
        self.log.debug('ending sleep')
        self.panel.house_light.on()
        self.init_summary()
        return None

    def _sleep_flow(self):
        machine = {'pre': self.sleep_pre,
                   'main': self.sleep_main,
                   'post': self.sleep_post,
                   }
        state = 'pre'
        while state is not None:
            state = machine[state]()
        return 'idle'

    # session flow

    def check_session_schedule(self):
        return not self.check_light_schedule()

    def session_pre(self):
        return 'main'

    def session_main(self):
        return 'post'

    def session_post(self):
        return None

    def _session_flow(self):
        utils.do_flow(pre=self.session_pre,
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
