import time, datetime, subprocess, comedi, socket

## defining Error classes for operant HW control
class Error(Exception):
    '''base class for exceptions in thie module'''
    pass

class ComediError(Error):
    '''raised for problems communicating with the comedi driver'''  
    pass

class OperantError(Error):
    """raised for problems with the operant box"""
    pass

class ResponseDuringFeedError(Error):
    """raised when subject response during feed, suggesting that hopper may be working improperly"""
    def __init__(self,box_id):
        self.box_id = box_id
        self.timestamp = datetime.datetime.now()

class HopperError(Error):
    """raised when there is a detected error with the hopper (1: already up, 2: didn't come up, 3: didn't go down)"""
    def __init__(self,box_id,value):
        self.box_id = box_id
        self.value = value
        self.timestamp = datetime.datetime.now()

## some basic parameters for the operant interface on vogel
# vogel IO map
class Machine():
    """Class which holds information about the computer which the code is running on.

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
            self.device.append(comedi.comedi_open('/dev/comedi0'))
            self.box_io= {1:(0,2, 0,2, 8), # box_id:(card_num,in_dev,in_chan,out_dev,out_chan)
                          2:(0,2, 4,2,16),
                          3:(0,2,24,2,32),
                          4:(0,2,28,2,40),
                          5:(0,2,48,2,56),
                          6:(0,2,52,2,64),
                          7:(0,2,72,2,80),
                          8:(0,2,76,2,88),
                          }
        elif self.hostname.find('ndege')>-1:
            self.name = 'ndege'
            self.device.append(comedi.comedi_open('/dev/comedi0'))
            self.device.append(comedi.comedi_open('/dev/comedi1'))
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
        else:
            raise ComediError

## defining operant functions
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
    proc = subprocess.Popen(['aplay','-q', '-D', alsadevice, filename],stdout=subprocess.PIPE)
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

        Returns boolean value of port
        """
        # port_id is the local port number 1-4
        r =  operant_read(self.m,self.box_id,port_id)
        if r < 0 :
            raise OperantError
        return r

    def write(self,port_id,val=None):
        """Writes value of output port on this box.
        
        Keyword arguments:
        port_id -- int of port to write or query
        val     -- value to assign to port (default=None)

        If no value is assigned for val, then current value is returned.
        Otherwise, returns 1 for successful write or -1 for failure
        """
        r = operant_write(self.m,self.box_id,port_id,val)
        if r < 0 :
            raise OperantError
        return r

    def toggle(self,port_id):
        """ Toggles value of output port based on current value"""
        return self.write(port_id, not self.write(port_id))


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
        try:
            return play_wav(self.box_id,soundfname)
        except:
            return False
        
    def feed(self, feedsecs=2.0, hopper_lag=0.3):
        """Performs a feed for this box.

        arguments:
        feedsecs -- duration of feed in seconds (default: %default)
        """
        
        try:
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

        except ResponseDuringFeedError as e:
            return e
        except HopperError as e:
            return e
        else: 
            return (tic, toc)
        finally:
            self.write(self.id_hopper, False)
    
    def timeout(self, timeoutsecs=10):
        """Turns off the light in the box temporarily

        :param timeoutsecs: Duration of timeout in seconds
        :type  timeoutsecs: float

        :return: epoch of timeout
        :rtype: (datetime, datetime)
        """
        try:
            tic = datetime.datetime.now()
            self.write(self.id_light, False)
            wait(timeoutsecs)
            toc = datetime.datetime.now()
            self.write(self.id_light, True)
        except OperantError as e:
            return e
        except Error as e:
            return e
        else:
            return (tic, toc)

    def lights_on(self,on=True):
        self.write(self.id_light,on)

    def lights_off(self,off=True):
        on = not off
        self.write(self.id_light,on) 

    def LED(self, port_ids=(1,2,3), dur=2.0):
        try:
            for p in port_ids:
                self.write(p,True)
            wait(dur)
            for p in port_ids:
                self.write(p,False)
            return True
            
        except:
            return False

    def flash(self,port_ids=(1,2,3),dur=2.0,isi=0.1):
        """ flash a set of LEDs """

        try:
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
            
        except:
            return False

    
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


