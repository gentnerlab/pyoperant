import os
import csv
import copy
import datetime as dt
from pyoperant.behavior import base, shape
from pyoperant.errors import EndSession, EndBlock
from pyoperant import components, utils, reinf, queues

# added for open ephys
from pyoperant.interfaces.open_ephys_ import connect_to_open_ephys, close_open_ephys
from pathlib import Path
import numpy as np
import random 
import time

class OpenEphysPassive(base.BaseExp):
    """A two alternative choice experiment

    Parameters
    ----------


    Attributes
    ----------
    req_panel_attr : list
        list of the panel attributes that are required for this behavior
    fields_to_save : list
        list of the fields of the Trial object that will be saved
    trials : list
        all of the trials that have run
    shaper : Shaper
        the protocol for shaping
    parameters : dict
        all additional parameters for the experiment
    data_csv : string
        path to csv file to save data
    reinf_sched : object
        does logic on reinforcement



    """

    def __init__(self, *args, **kwargs):
        super(OpenEphysPassive, self).__init__(*args, **kwargs)

        if "session_schedule" not in self.parameters:
            self.parameters["session_schedule"] = self.parameters["light_schedule"]
    def check_session_schedule(self):
        return True
    def session_pre(self):
        """ Runs before the session starts

        For each stimulus class, if there is a component associated with it, that
        component is mapped onto `experiment.class_assoc[class]`. For example,
        if the `left` port is registered with the 'L' class, you can access the response
        port through `experiment.class_assoc['L']`.

        """
        ### ensure all pins are down
        self.panel.reset()
        # open openephys connection and start recording
        self.open_ephys = connect_to_open_ephys(self.parameters)
        return "main"
        

    def session_main(self):
        """ Runs the sessions

        Inside of `session_main`, we loop through sessions and through the trials within
        them. This relies heavily on the 'block_design' parameter, which controls trial
        conditions and the selection of queues to generate trial conditions.

        """
        self.log.info("session main")
        try:
            # get list of stimuli
            wav_files = []
            for ext in ['.wav', '.WAV']:
                wav_files.extend(
                    list(
                        Path(
                            self.parameters['oe_conf']['passive']['stims_folder']
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
                # create a temporary wav with sine for OpenEphyss
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
        return "post"

    def session_post(self):
        """ Closes out the sessions

        """
        # reset if panel can reset
        if callable(getattr(self.panel, "reset", None)):
            self.panel.reset()
        close_open_ephys(self.open_ephys, self.parameters)
        self.log.info("ending session")
        
        return None

