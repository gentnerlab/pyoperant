import time, datetime, subprocess, comedi, socket, logging

## defining Error classes for operant HW control
class Error(Exception):
    '''base class for exceptions in this module'''
    logger = logging.getLogger()
    log_level = logging.ERROR
    def __init__(self):
        self.logger.log(self.log_level, self.log_message())
    def log_message(self):
        return 'Exception occured'

class ComediError(Error):
    '''raised for problems communicating with the comedi driver''' 
    log_level = logging.CRITICAL
    def log_message(self):
        return 'error with comedi driver'

class OperantError(Error):
    """raised for problems with the operant box"""
    log_level = logging.ERROR
    def log_message(self):
        return 'error with operant control'

class ResponseDuringFeedError(Error):
    """raised when subject response during feed, suggesting that hopper may be working improperly"""
    log_level = logging.ERROR
    # def __init__(self,box_id):
    #     self.box_id = box_id
    #     self.timestamp = datetime.datetime.now()
    def log_message(self):
        return 'bird is responding during a feed'

class HopperError(Error):
    """raised when there is a detected error with the hopper (1: already up, 2: didn't come up, 3: didn't go down)"""
    log_level = logging.ERROR
    # def __init__(self,box_id,value):
    #     self.box_id = box_id
    #     self.value = value
    #     self.timestamp = datetime.datetime.now()
    def log_message(self):
        if self.value == 1:
            return "hopper was already up at start of the feed"
        elif self.value == 2:
            return "hopper didn't raise at the start of the feed"
        elif self.value == 3:
            return "hopper didn't go down at the end of the feed"

## some basic parameters for the operant interface on vogel
# vogel IO map
class Machine():
    """Class which holds information about the computer which the code is running on.

    NOTE: "vogel" and "ndege" are the only hostnames this will work for.

    Methods:
    hostname -- hostname of computer
    device --  list of C pointers to comedi devices
    box_io -- dictionary of port mappings for comedi device 
              box_id:(card_num,in_dev,in_chan,out_dev,out_chan)
    """
    def __init__(self):
        self.device = []
        self.hostname = socket.gethostname()
        self.box_io = []
        if self.hostname.find('vogel')>-1:
            self.name = 'vogel'
            self.box_io= {1:(0,2, 0,2, 8), # box_id:(card_num,in_dev,in_chan,out_dev,out_chan)
                          2:(0,2, 4,2,16),
                          3:(0,2,24,2,32),
                          4:(0,2,28,2,40),
                          5:(0,2,48,2,56),
                          6:(0,2,52,2,64),
                          7:(0,2,72,2,80),
                          8:(0,2,76,2,88),
                          }
            try:
                self.device.append(comedi.comedi_open('/dev/comedi0'))
            except:
                raise ComediError("cannot connect to comedi device on vogel")
        elif self.hostname.find('ndege')>-1:
            self.name = 'ndege'
            self.box_io= {1:(0,0,0,0, 8), # box_id:(card_num,in_dev,in_chan,out_dev,out_chan)
                          2:(0,0,4,0,16),
                          3:(0,1,0,1, 8),
                          4:(0,1,4,1,16),
                          5:(0,2,0,2, 8),
                          6:(0,2,4,2,16),
                          7:(0,3,0,3, 8),
                          8:(0,3,4,3,16),
                          9:(1,0,0,0, 8), # box_id:(card_num,in_dev,in_chan,out_dev,out_chan)
                          10:(1,0,4,0,16),
                          11:(1,1,0,1, 8),
                          12:(1,1,4,1,16),
                          13:(1,2,0,2, 8),
                          14:(1,2,4,2,16),
                          15:(1,3,0,3, 8),
                          16:(1,3,4,3,16),
                          }
            try:
                self.device.append(comedi.comedi_open('/dev/comedi0'))
                self.device.append(comedi.comedi_open('/dev/comedi1'))
            except:
                raise ComediError("cannot connect to comedi device on ndege")
        else:
            raise Error("unknown hostname")


def operant_read(m,box_id,port):
    """Read from operant input port.
    
    m -- Machine() object
    box_id -- integer value of box to query
    port -- integer value of input port to query

    returns value of port (True=on,False=off) or negative error
    """
    device = m.device[m.box_io[box_id][0]]
    in_dev = m.box_io[box_id][1]
    in_chan= m.box_io[box_id][2]+port-1
    (s,v) = comedi.comedi_dio_read(device,in_dev,in_chan)
    if s:
        return (not v)
    else:
        return s
    
def operant_write(m,box_id,port,val=None):
    """Write to or read from operant output port

    m -- Machine() object
    box_id -- integer value of box to query
    port -- integer value of output port to query
    val -- value to assign to output (1=on,0=off)
    
    Returns 1 for successful write or -1 for failure

    If val is omitted, operant_write returns the status of the output port (1=on,0=off)
    """
    out_dev = m.box_io[box_id][3]
    out_chan= m.box_io[box_id][4]+port-1
    device = m.device[m.box_io[box_id][0]]
    if val > -1:
        val = not val #invert the value for comedi
    	return comedi.comedi_dio_write(device,out_dev,out_chan,val)
    else:
        (s,v) = comedi.comedi_dio_read(device,out_dev,out_chan)
        if s:
            return (not v)
        else:
            return s

def play_wav(box_id,filename):
    """Play wave file using ALSA aplay

    box_id -- integer value of box to play file to
    filename -- string of absolute path of wav file to play

    Returns a process object (see subprocess.Popen)
    
    This lets you continue to run other code (say, to query for
    responses during payback) but still have access to the aplay
    process status through the process object (so you can run 
    proc.kill() to terminate playback if the subject responded).
    """
    # takes box_id & filename and returns process object
    alsadevice = 'dac%d' % box_id
    proc = subprocess.Popen(['aplay','-q', '-D', alsadevice, filename],stdout=subprocess.PIPE,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    return proc

def wait(secs=1.0, final_countdown=0.2,waitfunc=None):
    """Smartly wait for a given time period.

    secs -- total time to wait in seconds
    final_countdown -- time at end of secs to wait and constantly poll the clock
    waitfunc -- optional function to run in a loop during hogCPUperiod 

    If secs=1.0 and final_countdown=0.2 then for 0.8s python's time.sleep function will be used,
    which is not especially precise, but allows the cpu to perform housekeeping. In
    the final hogCPUsecs the more precise method of constantly polling the clock
    is used for greater precision.
    """
    #initial relaxed period, using sleep (better for system resources etc)
    if secs>final_countdown:
        time.sleep(secs-final_countdown)
        secs=final_countdown # only this much is now left

    #It's the Final Countdown!! 
    #hog the cpu, checking time
    t0=time.time()
    while (time.time()-t0)<secs:
        #let's see if any events were collected in meantime
        try:
            waitfunc()
        except:
            pass


## Box classes
class Box():
    """Defines basic class for experiment box.

    This class has a minimal set of information to allow
    reading from input ports and writing to output ports
    of an experimental box.
    """
    def __init__(self, box_id):
        self.box_id = box_id
        self.m = Machine()

    def read(self,port_id):
        """Reads value of input port on this box.

        Keyword arguments:
        port_id -- int of port to query

        Returns boolean value of port or raises OperantError
        """
        # port_id is the local port number 1-4
        r =  operant_read(self.m,self.box_id,port_id)
        if r < 0 :
            raise OperantError("error reading from input port %i on %s box %i" % (port_id, self.m.name, self.box_id))
        return r

    def write(self,port_id,val=None):
        """Writes value of output port on this box.
        
        Keyword arguments:
        port_id -- int of port to write or query
        val     -- value to assign to port (default=None)

        If no value is assigned for val, then current value is returned.
        Returns 1 for successful write or raises OperantError
        """
        r = operant_write(self.m,self.box_id,port_id,val)
        if r < 0 :
            raise OperantError("error writing to output port %i on %s box %i" % (port_id, self.m.name, self.box_id))
        return r

    def toggle(self,port_id):
        """ Toggles value of output port based on current value"""
        current_val = self.write(port_id)
        if current_val > -1:
            r = self.write(port_id, not current_val)
            if r < 0 :
                raise OperantError("error writing to output port %i on %s box %i" % (port_id, self.m.name, self.box_id))
            return r
        else:
            raise OperantError("error reading from output port %i on %s box %i" % (port_id, self.m.name, self.box_id))


class OperantBox(Box):
    """Defines class for an operant box.

    Inherited from Box() class.

    Major methods:
    timeout --  
    feed --

    """
    def __init__(self,box_id):
        Box.__init__(self,box_id)
        # 
        self.id_LEDleft   = 1
        self.id_LEDcenter = 2
        self.id_LEDright  = 3
        self.id_light     = 4
        self.id_hopper    = 5

        self.id_LEDall = (self.id_LEDleft,
                          self.id_LEDcenter,
                          self.id_LEDright,
                          )

        self.id_IRleft   = 1
        self.id_IRcenter = 2
        self.id_IRright  = 3
        self.id_IRhopper = 4
    
    def play_wav(self, soundfname):
        """Plays wave file to this box
        
        soundfname -- absolute path and filename to wav file to play

        Returns a process object (see subprocess.Popen)
                    
        This lets you continue to run other code (say, to query for
        responses during payback) but still have access to the aplay
        process status through the process object (so you can run 
        proc.kill() to terminate playback if the subject responded).
        Returns Process object
        """
        
        return play_wav(self.box_id,soundfname)
        
        
    def feed(self, feedsecs=2.0, hopper_lag=0.3):
        """Performs a feed for this box.

        arguments:
        feedsecs -- duration of feed in seconds (default: %default)
        """
        if self.read(self.id_IRhopper):
            raise HopperError(self.box_id,1) # hopper already up
        tic = datetime.datetime.now()
        self.write(self.id_hopper, True)
        feed_timedelta = datetime.datetime.now() - tic
        while feed_timedelta < datetime.timedelta(seconds=feedsecs):
            for port_id in [1, 2, 3]:
                if self.read(port_id):
                    raise ResponseDuringFeedError(self.box_id)
            if feed_timedelta > datetime.timedelta(seconds=hopper_lag) and not self.read(4):
                raise HopperError(self.box_id,2) # hopper not up during feed
            feed_timedelta = datetime.datetime.now() - tic
        
        self.write(self.id_hopper, False)
        wait(hopper_lag) # let the hopper drop
        toc = datetime.datetime.now()
        if self.read(4):
            raise HopperError(self.box_id,3) # hopper still up after feed

        return (tic, toc)
    
    def timeout(self, timeoutsecs=10):
        """Turns off the light in the box temporarily

        :param timeoutsecs: Duration of timeout in seconds
        :type  timeoutsecs: float

        :return: epoch of timeout
        :rtype: (datetime, datetime)
        """
        
        tic = datetime.datetime.now()
        self.write(self.id_light, False)
        wait(timeoutsecs)
        toc = datetime.datetime.now()
        self.write(self.id_light, True)
    
        return (tic, toc)

    def lights_on(self,on=True):
        self.write(self.id_light,on)

    def lights_off(self,off=True):
        on = not off
        self.write(self.id_light,on) 

    def LED(self, port_ids=(1,2,3), dur=2.0):
        for p in port_ids:
            self.write(p,True)
        wait(dur)
        for p in port_ids:
            self.write(p,False)
        return True
            

    def flash(self,port_ids=(1,2,3),dur=2.0,isi=0.1):
        """ flash a set of LEDs """
        prior = [self.write(p) for p in port_ids]
        
        tic = datetime.datetime.now()
        while (datetime.datetime.now()-tic) < datetime.timedelta(seconds=dur):
            for p in port_ids:
                self.toggle(p)
            wait(isi)
        for i, p in enumerate(port_ids): 
            self.write(p,prior[i])

        toc = datetime.datetime.now()
        
        return (tic, toc)

    
    def reset(self):
        ports = range(1,9)
        for p in ports:
            self.write(p,False)

    def wait_for_peck(self, port_id):
        """wait for peck and return timestamp after peck"""
        no_peck = True
        while no_peck:
            no_peck = not self.read(port_id)
        return datetime.datetime.now()

class RGBcueBox(OperantBox):
    def __init__(self,box_id):
        OperantBox.__init__(self,box_id)
        self.id_cueG      = 6
        self.id_cueB      = 7
        self.id_cueR      = 8


