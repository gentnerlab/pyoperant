import threading
import Queue
# from multiprocessing import Process, Queue
import datetime as dt
import logging
import numpy as np
from pyoperant import hwio

logger = logging.getLogger(__name__)

class Events(object):
    """ Writes small event dictionaries out to a list of event handlers.

    Attributes
    ----------
    handlers: list
        The currently configured EventHandler instances

    Methods
    -------
    add_handler(handler) - appends the handler to the handlers list
    write(event) - Writes the dictionary `event` to each handler
    """

    def __init__(self):

        self.handlers = list()

    def add_handler(self, handler):
        """ Adds the handler to the list of handlers, as long as it supports
        writing.

        Parameters
        ----------
        handler: instance of EventHandler
            The handler to be added
        """

        if not hasattr(handler, "queue"):
            raise AttributeError("Event handler instance must contain a queue")

        self.handlers.append(handler)

    def close_handlers(self):
        """ Closes all of the existing handlers """

        for handler in self.handlers:
            handler.close()

    def write(self, event):
        """ Places the event in the queue for each handler to write.

        Parameters
        ----------
        event: dict
            A dictionary describing the current component event. It should have
            3 keys: name, action, and metadata. A time key will be added
            containing the datetime of the event.
        """
        if event is None:
            return

        event["time"] = dt.datetime.now()
        for handler in self.handlers:
            logger.debug("Adding to handler %s" % str(handler))
            handler.queue.put(event)


class EventHandler(object):
    """ Base class for all event handlers. Creates a separate thread that writes each event out using the handler's "write" method.

    Parameters
    ----------
    component: string
        Optionally argument that allows one to only log events with the
        specified component name.

    Attributes
    ----------
    thread: threading.Thread instance
        The thread that loops infinitely and writes each event placed in its
        queue out through the handler.
    queue: queue.Queue instance
        The queue that handles communicating events between threads.

    Methods
    -------
    write(event) - Writes the event using the specified handler
    close() - Ends the thread so everything can be properly closed out
    """
    STOP_FLAG = 0

    def __init__(self, component=None, *args, **kwargs):

        super(EventHandler, self).__init__(*args, **kwargs)

        self.component = component

        # Initialize the queue
        self.queue = Queue.Queue(maxsize=0)
        #self.queue = Queue(maxsize=0)

        # Initialize the thread
        self.thread = threading.Thread(target=self.run, name=self.__class__.__name__)
        # self.thread = Process(target=self.run, name=self.__class__.__name__)

        # Run the thread
        self.thread.start()

    def filter(self, event):
        """ Returns True if the event should be written """

        if self.component is None:
            return True

        return self.event["name"] == self.component

    def run(self):
        """ Runs inside the separate thread and calls the class' `write` method
        on any new events
        """
        while True:
            event = self.queue.get()
            if event is self.STOP_FLAG:
                logger.debug("Stopping thread %s" % self.thread.name)
                return
            if self.filter(event):
                self.write(event)

    def close(self):
        """ Ends the separate thread """

        self.queue.put(self.STOP_FLAG)

    def __del__(self):

        self.close()

    def write(self, event):

        raise NotImplementedError("Event handlers must implement a `write` method")


class EventInterfaceHandler(EventHandler, hwio.BooleanOutput):
    """ Handler to send event information out to a boolean interface. The event
    information is sent as a sequence of three chunks of bits, the first
    describing the name of the component, the second describing the action, and
    the third with any additional metadata. If the event details are too long to
    fit in the requested number of bytes, they are truncated first.

    Parameters
    ----------
    interface: instance of an Interface
        The interface to use to write the bit string out to hardware
    params: dictionary
        A set of key-value pairs that are sent to the interface when configuring
        the boolean write and when writing to it.
    name_bytes: int
        The number of bytes to use for encoding the name of the component
    action_bytes: int
        The number of bytes to use for encoding the action being performed
    metadata_bytes: int
        The number of bytes to use for any additional metadata.
    component: string
        Optionally argument that allows one to only log events with the
        specified component name.

    Attributes
    ----------
    thread: threading.Thread instance
        The thread that loops infinitely and writes each event placed in its
        queue out through the handler.
    queue: queue.Queue instance
        The queue that handles communicating events between threads.

    Methods
    -------
    write(event) - Writes the event using the specified handler
    close() - Ends the thread so everything can be properly closed out
    to_bit_sequence(event) - Serializes the event details into a string of bits
    """
    def __init__(self, interface, params={}, name_bytes=4, action_bytes=4,
                 metadata_bytes=16, component=None):

        self.name_bytes = name_bytes
        self.action_bytes = action_bytes
        self.metadata_bytes = metadata_bytes
        self.component = component
        self.map_to_bit = dict()
        super(EventInterfaceHandler, self).__init__(interface=interface,
                                                    params=params,
                                                    component=component)

    def write(self, event):
        """ Writes the event out the boolean output

        Parameters
        ----------
        event: dict
            A dictionary describing the current component event. It should have
            3 keys: name, action, and metadata.
        """

        try:
            key = (event["name"], event["action"], event["metadata"])
            bits = self.map_to_bit[key]
        except KeyError:
            bits = self.to_bit_sequence(event)
        self.interface._write_bool(value=bits, **self.params)

    def to_bit_sequence(self, event):
        """ Creates an array of bits containing the details in the event
        dictionary. Once created, the array is cached to speed up future writes.

        Parameters
        ----------
        event: dict
            A dictionary describing the current component event. It should have
            3 keys: name, action, and metadata.

        Returns
        -------
        The array of bits
        """

        if event["metadata"] is None:
            nbytes = self.action_bytes + self.name_bytes
            metadata_array = []
        else:
            nbytes = self.metadata_bytes  + self.action_bytes + self.name_bytes
            try:
                metadata_array = np.fromstring(event["metadata"],
                                               dtype=np.uint16).astype(np.uint8)[:self.metadata_bytes]
            except TypeError:
                metadata_array = np.array(map(ord,
                                              event["metadata"].ljust(self.metadata_bytes)[:self.metadata_bytes]),
                                          dtype=np.uint8)

        int8_array = np.zeros(nbytes, dtype="uint8")
        int8_array[:self.name_bytes] = map(ord, event["name"].ljust(self.name_bytes)[:self.name_bytes])
        int8_array[self.name_bytes:self.name_bytes + self.action_bytes] = map(ord, event["action"].ljust(self.action_bytes)[:self.action_bytes])
        int8_array[self.name_bytes + self.action_bytes:] = metadata_array

        sequence = ([True] +
                    np.unpackbits(int8_array).astype(bool).tolist() +
                    [False])
        key = (event["name"], event["action"], event["metadata"])
        self.map_to_bit[key] = sequence

        return sequence

    def toggle(self):
        pass


class EventDToAHandler(EventHandler):
    """ Handler to format event information so that it can be sent as a sequence
    of bits out an analog output. The event information is returned as a
    sequence of three chunks of bits, the first describing the name of the
    component, the second describing the action, and the third with any
    additional metadata. If the event details are too long to fit in the
    requested number of bytes, they are truncated first. Before being returned,
    the sequence is upsampled by a certain factor and then converted to float64.

    Parameters
    ----------
    name_bytes: int
        The number of bytes to use for encoding the name of the component
    action_bytes: int
        The number of bytes to use for encoding the action being performed
    metadata_bytes: int
        The number of bytes to use for any additional metadata.
    upsample_factor: int
        The factor by which the bit sequence should be upsampled.
    scaling: float
        A scaling factor to scale the analog representation of the digital signal (e.g. send out 3.3 Volts to pass to a digital input)
    component: string
        Optionally argument that allows one to only log events with the
        specified component name.

    All additional key-value pairs are stored for use by the interface

    Methods
    -------
    to_bit_sequence(event) - Serializes the event details into a string of bits
    """
    def __init__(self, name_bytes=4, action_bytes=4, metadata_bytes=16,
                 upsample_factor=1, scaling=1.0, component=None,
                 **interface_params):

        self.name_bytes = name_bytes
        self.action_bytes = action_bytes
        self.metadata_bytes = metadata_bytes
        self.upsample_factor = upsample_factor
        self.scaling = scaling
        self.component = component
        self.map_to_bit = dict()
        self.queue = Queue.Queue(maxsize=0)
        for key, value in interface_params.items():
            setattr(self, key, value)

    def filter(self, event):
        """ Always returns False, as this one should never be called by Events
        """

        return False

    def write(self, event):
        """ Does nothing """
        pass

    def to_bit_sequence(self, event):
        """ Creates an array of bits containing the details in the event
        dictionary. This array is then upsampled and converted to float64 to be
        sent down an analog output. Once created, the array is cached to speed
        up future calls.

        Parameters
        ----------
        event: dict
            A dictionary describing the current component event. It should have
            3 keys: name, action, and metadata.

        Returns
        -------
        The array of bits expressed as analog values
        """

        key = (event["name"], event["action"], event["metadata"])
        # Check if the bit string is already stored
        if key in self.map_to_bit:
            return self.map_to_bit[key]

        trim = lambda ss, l: ss.ljust(l)[:l]
        # Set up int8 arrays where strings are converted to integers using ord
        name_array = np.array(map(ord, trim(event["name"], self.name_bytes)),
                              dtype=np.uint8)
        action_array = np.array(map(ord, trim(event["action"],
                                              self.action_bytes)),
                                dtype=np.uint8)

        # Add the metadata array if a value was passed
        if event["metadata"] is not None:
            metadata_array = np.array(map(ord, trim(event["metadata"],
                                                    self.metadata_bytes)),
                                      dtype=np.uint8)
        else:
            metadata_array = np.array([], dtype=np.uint8)

        sequence = ([True] +
                    np.unpackbits(name_array).astype(bool).tolist() +
                    np.unpackbits(action_array).astype(bool).tolist() +
                    np.unpackbits(metadata_array).astype(bool).tolist() +
                    [False])
        sequence = np.repeat(sequence, self.upsample_factor).astype("float64")
        sequence *= self.scaling

        self.map_to_bit[key] = sequence

        return sequence

    def close(self):
        """ Nothing needs to be done """
        pass


class EventLogHandler(EventHandler):
    """ Writes event details out to a file log.

    Parameters
    ----------
    filename: string
        Path to the output file
    format: string
        A string that can be formatted with the event dictionary
    component: string
        Optional argument that allows one to only log events with the
        specified component name.

    Attributes
    ----------
    thread: threading.Thread instance
        The thread that loops infinitely and writes each event placed in its
        queue out through the handler.
    queue: queue.Queue instance
        The queue that handles communicating events between threads.

    Methods
    -------
    write(event) - Writes the event to the file
    close() - Ends the thread so everything can be properly closed out
    """
    def __init__(self, filename, format=None, component=None):

        self.filename = filename
        if format is None:
            self.format = "\t".join(["{time}",
                                     "{name}",
                                     "{action}",
                                     "{metadata}"])
        super(EventLogHandler, self).__init__(component=component)

    def write(self, event):
        """ Writes the event out to the file

        Parameters
        ----------
        event: dict
            A dictionary describing the current component event. It should have
            4 keys: name, action, and metadata added by the compnent, and time
            added by the Events class.
        """

        if "time" not in event:
            event["time"] = dt.datetime.now()

        with open(self.filename, "a") as fh:
            fh.write(self.format.format(**event) + "\n")

events = Events()

if __name__ == "__main__":

    ihandler = EventInterfaceHandler(None)
    events.add_handler(ihandler)
    for ii in range(100):
        events.write({})
        time.sleep(0.1)

    if ihandler.delay_queue.qsize() > 0:
        for ii in range(ihandler.delay_queue.qsize()):
            ihandler.delays.append(ihandler.delay_queue.get())

    print("Mean delay was %.4e seconds" % (sum(ihandler.delays) / 100))
    print("Max delay was %.4e seconds" % max(ihandler.delays))
