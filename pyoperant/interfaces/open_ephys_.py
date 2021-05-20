"""
ZMQ communication to open ephys
For references see:
        - https://open-ephys.atlassian.net/wiki/spaces/OEW/pages/23265310/Network+Events
        - https://github.com/open-ephys/GUI/blob/master/Resources/Python/
        - https://github.com/theilmbh/glab_oe_rig_tools/blob/master/acute_rig_control_gui.py
        - https://github.com/zekearneodo/rigmq
"""
import smtplib
import zmq
import logging
import time
import datetime

class OpenEphysEvents:
    def __init__(self, port="5556", ip="127.0.0.1", parameters = None, is_logging=True):
        """creates an open ephys object to communicate with open ephys via ZeroMQ
        
        [description]
        
        Keyword Arguments:
            port {str} -- The port to communicate over (default: {'5556'})
            ip {str} -- the ip address to communicate with (default: {'127.0.0.1'})
            is_logging whether to log, or print errors -- [description] (default: {True})
        """
        self.ip = ip
        self.port = port
        self.socket = None
        self.context = None
        self.timeout = 5.0
        self.last_cmd = None
        self.last_rcv = None
        self.parameters = parameters
        # how to log errors, warnings, etc
        self.is_logging = is_logging
        if self.is_logging:
            self.log = logging.getLogger()
    
        # send emails when ZMQ has errors (because the smtp email handler isn't working)
        self._smtp_server = smtplib.SMTP_SSL('smtp.ucsd.edu', 465)
        self._smtp_server.login('starling@ucsd.edu', 'V0gel&Z0g')
        self._last_error_email = datetime.datetime.now() - datetime.timedelta(hours=1, minutes=0)
    def send_error_email(self, e):
        if (datetime.datetime.now() - self._last_error_email).seconds/60 > 30: 
            try:
                message = "Subject: ZMQ Error in Magpi\n\n{}".format(e)
                self._smtp_server.sendmail(
                    'starling@ucsd.edu', 
                    self.parameters['experimenter']['email'],
                    message
                )
                self._last_error_email = datetime.datetime.now()
            except Exception as e:
                self.log_event('Could not send email:'.format(e))

    def connect(self):
        """Connect raspberry pi to open ephys via port
        """
        url = "tcp://%s:%d" % (self.ip, int(self.port))
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.REQ)
        self.socket.RCVTIMEO = int(self.timeout * 1000)
        self.socket.connect(url)

    def start_acq(self,):
        """sends a StartAcquisition command to open_ephys if not currently acquiring data
        """
        if self.query_status("Acquiring"):
            self.log_event(type_="info", message="Already acquiring")
        else:
            self.send_command("StartAcquisition")
            if self.query_status("Acquiring"):
                self.log_event(type_="info", message="Acquisition Started")
            else:
                self.log_event(
                    type_="error", message="Something went wrong starting acquisition"
                )

    def stop_acq(self,):
        """sends a StopAcquisition command to open_ephys if currently acquiring data
        """
        # if currently recording, don't try to stop acquisition
        if self.query_status("Recording"):
            self.log_event(type_="info", message="Cant stop acquistion while recording")
        # if not acquiring, no need to stop
        elif not self.query_status("Acquiring"):
            self.log_event(type_="info", message="No acquisition running")
        # try to stop acquisition, if it doesn't work, send an error message
        else:
            self.send_command("StopAcquisition")
            if not self.query_status("Acquiring"):
                self.log_event(type_="info", message="Acquistion stopped")
            else:
                self.log_event(
                    type_="error", message="Something went wrong stopping acquisition"
                )

    def start_rec(
        self,
        rec_par={
            "CreateNewDir": "0",
            "RecDir": None,
            "PrependText": None,
            "AppendText": None,
        },
    ):
        """Tries to send a StartRecord command to open ephys, making sure open_ephys is also acquiring
        
        Keyword Arguments:
            rec_par {dict} -- parameters for start recording.  (default: {{'CreateNewDir': '0', 'RecDir', 'PrependText', 'AppendText'}})
        
        Returns:
            ok_started [type] -- if the recording started properly
        """
        ok_to_start = (
            False
        )  # if it is ok to start the recording (if currently acquiring)
        ok_started = False  # if the recording started properly

        if self.query_status("Recording"):
            self.log_event(type_="info", message="Already Recording")

        # if your not acquiring, start acquiring
        elif not self.query_status("Acquiring"):
            self.log_event(type_="info", message="Was not Acquiring")
            self.start_acq()
            if self.query_status("Acquiring"):
                ok_to_start = True
                self.log_event(type_="info", message="OK to start")
        else:
            ok_to_start = True
            self.log_event(type_="info", message="OK to start")

        # if its ok to start acquiring, do so
        if ok_to_start:
            rec_opt = [
                "{0}={1}".format(key, value)
                for key, value in rec_par.items()
                if value is not None
            ]
            self.send_command(" ".join(["StartRecord"] + rec_opt))
            if self.query_status("Recording"):
                self.log_event(
                    type_="info",
                    message="Recording path: {}".format(self.get_rec_path()),
                )
                ok_started = True
            else:
                self.log_event(
                    type_="error", message="Something went wrong starting recording"
                )
        else:
            self.log_event(type_="info", message="Did not start recording")
        return ok_started

    def stop_rec(self):
        """ stops recording (not acquiring though)
        """
        if self.query_status("Recording"):
            self.send_command("StopRecord")
            if not self.query_status("Recording"):
                self.log_event(type_="info", message="Recording stopped")
            else:
                self.log_event(
                    type_="error", message="Something went wrong stopping recording"
                )
        else:
            self.log_event(type_="info", message="Was not recording")

    def break_rec(self):
        """ Tries to stop and then restart a recording
        """
        ok_to_start = False
        ok_started = False
        self.log_event(type_="info", message="Breaking recording in progress")
        # if recording, try to stop recording
        if self.query_status("Recording"):
            self.send_command("StopRecord")
            if not self.query_status("Recording"):
                ok_to_start = True
            else:
                self.log_event(
                    type_="error", message="Something went wrong stopping recording"
                )
        else:
            self.log_event(type_="info", message="Was not recording")

        # if recording was successfully stopped, start recording again
        if ok_to_start:
            self.send_command("StartRecord")
            if self.query_status("Recording"):
                # self.log_event(type_="info", message='Recording path: {}'.format(self.get_rec_path()))
                ok_started = True
            else:
                self.log_event(
                    type_="error", message="Something went wrong starting recording"
                )
        return ok_started

    def get_rec_path(self):
        """returns the recording path queried from open ephys
        """
        return self.send_command("GetRecordingPath")

    def query_status(self, status_query="Recording"):
        """ queries whether recording/acquisition is happening
                
        Keyword Arguments:
            status_query {str} -- query for `Recording` or `Acquiring` (default: {'Recording'})
        
        Returns:
            bool -- [description]
        """
        query_dict = {"Recording": "isRecording", "Acquiring": "isAcquiring"}

        # pose query over zmq
        status_queried = self.send_command(query_dict[status_query])
        return (
            True
            if status_queried == b"1"
            else False
            if status_queried == b"0"
            else None
        )

    def send_command(self, cmd):
        """ send a command over zmq socket
        """
        try:
            self.socket.send_string(cmd)
            self.last_cmd = cmd
            self.last_rcv = self.socket.recv()
            return self.last_rcv
        except Exception as e:
            #self.log_event('command failed, retrying: {}'.format(i))
            self.log_event("FAILED ZMQ Command :{}".format(e), type_="error")
            self.send_error_email(e)
            return 0
                
    def close(self):
        """
        Stop recording, acquiring, and kill connection over socket
        """
        self.stop_rec()
        self.stop_acq()
        self.context.destroy()

    def log_event(self, message, type_="info"):
        """either logs or prints events
        
        Log types: logging.DEBUG, logging.INFO,
                  logging.WARN, logging.ERROR, logging.CRITICAL
            
        Arguments:
            message {[type]} -- [description]
        
        Keyword Arguments:
            type_ {str} -- type of message [debug, info, warn, error, critical] (default: {"info"})
            is_logging {bool} -- if we should use a logger or just print (default: {True})
        """

        if self.is_logging:
            if type_ == "debug":
                self.log.debug(message)
            elif type_ == "info":
                self.log.info(message)
            elif type_ == "warn":
                self.log.warn(message)
            elif type_ == "error":
                self.log.error(message)
            elif type_ == "critical":
                self.log.critical(message)

        else:
            self.log_event(type_="info", message=message)


def connect_to_open_ephys(parameters):
    # if set to start open ephys upon session
    if parameters['oe_conf']["on"]:
        openephys = OpenEphysEvents(
                port=parameters['oe_conf']["open_ephys_port"], 
                ip=parameters['oe_conf']["open_ephys_address"],
                parameters=parameters
                )
        openephys.connect()
    else:
        log.error("Open Ephys is off. Ending session.")
        return "post"
    if parameters['oe_conf']['record_sessions_automatically']:
        # start acquiring data
        openephys.start_acq()
        # start recording data 
        RecDir = parameters['oe_conf'][ 'recording_directory'] if 'recording_directory' in parameters['oe_conf'] else None
        openephys.start_rec(rec_par = {
            "CreateNewDir": 1,
            "RecDir": RecDir,
            "PrependText": None,
            "AppendText": None,
        })
    return openephys

def close_open_ephys(open_ephys, parameters):
    # check if we should start recording
    if "oe_conf" in parameters:   
        # check if open ephys is on
        if parameters['oe_conf']["on"]:
            # if set to start open ephys upon session
            if parameters['oe_conf']['record_sessions_automatically']:
                # start recording data 
                open_ephys.stop_rec()
                #start acquiring data
                open_ephys.stop_acq()
