import comedi
import subprocess, datetime
from pyoperant.interfaces import base_
from pyoperant import utils, InterfaceError


class ComediInterface(base_.BaseInterface):
    """docstring for ComediInterface"""

    def __init__(self, device_name, *args, **kwargs):
        super(ComediInterface, self).__init__(*args, **kwargs)
        self.device_name = device_name
        self.read_params = ("subdevice", "channel")
        self.open()

    def open(self):
        self.device = comedi.comedi_open(self.device_name)
        if self.device is None:
            raise InterfaceError("could not open comedi device %s" % self.device_name)

    def close(self):
        s = comedi.comedi_close(self.device)
        if s < 0:
            raise InterfaceError(
                "could not close comedi device %s(%s)" % (self.device_name, self.device)
            )

    def _config_read(self, subdevice, channel):
        s = comedi.comedi_dio_config(
            self.device, subdevice, channel, comedi.COMEDI_INPUT
        )
        if s < 0:
            raise InterfaceError(
                'could not configure comedi device "%s", subdevice %s, channel %s'
                % (self.device, subdevice, channel)
            )
        else:
            return True

    def _config_write(self, subdevice, channel):
        s = comedi.comedi_dio_config(
            self.device, subdevice, channel, comedi.COMEDI_OUTPUT
        )
        if s < 0:
            raise InterfaceError(
                'could not configure comedi device "%s", subdevice %s, channel %s'
                % (self.device, subdevice, channel)
            )
        else:
            return True

    def _read_bool(self, subdevice, channel):
        """ read from comedi port
        """
        (s, v) = comedi.comedi_dio_read(self.device, subdevice, channel)
        if s:
            return not v
        else:
            raise InterfaceError(
                'could not read from comedi device "%s", subdevice %s, channel %s'
                % (self.device, subdevice, channel)
            )

    def _poll(self, subdevice, channel, timeout=None):
        """ runs a loop, querying for pecks. returns peck time or "GoodNite" exception """
        date_fmt = "%Y-%m-%d %H:%M:%S.%f"
        cmd = [
            "comedi_poll",
            self.device_name,
            "-s",
            str(subdevice),
            "-c",
            str(channel),
        ]
        poll_command = utils.Command(cmd)
        status, output, error = poll_command.run(timeout=timeout)
        if status < 0:
            return None
        else:
            timestamp = output
            return datetime.datetime.strptime(timestamp.strip(), date_fmt)

    def _write_bool(self, subdevice, channel, value):
        """Write to comedi port
        """
        value = not value  # invert the value for comedi

        s = comedi.comedi_dio_write(self.device, subdevice, channel, value)
        if s:
            return True
        else:
            raise InterfaceError(
                'could not write to comedi device "%s", subdevice %s, channel %s'
                % (self.device, subdevice, channel)
            )
