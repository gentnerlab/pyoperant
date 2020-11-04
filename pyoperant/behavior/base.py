import logging, traceback
import os, sys, socket
import datetime as dt
from pyoperant import utils, components
from pyoperant import ComponentError, InterfaceError
from pyoperant.behavior import shape
import random
import zmq
from zmq.log.handlers import PUBHandler
from pyoperant.interfaces.open_ephys_ import OpenEphysEvents


try:
    import simplejson as json
except ImportError:
    import json


def _log_except_hook(*exc_info):
    text = "".join(traceback.format_exception(*exc_info))
    logging.error("Unhandled exception: %s", text)


class BaseExp(object):
    """Base class for an experiment.

    Defines things like the the state machine between the behavior and sleep states, 
    what a session is, etc. 

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

    def __init__(
        self,
        name="",
        description="",
        debug=False,
        filetime_fmt="%Y%m%d%H%M%S",
        light_schedule="sun",
        idle_poll_interval=60.0,
        experiment_path="",
        stim_path="",
        subject="",
        panel=None,
        log_handlers=[],
        *args,
        **kwargs
    ):
        super(BaseExp, self).__init__()

        self.name = name
        self.description = description
        self.debug = debug
        self.timestamp = dt.datetime.now().strftime(filetime_fmt)
        self.parameters = kwargs
        self.parameters["filetime_fmt"] = filetime_fmt
        self.parameters["light_schedule"] = light_schedule
        self.parameters["idle_poll_interval"] = idle_poll_interval

        self.parameters["experiment_path"] = experiment_path
        if stim_path == "":
            self.parameters["stim_path"] = os.path.join(experiment_path, "stims")
        else:
            self.parameters["stim_path"] = stim_path
        self.parameters["subject"] = subject

        # configure logging
        self.parameters["log_handlers"] = log_handlers
        self.log_config()

        self.req_panel_attr = ["house_light", "reset"]
        self.panel = panel
        self.log.debug("panel %s initialized" % self.parameters["panel_name"])

        if "shape" not in self.parameters or self.parameters["shape"] not in [
            "block1",
            "block2",
            "block3",
            "block4",
            "block5",
        ]:
            self.parameters["shape"] = None

        self.shaper = shape.Shaper(
            self.panel, self.log, self.parameters, self.log_error_callback
        )

        # connect to open ephys
        if "open_ephys" in self.parameters.keys():
            if self.parameters["open_ephys"]["connect"] == "True":
                self.openephys = OpenEphysEvents(
                    port=self.parameters["open_ephys"]["port"],
                    ip=self.parameters["open_ephys"]["address"],
                )
                self.openephys.connect()

    def save(self):
        self.snapshot_f = os.path.join(
            self.parameters["experiment_path"], self.timestamp + ".json"
        )
        with open(self.snapshot_f, "w") as config_snap:
            json.dump(self.parameters, config_snap, sort_keys=True, indent=4)

    def log_config(self):

        self.log_file = os.path.join(
            self.parameters["experiment_path"], self.parameters["subject"] + ".log"
        )

        if self.debug:
            self.log_level = logging.DEBUG
        else:
            self.log_level = logging.INFO

        sys.excepthook = _log_except_hook  # send uncaught exceptions to log file

        logging.basicConfig(
            filename=self.log_file,
            level=self.log_level,
            format='"%(asctime)s","%(levelname)s","%(message)s"',
        )
        self.log = logging.getLogger()

        if "email" in self.parameters["log_handlers"]:
            from pyoperant.local import SMTP_CONFIG
            from logging import handlers

            SMTP_CONFIG["toaddrs"] = [self.parameters["experimenter"]["email"]]

            email_handler = handlers.SMTPHandler(**SMTP_CONFIG)
            email_handler.setLevel(logging.WARNING)

            heading = "%s\n" % (self.parameters["subject"])
            formatter = logging.Formatter(
                heading + "%(levelname)s at %(asctime)s:\n%(message)s"
            )
            email_handler.setFormatter(formatter)

            self.log.addHandler(email_handler)

    def check_light_schedule(self):
        """returns true if the lights should be on"""
        return utils.check_time(self.parameters["light_schedule"])

    def check_session_schedule(self):
        """returns True if the subject should be running sessions"""
        return False

    def panel_reset(self):
        try:
            self.panel.reset()
        except components.ComponentError as err:
            self.log.error("component error: %s" % str(err))

    def run(self):

        for attr in self.req_panel_attr:
            assert hasattr(self.panel, attr)
        self.panel_reset()
        self.save()
        self.init_summary()

        self.log.info(
            "%s: running %s with parameters in %s"
            % (self.name, self.__class__.__name__, self.snapshot_f)
        )
        if self.parameters["shape"]:
            self.shaper.run_shape(self.parameters["shape"])
        while True:  # is this while necessary
            utils.run_state_machine(
                start_in="idle",
                error_state="idle",
                error_callback=self.log_error_callback,
                idle=self._run_idle,
                sleep=self._run_sleep,
                session=self._run_session,
                free_food_block=self._free_food,
                passive_playback_block=self._passive_playback,
            )

    def _run_idle(self):
        self.log.debug("Starting _run_idle")
        if self.check_light_schedule() == False:
            return "sleep"
        elif self.check_session_schedule():
            if self._check_free_food_block():
                return "free_food_block"
            if self._check_passive_playback_block():
                return "passive_playback_block"
            return "session"
        else:
            self.panel_reset()
            self.log.debug("idling...")
            utils.wait(self.parameters["idle_poll_interval"])
            return "idle"

    # defining functions for sleep
    def sleep_pre(self):
        self.log.debug("lights off. going to sleep...")
        return "main"

    def sleep_main(self):
        """ reset expal parameters for the next day """
        self.log.debug("sleeping...")
        self.panel.house_light.off()
        utils.wait(self.parameters["idle_poll_interval"])
        if self.check_light_schedule() == False:
            return "main"
        else:
            return "post"

    def sleep_post(self):
        self.log.debug("ending sleep")
        self.panel.house_light.on()
        self.init_summary()
        return None

    def _run_sleep(self):
        utils.run_state_machine(
            start_in="pre",
            error_state="post",
            error_callback=self.log_error_callback,
            pre=self.sleep_pre,
            main=self.sleep_main,
            post=self.sleep_post,
        )
        return "idle"

    # session
    def _wait_block(self, t_min, t_max, next_state):
        def temp():
            if t_min == t_max:
                t = t_max
            else:
                t = random.randrange(t_min, t_max)
            utils.wait(t)
            return next_state

        return temp

    ### passive playback code
    def _check_passive_playback_block(self):
        """ Checks if it is currently a passive playback block
        """
        if "oe_conf" in self.parameters:
            if self.parameters["oe_conf"]["on"] is True:
                if "passive_playback" in self.parameters["oe_conf"]:
                    if self.parameters["oe_conf"]["passive_playback"] is True:
                        passive_playback_times = self.parameters["oe_conf"][
                            "passive_playback_times"
                        ]
                        # look through passive playback times (e.g. [["09:00","23:00"]])
                        if utils.check_time(passive_playback_times):
                            return True

    def passive_playback_pre(self):
        self.log.debug("Passive playback starting.")
        return "main"

    def passive_playback_main(self):
        """"""
        self.log.debug("Starting passive playback main.")
        utils.run_state_machine(
            start_in="wait",
            error_state="wait",
            error_callback=self.log_error_callback,
            # wait 5 seconds
            wait=self._wait_block(5, 5, "passive_playback"),
            # start passive playback
            passive_playback=self.perform_passive_playback(10, "checker"),
            # check if we should still be in passive playback mode
            checker=self.passive_playback_checker("wait"),
        )
        passive_playback_times = self.parameters["oe_conf"]["passive_playback_times"]
        if not utils.check_time(passive_playback_times):
            return "post"
        else:
            return "main"

    def passive_playback_checker(self, next_state):
        # should we be doing a passive playback
        def temp():
            if "oe_conf" in self.parameters:
                if self.parameters["oe_conf"]["on"] is True:
                    if "passive_playback" in self.parameters["oe_conf"]:
                        if self.parameters["oe_conf"]["passive_playback"] is True:
                            passive_playback_times = self.parameters["oe_conf"][
                                "passive_playback_times"
                            ]
                            # look through passive playback times (e.g. [["09:00","23:00"]])
                            if utils.check_time(passive_playback_times):
                                return next_state
            return None

        return temp

    def passive_playback_post(self):
        self.log.debug("Passive playback over.")
        return None

    def _passive_playback(self):
        self.log.debug("Starting _passive_playback")
        utils.run_state_machine(
            start_in="pre",
            error_state="post",
            error_callback=self.log_error_callback,
            pre=self.passive_playback_pre,
            main=self.passive_playback_main,
            post=self.passive_playback_post,
        )
        return "idle"


    def perform_passive_playback(self, value, next_state):
        """
        A function to run a passive playback block, embedded within normal behavior, in open ephys
        """
        def temp():
            self.log.debug("Starting passive playback function.")
                try:
                    # get list of stimuli
                    wav_files = []
                    for ext in ['.wav', '.WAV']:
                        for stim_folder in self.parameters['oe_conf']['passive']['stims_folders']:
                            wav_files.extend(
                                list(
                                    Path(
                                        stim_folder
                                    ).glob('**/*'+ext)
                                )
                            )
                    # create a list of wav_files
                    n_rep = self.parameters['oe_conf']['passive']['wav_repeats']
                    wav_list = np.repeat(wav_files, n_rep)
                    wav_list = np.random.permutation(wav_list)

                    # total expected duration
                    durations = [utils.get_audio_duration(wf.as_posix()) for wf in wav_list]
                    duration_remaining = (
                        np.sum(durations) + 
                        self.parameters['oe_conf']['sine_wav_padding']*2*len(wav_list)
                    )
                    start_time = time.time()

                    # loop through stimuli
                    for wfi, wf in enumerate(wav_list):
                        # get timing info
                        current_time = time.time()
                        duration_elapsed = current_time - start_time
                        expected_time_remaining = (
                            duration_remaining + 
                            np.mean(self.parameters['oe_conf']["passive"]['isi_range'])*
                            (len(wav_list) -wfi)
                        )
                        time_string = "{}/{}".format(
                            utils.seconds_to_human_readable(duration_elapsed), 
                            utils.seconds_to_human_readable(
                                (expected_time_remaining+duration_elapsed)
                            )
                            )
                        # Send Stimulus Name to OpenEphys
                        stim_string = "{}/{}:  {}".format(wfi, len(wav_list), wf)
                        self.log.info(stim_string)
                        self.log.info(time_string)

                        self.open_ephys.send_command('stim ' + wf.as_posix())
                        # create a temporary wav with sine for OpenEphys
                        temp_wav = utils.add_sine_to_wav(
                            wf.as_posix(), 
                            padding = self.parameters['oe_conf']['sine_wav_padding']
                            )
                        stim = utils.auditory_stim_from_wav(temp_wav)
                        # play the wav
                        self.panel.speaker.queue(stim.file_origin)
                        self.panel.speaker.play()
                        utils.wait(stim.duration)
                        self.panel.speaker.stop()
                        duration_remaining -= stim.duration

                        # pause for isi time
                        isi = random.uniform(
                            self.parameters['oe_conf']["passive"]['isi_range'][0],
                            self.parameters['oe_conf']["passive"]['isi_range'][1]
                        )
                        utils.wait(isi)

                except Exception as e:
                    self.log.error('Error at %s', 'division', exc_info=e)
            
            return next_state
        return temp

    def _check_free_food_block(self):
        """ Checks if it is currently a free food block
        """
        if "free_food_schedule" in self.parameters:
            if utils.check_time(self.parameters["free_food_schedule"]):
                return True

    def free_food_pre(self):
        self.log.debug("Buffet starting.")
        return "main"

    def free_food_main(self):
        """ reset expal parameters for the next day """
        self.log.debug("Starting Free Food main.")
        utils.run_state_machine(
            start_in="wait",
            error_state="wait",
            error_callback=self.log_error_callback,
            wait=self._wait_block(5, 5, "food"),
            food=self.deliver_free_food(10, "checker"),
            checker=self.food_checker("wait"),
        )

        if not utils.check_time(self.parameters["free_food_schedule"]):
            return "post"
        else:
            return "main"

    def food_checker(self, next_state):
        # should we still be giving free food?
        def temp():
            if "free_food_schedule" in self.parameters:
                if utils.check_time(self.parameters["free_food_schedule"]):
                    return next_state
            return None

        return temp

    def free_food_post(self):
        self.log.debug("Free food over.")
        return None

    def _free_food(self):
        self.log.debug("Starting _free_food")
        utils.run_state_machine(
            start_in="pre",
            error_state="post",
            error_callback=self.log_error_callback,
            pre=self.free_food_pre,
            main=self.free_food_main,
            post=self.free_food_post,
        )
        return "idle"

    def deliver_free_food(self, value, next_state):
        """ reward function with no frills
        """

        def temp():
            self.log.debug("Doling out some free food.")

            try:
                reward_event = self.panel.reward(value=value)
            except:
                self.log.warning("Hopper did not drop on free food")

            return next_state

        return temp

    def session_pre(self):
        return "main"

    def session_main(self):
        return "post"

    def session_post(self):
        return None

    def _run_session(self):
        utils.run_state_machine(
            start_in="pre",
            error_state="post",
            error_callback=self.log_error_callback,
            pre=self.session_pre,
            main=self.session_main,
            post=self.session_post,
        )
        return "idle"

    # gentner-lab specific functions
    def init_summary(self):
        """ initializes an empty summary dictionary """
        self.summary = {
            "trials": 0,
            "feeds": 0,
            "hopper_failures": 0,
            "hopper_wont_go_down": 0,
            "hopper_already_up": 0,
            "responses_during_feed": 0,
            "responses": 0,
            "last_trial_time": [],
        }

    def write_summary(self):
        """ takes in a summary dictionary and options and writes to the bird's summaryDAT"""
        summary_file = os.path.join(
            self.parameters["experiment_path"],
            self.parameters["subject"][1:] + ".summaryDAT",
        )
        with open(summary_file, "w") as f:
            f.write("Trials this session: %s\n" % self.summary["trials"])
            f.write("Last trial run @: %s\n" % self.summary["last_trial_time"])
            f.write("Feeder ops today: %i\n" % self.summary["feeds"])
            f.write("Hopper failures today: %i\n" % self.summary["hopper_failures"])
            f.write(
                "Hopper won't go down failures today: %i\n"
                % self.summary["hopper_wont_go_down"]
            )
            f.write(
                "Hopper already up failures today: %i\n"
                % self.summary["hopper_already_up"]
            )
            f.write(
                "Responses during feed: %i\n" % self.summary["responses_during_feed"]
            )
            f.write("Rf'd responses: %i\n" % self.summary["responses"])

    def log_error_callback(self, err):
        if err.__class__ is InterfaceError or err.__class__ is ComponentError:
            self.log.critical(str(err))
